import json
import logging
from datetime import datetime
from typing import Any, Dict, Type

import pytz
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)

from config import settings
from telegram.db import User
from telegram.db.models import Show
from telegram.lexicon.lexicon_ru import LEXICON_LOGS, LEXICON_MONTHS_RU
from telegram.tg_utils import parse_show_date

logger = logging.getLogger(__name__)

timezone = pytz.timezone(settings.DEFAULT_TIMEZONE)


def get_current_month_year() -> tuple[int, int]:
    """
    Get the current time in Moscow timezone.

    Returns:
        tuple: A tuple containing the current month and year.
    """
    current_time = datetime.now(timezone)
    return current_time.month, current_time.year


def get_next_month_year() -> tuple[int, int]:
    """
    Get the next month and year based on the current time in Moscow timezone.

    Returns:
        tuple: A tuple containing the next month and year.
    """
    next_time = datetime.now(timezone) + relativedelta(months=+1)
    return next_time.month, next_time.year


def get_three_months() -> tuple:
    """
    Get information about current month and two
    following months in Moscow timezone.

    Returns:
        tuple: A tuple containing three tuples,
        each with (month_number, month_name).
    """
    current_time = datetime.now(timezone)

    months = []
    for i in range(3):
        month_date = current_time + relativedelta(months=i)
        month_number = month_date.month
        month_name = month_date.strftime('%B')
        month_name_ru = LEXICON_MONTHS_RU[month_name]
        months.append((month_number, month_name_ru, month_date.year))

    return tuple(months)


def get_result_message(
    seats: int, previous_seats: int, show_name: str, date: str, buy_link: str
) -> str:
    """
    Function to create a message with information about a performance.

    Args:
        seats: Number of available seats
        previous_seats: Number of seats from previous update
        show_name: Name of the performance
        date: Date of the performance
        buy_link: Ticket purchase link

    Returns:
        str: Formatted message with show information
    """
    if seats == 0:
        seats_text = '<code>SOLD OUT</code>'
    else:
        seats_text = f'Билетов: <a href="{buy_link}">{seats}</a>'

    seats_diff = ''
    if previous_seats is not None and seats != previous_seats:
        diff = seats - previous_seats
        if diff < 0:
            seats_diff = f' ({diff} 🔻)'
        else:
            seats_diff = f' (+{diff} 🔺)'

    return (
        f'📅<strong> {date}</strong>\n'
        f'💎 {show_name}\n'
        f'🎫 {seats_text}{seats_diff}\n'
        '------------------------\n'
    )


async def get_available_months(session: AsyncSession) -> list:
    """
    Get available months that have show data.

    Args:
        session: Database session

    Returns:
        list: List of tuples (month_number, month_name_ru, year)
        for months with data
    """
    current_time = datetime.now(timezone)

    available_months = []
    for i in range(3):
        month_date = current_time + relativedelta(months=i)
        month_number = month_date.month
        year = month_date.year

        query = (
            select(Show)
            .where(
                Show.month == month_number,
                Show.year == year,
                Show.seats > 0,
                ~Show.is_deleted,
            )
            .limit(1)
        )

        result = await session.execute(query)
        if result.scalar():
            month_name = month_date.strftime('%B')
            month_name_ru = LEXICON_MONTHS_RU[month_name]
            available_months.append((month_number, month_name_ru, year))

    return available_months


async def check_data_freshness(session_pool: async_sessionmaker) -> bool:
    """
    Checks if the show data is fresh enough.

    Args:
        session_pool: Database session pool

    Returns:
        bool: True if data is fresh, False otherwise
    """
    try:
        async with session_pool() as session:
            query = (
                select(Show.updated_at)
                .order_by(Show.updated_at.desc())
                .limit(1)
            )
            result = await session.execute(query)
            last_update = result.scalar()

            if not last_update:
                logger.info(LEXICON_LOGS['NO_SHOW_DATA'])
                return False

            current_time = int(datetime.now(timezone).timestamp())
            time_diff = current_time - last_update

            is_fresh = time_diff < settings.UPDATE_INTERVAL
            if is_fresh:
                logger.info(LEXICON_LOGS['DATA_IS_FRESH'])
            else:
                logger.info(LEXICON_LOGS['DATA_NEEDS_UPDATE'])

            return is_fresh
    except Exception as e:
        logger.error(LEXICON_LOGS['ERROR_CHECKING_DATA'].format(str(e)))
        return False


async def get_user(session: AsyncSession, user_id: int) -> Type[User] | None:
    """
    Get user by ID from database.

    Args:
        session: Database session
        user_id: User ID

    Returns:
        User object or None
    """
    return await session.get(User, user_id)


async def search_count(session: AsyncSession, user_id: int) -> None:
    """
    Increment user's search counter.

    Args:
        session: Database session
        user_id: User ID
    """
    user = await get_user(session, user_id)
    if user.search_count is not None:
        user.search_count += 1
    else:
        user.search_count = 1
    await session.commit()


async def set_spectacle_fio(
    session: AsyncSession, user_id: int, spectacle_fio: str
) -> None:
    """
    Set user's spectacle full name.

    Args:
        session: Database session
        user_id: User ID
        spectacle_fio: Full name to set
    """
    user = await get_user(session, user_id)
    user.spectacle_full_name = spectacle_fio
    await session.commit()


async def get_shows_from_db(
    session: AsyncSession,
    month: int,
    year: int,
    actor_filter=None,
    descending: bool = False,
) -> str:
    """
    Get shows from database for specified month and year.

    Args:
        session: Database session
        month: Month number
        year: Year
        actor_filter: Optional actor name to filter shows
        descending: Sort in descending order if True

    Returns:
        str: Formatted message with shows information
    """
    query = select(Show).where(
        Show.month == month, Show.year == year, ~Show.is_deleted
    )
    result = await session.execute(query)
    shows = result.scalars().all()

    shows.sort(
        key=lambda s: parse_show_date(s.date),
        reverse=descending,
    )

    if not shows:
        return 'Нет спектаклей в этом месяце'

    msg = ''
    show_count = 0
    last_update = 0

    for show in shows:
        actors = json.loads(show.actors)
        actors_lower = [actor.lower().strip() for actor in actors if actor]

        if actor_filter and actor_filter not in actors_lower:
            continue

        show_count += 1
        msg += get_result_message(
            show.seats,
            show.previous_seats,
            show.show_name,
            show.date,
            show.buy_link,
        )
        last_update = max(last_update, show.updated_at)

    if show_count == 0:
        return 'Нет спектаклей в этом месяце'

    update_time = datetime.fromtimestamp(last_update, tz=timezone)
    formatted_time = update_time.strftime('%d.%m.%Y %H:%M')

    total = (
        f'Всего {show_count} спектаклей🌚\n'
        f'Данные актуальны на: {formatted_time}'
    )
    return f'{msg}{total}'


async def setup_database() -> tuple[async_sessionmaker, Dict[str, Any]]:
    """
    Configures database connection and returns session maker.

    Returns:
        tuple: Session maker and context data
    """
    engine = create_async_engine(
        settings.DB_URL,
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
    logger.info(LEXICON_LOGS['ENGINE_CREATED'])

    session_pool = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )
    logger.info(LEXICON_LOGS['SESSION_MAKER_INITIALIZED'])

    return session_pool, {'session_pool': session_pool}
