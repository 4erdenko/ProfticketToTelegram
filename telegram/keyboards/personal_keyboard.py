from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


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
