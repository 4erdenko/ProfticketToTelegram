import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from telegram.db.user_operations import (get_available_months,
                                         get_shows_from_db, search_count)
from telegram.filters.month_filter import MonthFilter
from telegram.keyboards.main_keyboard import main_keyboard
from telegram.lexicon.lexicon_ru import (LEXICON_COMMANDS_RU, LEXICON_LOGS,
                                         LEXICON_RU, LEXICON_BUTTONS_RU)
from telegram.tg_utils import send_chunks_edit
from telegram.db.models import Show, ShowSeatHistory
import json

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
