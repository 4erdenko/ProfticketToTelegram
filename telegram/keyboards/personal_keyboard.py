from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.db.user_operations import get_available_months


async def personal_keyboard(session: AsyncSession):
    # Получаем доступные месяцы
    months = await get_available_months(session)

    # Если нет доступных месяцев, показываем только кнопку возврата
    if not months:
        personal_menu_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text='↩️')],
            ],
            resize_keyboard=True,
            is_persistent=True,
        )
        return personal_menu_keyboard

    # Создаем кнопки для доступных месяцев с префиксом
    month_buttons = [KeyboardButton(text=f'👤 {month[1]}') for month in months]

    personal_menu_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            month_buttons,
            [KeyboardButton(text='↩️')],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
    return personal_menu_keyboard
