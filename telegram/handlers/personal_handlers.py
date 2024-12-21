import logging

from aiogram import F, Router
from aiogram.filters import Command, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.user_operations import (get_shows_from_db, get_user,
                                         search_count, set_spectacle_fio)
from telegram.keyboards.main_keyboard import main_keyboard
from telegram.keyboards.personal_keyboard import personal_keyboard
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_RU
from telegram.tg_utils import (check_text, get_current_month_year,
                               get_next_month_year, send_chunks_edit)

personal_user_router = Router(name=__name__)
logger = logging.getLogger(__name__)


class ChooseYourFighter(StatesGroup):
    set_your_fighter = State()


@personal_user_router.message(Command('cancel'))
async def cmd_cancel(
    message: Message, state: FSMContext, session: AsyncSession
):
    await message.answer(
        LEXICON_RU['MAIN_MENU'],
        reply_markup=await main_keyboard(message, session),
    )
    await state.clear()


@personal_user_router.message(
    or_f(F.text == LEXICON_BUTTONS_RU['/set_fighter'], Command('set_actor'))
)
async def cmd_choose_fighter(message: Message, state: FSMContext):
    await message.answer(text=LEXICON_RU['SET_NAME'])
    await state.set_state(ChooseYourFighter.set_your_fighter)


@personal_user_router.message(ChooseYourFighter.set_your_fighter, F.text)
async def cmd_set_fighter(
    message: Message, state: FSMContext, session: AsyncSession
):
    fio_from_user = await check_text(message)
    if fio_from_user:
        await set_spectacle_fio(session, message.from_user.id, fio_from_user)
        await message.answer(
            text=LEXICON_RU['SET_NAME_SUCCESS'].format(message.text.title()),
            reply_markup=await main_keyboard(message, session),
        )
        await state.clear()
    else:
        await message.answer(LEXICON_RU['WRONG_FIO'])
        await state.set_state(ChooseYourFighter.set_your_fighter)


@personal_user_router.message(
    F.text.startswith(LEXICON_BUTTONS_RU['/shows_with'])
)
async def cmd_my_shows(message: Message):
    await message.answer(
        'Выберите месяц', reply_markup=await personal_keyboard()
    )


@personal_user_router.message(F.text == '↩️')
async def cmd_back_to_main_menu(message: Message, session: AsyncSession):
    await message.answer(
        LEXICON_RU['MAIN_MENU'],
        reply_markup=await main_keyboard(message, session),
    )


@personal_user_router.message(F.text == 'Этот')
async def cmd_this(message: Message, session: AsyncSession):
    await search_count(session, message.from_user.id)
    month, year = get_current_month_year()
    try:
        msg = await message.answer(LEXICON_RU['WAIT_MSG'])
        user = await get_user(session, message.from_user.id)
        shows_info = await get_shows_from_db(
            session,
            month,
            year,
            actor_filter=user.spectacle_full_name.lower().strip(),
        )
        await send_chunks_edit(message.chat.id, msg, shows_info)

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


@personal_user_router.message(F.text == 'Следующий')
async def cmd_next(message: Message, session: AsyncSession):
    await search_count(session, message.from_user.id)
    month, year = get_next_month_year()
    try:
        msg = await message.answer(LEXICON_RU['WAIT_MSG'])
        user = await get_user(session, message.from_user.id)
        shows_info = await get_shows_from_db(
            session,
            month,
            year,
            actor_filter=user.spectacle_full_name.lower().strip(),
        )
        await send_chunks_edit(message.chat.id, msg, shows_info)

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
