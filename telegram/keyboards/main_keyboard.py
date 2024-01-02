from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession


async def main_keyboard(message: Message, session: AsyncSession):

    menu_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Этот месяц')],
            [KeyboardButton(text='Следующий месяц')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )

    return menu_keyboard
