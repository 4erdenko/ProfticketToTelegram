from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.user_operations import get_user


async def main_keyboard(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    user = await get_user(session, user_id)

    personal_menu_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Этот месяц'), KeyboardButton(text='Следующий месяц')],
            [KeyboardButton(text='Мои спектакли')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

    menu_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Этот месяц')],
            [KeyboardButton(text='Следующий месяц')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
    if user.spectacle_full_name:
        return personal_menu_keyboard
    return menu_keyboard
