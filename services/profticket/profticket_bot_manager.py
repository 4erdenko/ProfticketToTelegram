from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from services.profticket.profticket_api import ProfticketsInfo
from services.profticket.utils import pluralize
from telegram.db.user_operations import get_user
from telegram.lexicon.lexicon_ru import LEXICON_RU
from telegram.tg_utils import get_result_message


async def collect_shows_info(
    profticket: ProfticketsInfo, month: int, year: int, actor_filter=None
):
    profticket.set_date(month, year)
    result = await profticket.collect_full_info()
    if not result:
        return LEXICON_RU['NONE_SHOWS_THIS_MONTH']

    msg = ''
    show_count = 0

    for item in result.values():
        if actor_filter and actor_filter not in [
            actor.lower() for actor in item['actors']
        ]:
            continue

        date = item['date']
        show_name = item['show_name'].strip()
        seats = int(item['seats'])
        buy_link = item['buy_link']

        show_count += 1
        msg += get_result_message(seats, show_name, date, buy_link)

    if show_count == 0:
        return LEXICON_RU['NONE_SHOWS_THIS_MONTH']

    total = f'Всего {show_count} {pluralize("спектакль", show_count)}🌚'
    return f'{msg}{total}'


async def get_all_shows_info(profticket: ProfticketsInfo, month, year):
    return await collect_shows_info(profticket, month, year)


async def get_personal_shows_info(
    profticket: ProfticketsInfo,
    session: AsyncSession,
    message: Message,
    month: int,
    year: int,
):
    user = await get_user(session, message.from_user.id)
    user_fio = user.spectacle_full_name.lower().strip()
    return await collect_shows_info(
        profticket, month, year, actor_filter=user_fio
    )
