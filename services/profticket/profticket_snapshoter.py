import asyncio
import json
import logging
from datetime import datetime

from aiogram import Bot
import pytz
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.profticket.profticket_api import ProfticketsInfo
from telegram.db.models import Show
from telegram.tg_utils import get_current_month_year, get_next_month_year

logger = logging.getLogger(__name__)
timezone = pytz.timezone(settings.DEFAULT_TIMEZONE)

class ShowUpdateService:
    def __init__(self, session_maker, profticket: ProfticketsInfo, bot: Bot):
        self.session_maker = session_maker
        self.profticket = profticket
        self.bot = bot
        self.consecutive_errors = 0

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
            # # Check the freshness of the data
            # if await self._check_data_freshness(session, month, year):
            #     logger.info(
            #         f'Data for {month}/{year} is up-to-date, skipping update'
            #     )
            #     return True

            self.profticket.set_date(month, year)
            shows = await self.profticket.collect_full_info()
            if not shows:
                logger.warning(f'No data available for {month}/{year}')
                return False

            current_time = int(datetime.now(timezone).timestamp())

            current_shows = await session.execute(
                select(Show).where(Show.month == month, Show.year == year)
            )
            current_shows_dict = {
                show.id: show.seats for show in current_shows.scalars()
            }

            await session.execute(
                delete(Show).where(Show.month == month, Show.year == year)
            )

            for event_id, show_data in shows.items():
                show = Show(
                    id=event_id,
                    show_id=int(show_data['show_id']),
                    theater=show_data['theater'],
                    scene=show_data['scene'],
                    show_name=show_data['show_name'],
                    date=show_data['date'],
                    duration=str(show_data['duration']),
                    age=str(show_data['age']),
                    seats=int(show_data['seats'] or 0),
                    previous_seats=current_shows_dict.get(event_id),                    image=show_data['image'],
                    annotation=show_data['annotation'],
                    min_price=int(show_data['min_price'] or 0),
                    max_price=int(show_data['max_price'] or 0),
                    pushkin=bool(show_data['pushkin']),
                    buy_link=show_data['buy_link'],
                    actors=json.dumps(
                        [actor for actor in show_data['actors'] if actor],
                        ensure_ascii=False,
                    ),
                    month=month,
                    year=year,
                    updated_at=current_time,
                )
                session.add(show)

            await session.commit()
            self.consecutive_errors = 0
            logger.info(f'Show data for {month}/{year} has been updated')
            return True
        except Exception as e:
            logger.error(f'Error updating data for {month}/{year}: {e}')
            await session.rollback()
            self.consecutive_errors += 1

            if self.consecutive_errors >= settings.MAX_CONSECUTIVE_ERRORS:
                await self._notify_admin(
                    f'❗️ Critical error during data update!\n'
                    f'Month: {month}/{year}\n'
                    f'Error: {str(e)}\n'
                    f'Consecutive error count: {self.consecutive_errors}'
                )

            return False

    async def update_loop(self):
        while True:
            try:
                async with self.session_maker() as session:
                    current_month, current_year = get_current_month_year()
                    next_month, next_year = get_next_month_year()

                    current_success = await self._update_month_data(
                        session, current_month, current_year
                    )
                    next_success = await self._update_month_data(
                        session, next_month, next_year
                    )

                    wait_time = (
                        settings.UPDATE_INTERVAL
                        if current_success and next_success
                        else settings.ERROR_RETRY_INTERVAL
                    )
            except Exception as e:
                logger.error(f'Error in update loop: {e}')
                await self._notify_admin(f'🆘 Error in update loop: {str(e)}')
                wait_time = settings.ERROR_RETRY_INTERVAL

            await asyncio.sleep(wait_time)
