from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.user_operations import get_user
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU


async def main_keyboard(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    user = await get_user(session, user_id)

    if user.spectacle_full_name:
        spectacle_full_name = user.spectacle_full_name.title()
        button = LEXICON_BUTTONS_RU['/shows_with'] + spectacle_full_name
        personal_menu_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text='Этот месяц'),
                    KeyboardButton(text='Следующий месяц'),
                ],
                [KeyboardButton(text=button)],
            ],
            resize_keyboard=True,
            is_persistent=True,
        )
        return personal_menu_keyboard

    menu_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Этот месяц'),
             KeyboardButton(text='Следующий месяц')],
            [KeyboardButton(text=LEXICON_BUTTONS_RU['/set_fighter'])],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

    return menu_keyboard
