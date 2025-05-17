import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.user_operations import (
    get_available_months,
    get_shows_from_db,
    get_top_shows_and_actors,
    search_count,
)
from telegram.filters.month_filter import MonthFilter
from telegram.keyboards.main_keyboard import main_keyboard
from telegram.lexicon.lexicon_ru import (LEXICON_COMMANDS_RU, LEXICON_LOGS,
                                         LEXICON_RU)
from telegram.tg_utils import send_chunks_edit

user_router = Router(name=__name__)
logger = logging.getLogger(__name__)


@user_router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    await message.answer(
        LEXICON_COMMANDS_RU['/start'],
        reply_markup=await main_keyboard(message, session),
    )


@user_router.message(Command('help'))
async def cmd_help(message: Message):
    logger.info(
        LEXICON_LOGS['LOG_MSH_HELP_COMMAND'].format(message.from_user.id)
    )
    await message.answer(LEXICON_RU['HELP_CONTACT'])


@user_router.message(Command('rating'))
async def cmd_rating(message: Message, session: AsyncSession):
    """Send top shows and actors."""
    parts = message.text.split()
    limit = 5
    if len(parts) > 1 and parts[1].isdigit():
        limit = int(parts[1])

    top_shows, top_actors = await get_top_shows_and_actors(session, limit=limit)

    msg_lines = ['\uD83D\uDCC8 Top shows:']
    for i, (name, score) in enumerate(top_shows, 1):
        msg_lines.append(f'{i}. {name} - {score}')

    msg_lines.append('\n\uD83C\uDFAD Top actors:')
    for i, (name, score) in enumerate(top_actors, 1):
        msg_lines.append(f'{i}. {name.title()} - {score}')

    await message.answer('\n'.join(msg_lines))


@user_router.message(MonthFilter(personal=False))
async def cmd_show_month(message: Message, session: AsyncSession):
    await search_count(session, message.from_user.id)
    months = await get_available_months(session)
    selected_month = None

    for month in months:
        if month[1] == message.text:
            selected_month = month
            break

    if selected_month:
        month_number, _, year = selected_month
        try:
            msg = await message.answer(LEXICON_RU['WAIT_MSG'])
            shows_info = await get_shows_from_db(session, month_number, year)
            await send_chunks_edit(message.chat.id, msg, shows_info)

            logger.info(
                LEXICON_LOGS['USER_GOT_SHOWS'].format(
                    message.from_user.full_name,
                    message.from_user.username,
                    message.from_user.id,
                    month_number,
                )
            )
        except Exception as e:
            await message.answer(LEXICON_RU['ERROR_MSG'])
            logger.error(
                LEXICON_LOGS['USER_ERROR'].format(
                    message.from_user.full_name,
                    message.from_user.username,
                    message.from_user.id,
                    str(e),
                )
            )


@user_router.message(
    F.text.in_({'Этот месяц', 'Следующий месяц', 'Выбрать актёра/актрису'})
)
async def handle_old_buttons(message: Message, session: AsyncSession):
    await message.answer(
        LEXICON_RU['MAIN_MENU'],
        reply_markup=await main_keyboard(message, session),
    )
