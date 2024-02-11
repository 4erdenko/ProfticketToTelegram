import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from services.profticket.profticket_api import ProfticketsInfo
from services.profticket.profticket_bot_manager import get_all_shows_info
from telegram.db.user_operations import search_count
from telegram.keyboards.main_keyboard import main_keyboard
from telegram.lexicon.lexicon_ru import (LEXICON_COMMANDS_RU, LEXICON_LOGS,
                                         LEXICON_RU)
from telegram.tg_utils import (get_current_month_year, get_next_month_year,
                               send_chunks_edit)

user_router = Router(name=__name__)
logger = logging.getLogger(__name__)


@user_router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    await message.answer(
        LEXICON_COMMANDS_RU['/start'],
        reply_markup=await main_keyboard(message, session),
    )


@user_router.message(Command('help'))
async def cmd_start(message: Message):
    logger.info(LEXICON_LOGS['LOG_MSH_HELP_COMMAND'].format(
        message.from_user.id))
    await message.answer(LEXICON_RU['HELP_CONTACT'])


@user_router.message(F.text == 'Этот месяц')
async def cmd_this_month(
    message: Message, session: AsyncSession, profticket: ProfticketsInfo
):
    await search_count(session, message.from_user.id)
    month, year = get_current_month_year()
    try:
        msg = await message.answer(LEXICON_RU['WAIT_MSG'])
        await send_chunks_edit(
            message.chat.id,
            msg,
            await get_all_shows_info(profticket, month, year),
        )

        logger.info(
            f'{message.from_user.full_name} '
            f'(@{message.from_user.username}) '
            f'ID({message.from_user.id}) got shows for {month} month'
        )
    except Exception as e:
        await message.answer(
            'Произошла ошибка, попробуйте ещё раз через минутку.'
        )
        logger.error(e)


@user_router.message(F.text == 'Следующий месяц')
async def next_month_command(
    message: Message, session: AsyncSession, profticket: ProfticketsInfo
):
    await search_count(session, message.from_user.id)
    month, year = get_next_month_year()
    try:
        msg = await message.answer(LEXICON_RU['WAIT_MSG'])
        await send_chunks_edit(
            message.chat.id,
            msg,
            await get_all_shows_info(profticket, month, year),
        )

        logger.info(
            f'{message.from_user.full_name} '
            f'(@{message.from_user.username}) '
            f'ID({message.from_user.id}) got shows for {month} month'
        )
    except Exception as e:
        await message.answer(
            'Произошла ошибка, попробуйте ещё раз через минутку.'
        )
        logger.error(e)
