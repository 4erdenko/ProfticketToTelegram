from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.user_operations import get_available_months, get_user
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU


async def main_keyboard(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    user = await get_user(session, user_id)
    months = await get_available_months(session)

    kb = []
    if months:
        month_buttons = [KeyboardButton(text=month[1]) for month in months]
        kb.append(month_buttons)

    if user.spectacle_full_name:
        spectacle_full_name = user.spectacle_full_name.title()
        button_text = LEXICON_BUTTONS_RU['/shows_with'] + spectacle_full_name
        kb.append([KeyboardButton(text=button_text)])
    else:
        kb.append([KeyboardButton(text=LEXICON_BUTTONS_RU['/set_fighter'])])

    # Add Analytics button
    kb.append([KeyboardButton(text=LEXICON_BUTTONS_RU['/analytics_menu'])])

    if not months and not user.spectacle_full_name:
        kb = [
            [KeyboardButton(text=LEXICON_BUTTONS_RU['/set_fighter'])],
            [KeyboardButton(text=LEXICON_BUTTONS_RU['/analytics_menu'])],
        ]
    elif not months and user.spectacle_full_name:
        spectacle_full_name = user.spectacle_full_name.title()
        button_text = LEXICON_BUTTONS_RU['/shows_with'] + spectacle_full_name
        kb = [
            [KeyboardButton(text=button_text)],
            [KeyboardButton(text=LEXICON_BUTTONS_RU['/analytics_menu'])],
        ]

    return ReplyKeyboardMarkup(
        keyboard=kb, resize_keyboard=True, is_persistent=True
    )
