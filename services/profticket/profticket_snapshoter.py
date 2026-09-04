import asyncio
import json
import logging
from datetime import datetime

import pytz
from aiogram import Bot
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.ermolova import ErmolovaInfo
from services.profticket.profticket_api import ProfticketsInfo
from telegram.db.models import Show, ShowSeatHistory

logger = logging.getLogger(__name__)
timezone = pytz.timezone(settings.DEFAULT_TIMEZONE)


class ShowUpdateService:
    def __init__(
        self,
        session_maker,
        profticket: ProfticketsInfo | ErmolovaInfo,
        bot: Bot,
    ) -> None:
        self.session_maker = session_maker
        self.profticket = profticket
        self.bot = bot
        self.month_errors: dict[tuple[int, int], int] = {}

    async def _notify_admin(self, message: str):
        """Send a notification to the admin"""
        try:
            await self.bot.send_message(settings.ADMIN_ID, message)
        except Exception as e:
            logger.error(f'Error sending notification to admin: {e}')

    async def _check_data_freshness(
        self, session: AsyncSession, month: int, year: int
    ) -> bool:
        """Check the freshness of the data"""
        query = (
            select(Show.updated_at)
            .where(Show.month == month, Show.year == year)
            .order_by(Show.updated_at.desc())
            .limit(1)
        )
        result = await session.execute(query)
        last_update = result.scalar()
        if not last_update:
            return False
        current_time = int(datetime.now(timezone).timestamp())
        return (current_time - last_update) < settings.MAX_DATA_AGE

    async def _update_month_data(
        self, session: AsyncSession, month: int, year: int
    ) -> bool:
        try:
            self.profticket.set_date(month, year)
            shows = await self.profticket.collect_full_info()
            if not shows:
                raise ValueError(f'No verified data for {month}/{year}')

            current_time = int(datetime.now(timezone).timestamp())

            # Получаем текущие данные о местах
            current_shows = await session.execute(
                select(Show).where(
                    Show.month == month,
                    Show.year == year,
                    ~Show.is_deleted,
                )
            )
            current_shows_dict = {
                show.id: show.seats for show in current_shows.scalars()
            }

            # Подготавливаем данные для обновления
            for event_id, show_data in shows.items():
                show_values = {
                    'id': event_id,
                    'show_id': int(show_data['show_id']),
                    'theater': show_data['theater'],
                    'scene': show_data['scene'],
                    'show_name': show_data['show_name'],
                    'date': show_data['date'],
                    'duration': str(show_data['duration'])
                    if show_data['duration'] is not None
                    else None,
                    'age': str(show_data['age'])
                    if show_data['age'] is not None
                    else None,
                    'seats': int(show_data['seats'])
                    if show_data['seats'] is not None
                    else None,
                    'previous_seats': current_shows_dict.get(event_id)
                    if show_data['seats'] is not None
                    else None,
                    'image': show_data['image'],
                    'annotation': show_data['annotation'],
                    'min_price': int(show_data['min_price'])
                    if show_data['min_price'] is not None
                    else None,
                    'max_price': int(show_data['max_price'])
                    if show_data['max_price'] is not None
                    else None,
                    'pushkin': bool(show_data['pushkin']),
                    'buy_link': show_data['buy_link'],
                    'actors': json.dumps(
                        [actor for actor in show_data['actors'] if actor],
                        ensure_ascii=False,
                    ),
                    'month': month,
                    'year': year,
                    'updated_at': current_time,
                    'is_deleted': False,
                }

                # Используем insert().on_conflict_do_update()
                stmt = insert(Show).values(show_values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'], set_=show_values
                )
                await session.execute(stmt)

                if show_values['seats'] is not None:
                    await session.execute(
                        insert(ShowSeatHistory).values(
                            show_id=event_id,
                            timestamp=current_time,
                            seats=show_values['seats'],
                        )
                    )

            # Мягко удаляем устаревшие записи
            all_event_ids = list(shows.keys())
            await session.execute(
                Show.__table__.update()
                .where(
                    Show.month == month,
                    Show.year == year,
                    Show.id.notin_(all_event_ids),
                    ~Show.is_deleted,
                )
                .values(is_deleted=True)
            )

            await session.commit()
            self.month_errors.pop((year, month), None)
            logger.info(f'Show data for {month}/{year} has been updated')
            return True

        except Exception as e:
            logger.error(f'Error updating data for {month}/{year}: {e}')
            await session.rollback()
            key = (year, month)
            self.month_errors[key] = self.month_errors.get(key, 0) + 1
            error_count = self.month_errors[key]

            if error_count == settings.MAX_CONSECUTIVE_ERRORS:
                await self._notify_admin(
                    f'❗️ Critical error during data update!\n'
                    f'Month: {month}/{year}\n'
                    f'Error: {str(e)}\n'
                    f'Consecutive error count: {error_count}'
                )

            return False

    async def update_loop(self):
        logger.info('Starting update loop service')
        while True:
            try:
                async with self.session_maker() as session:
                    # Проверяем и обновляем 3 месяца
                    for i in range(3):
                        check_date = datetime.now(timezone) + relativedelta(
                            months=i
                        )
                        month = check_date.month
                        year = check_date.year

                        logger.info(
                            f'Checking data freshness for {month}/{year}'
                        )
                        is_fresh = await self._check_data_freshness(
                            session, month, year
                        )

                        if not is_fresh:
                            logger.info(f'Updating data for {month}/{year}')
                            await self._update_month_data(session, month, year)

                    wait_time = settings.UPDATE_INTERVAL
                    logger.info(
                        f'Waiting {wait_time} seconds before next check'
                    )

            except Exception as e:
                logger.error(f'Error in update loop: {e}')
                await self._notify_admin(f'🆘 Error in update loop: {str(e)}')
                wait_time = settings.ERROR_RETRY_INTERVAL
                logger.info(f'Will retry in {wait_time} seconds')

            await asyncio.sleep(wait_time)

    async def _has_shows(
        self, session: AsyncSession, month: int, year: int
    ) -> bool:
        """Check if there are any shows for the given month and year."""
        query = (
            select(Show)
            .where(Show.month == month, Show.year == year, Show.seats > 0)
            .limit(1)
        )

        result = await session.execute(query)
        return result.scalar() is not None
