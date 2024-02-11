from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession


async def personal_keyboard():
    personal_menu_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Этот'), KeyboardButton(text='Следующий')],
            [KeyboardButton(text='↩️')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
    return personal_menu_keyboard
