import logging

from aiogram import F, Router
from aiogram.filters import Command, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.user_operations import (
    get_available_months,
    get_shows_from_db,
    get_user,
    search_count,
    set_spectacle_fio,
)
from telegram.filters.month_filter import MonthFilter
from telegram.keyboards.main_keyboard import main_keyboard
from telegram.keyboards.personal_keyboard import personal_keyboard
from telegram.lexicon.lexicon_ru import (
    LEXICON_BUTTONS_RU,
    LEXICON_LOGS,
    LEXICON_RU,
)
from telegram.tg_utils import check_text, send_chunks_edit

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
async def cmd_my_shows(message: Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    if not user or not user.spectacle_full_name:
        await message.answer(
            LEXICON_RU['MAIN_MENU'],
            reply_markup=await main_keyboard(message, session),
        )
        return

    await message.answer(
        LEXICON_RU['CHOOSE_MONTH'],
        reply_markup=await personal_keyboard(session),
    )


@personal_user_router.message(F.text == '↩️')
async def cmd_back_to_main_menu(message: Message, session: AsyncSession):
    await message.answer(
        LEXICON_RU['MAIN_MENU'],
        reply_markup=await main_keyboard(message, session),
    )


@personal_user_router.message(MonthFilter(personal=True))
async def cmd_show_month_personal(message: Message, session: AsyncSession):
    await search_count(session, message.from_user.id)
    user = await get_user(session, message.from_user.id)
    if not user or not user.spectacle_full_name:
        await message.answer(
            LEXICON_RU['MAIN_MENU'],
            reply_markup=await main_keyboard(message, session),
        )
        return

    months = await get_available_months(session)
    selected_month = None

    message_text = message.text.replace('👤 ', '')

    for month in months:
        if month[1] == message_text:
            selected_month = month
            break

    if selected_month:
        month_number, _, year = selected_month
        try:
            msg = await message.answer(LEXICON_RU['WAIT_MSG'])
            shows_info = await get_shows_from_db(
                session,
                month_number,
                year,
                actor_filter=user.spectacle_full_name.lower().strip(),
            )
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


@personal_user_router.message(F.text.in_({'Этот', 'Следующий', 'Назад'}))
async def handle_old_personal_buttons(message: Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    if user and user.spectacle_full_name and message.text != 'Назад':
        await message.answer(
            LEXICON_RU['CHOOSE_MONTH'],
            reply_markup=await personal_keyboard(session),
        )
    else:
        await message.answer(
            LEXICON_RU['MAIN_MENU'],
            reply_markup=await main_keyboard(message, session),
        )
