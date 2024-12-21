import json
import logging
from datetime import datetime
from typing import Type

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db import User
from telegram.db.models import Show
from telegram.tg_utils import get_result_message

logger = logging.getLogger(__name__)

timezone = pytz.timezone('Europe/Moscow')


async def get_user(session: AsyncSession, user_id: int) -> Type[User] | None:
    return await session.get(User, user_id)


async def search_count(session: AsyncSession, user_id: int):
    user = await get_user(session, user_id)
    if user.search_count is not None:
        user.search_count += 1
    else:
        user.search_count = 1
    await session.commit()


async def set_spectacle_fio(
    session: AsyncSession, user_id: int, spectacle_fio: str
):
    user = await get_user(session, user_id)
    user.spectacle_full_name = spectacle_fio
    await session.commit()


async def get_shows_from_db(
    session: AsyncSession, month: int, year: int, actor_filter=None
):
    query = select(Show).where(Show.month == month, Show.year == year)
    result = await session.execute(query)
    shows = result.scalars().all()

    if not shows:
        return 'Нет спектаклей в этом месяце'

    msg = ''
    show_count = 0
    last_update = 0

    for show in shows:
        actors = json.loads(show.actors)
        if actor_filter and actor_filter not in [
            actor.lower() for actor in actors
        ]:
            continue

        show_count += 1
        msg += get_result_message(
            show.seats, show.show_name, show.date, show.buy_link
        )
        last_update = max(last_update, show.updated_at)

    if show_count == 0:
        return 'Нет спектаклей в этом месяце'

    update_time = datetime.fromtimestamp(last_update, tz=timezone)
    formatted_time = update_time.strftime('%d.%m.%Y %H:%M')

    total = f'Всего {show_count} спектаклей🌚\nДанные актуальны на: {formatted_time}'
    return f'{msg}{total}'
