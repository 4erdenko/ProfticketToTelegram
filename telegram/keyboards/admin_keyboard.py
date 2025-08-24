from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU


def admin_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура админского меню.
    """
    keyboard = [
        [
            KeyboardButton(text=LEXICON_BUTTONS_RU['/admin_stats']),
            KeyboardButton(text=LEXICON_BUTTONS_RU['/admin_users']),
        ],
        [
            KeyboardButton(text=LEXICON_BUTTONS_RU['/admin_prefs']),
            KeyboardButton(text=LEXICON_BUTTONS_RU['/admin_db']),
        ],
        [KeyboardButton(text=LEXICON_BUTTONS_RU['/back_to_main_menu'])],
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard, resize_keyboard=True, is_persistent=False
    )
