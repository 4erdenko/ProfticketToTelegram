from datetime import datetime

import pytz
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from config import settings
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_MONTHS_RU

DEFAULT_TIMEZONE = pytz.timezone(settings.DEFAULT_TIMEZONE)

RUS_TO_MONTH = {v: i + 1 for i, (k, v) in enumerate(LEXICON_MONTHS_RU.items())}


def analytics_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Клавиатура главного меню аналитики с кнопками для выбора разных отчетов
    """
    builder = ReplyKeyboardMarkup(
        keyboard=[
            # Объединяем кнопки продаж и скорости в один ряд
            [
                KeyboardButton(
                    text=LEXICON_BUTTONS_RU['/report_top_shows_sales']
                ),
                KeyboardButton(
                    text=LEXICON_BUTTONS_RU['/report_top_shows_speed']
                ),
            ],
            # Объединяем кнопки прогноза и артистов в один ряд
            [
                KeyboardButton(
                    text=LEXICON_BUTTONS_RU['/report_predict_sell_out']
                ),
                KeyboardButton(
                    text=LEXICON_BUTTONS_RU['/report_top_artists_sales']
                ),
            ],
            # Добавляем новые кнопки для отчётов по возвратам
            [
                KeyboardButton(
                    text=LEXICON_BUTTONS_RU['/report_top_shows_returns']
                ),
                KeyboardButton(
                    text=LEXICON_BUTTONS_RU['/report_top_shows_return_rate']
                ),
            ],
            # Кнопка навигации
            [KeyboardButton(text=LEXICON_BUTTONS_RU['/back_to_main_menu'])],
        ],
        resize_keyboard=True,
        is_persistent=False,  # Чтобы клавиатура легко заменялась
    )
    return builder


def analytics_period_choice_keyboard(
    report_command_base: str,
) -> ReplyKeyboardMarkup:
    """
    Клавиатура для выбора периода отчёта (для всех кроме sold out)
    """
    builder = ReplyKeyboardMarkup(
        keyboard=[
            # Объединяем кнопки периодов в один ряд
            [
                KeyboardButton(text=LEXICON_BUTTONS_RU['/period_all_time']),
                KeyboardButton(
                    text=LEXICON_BUTTONS_RU['/period_current_month']
                ),
            ],
            # Кнопка навигации
            [
                KeyboardButton(
                    text=LEXICON_BUTTONS_RU['/back_to_analytics_menu']
                )
            ],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )
    return builder


def analytics_months_keyboard(
    months: list[tuple[int, int]],
) -> ReplyKeyboardMarkup:
    """
    Клавиатура для выбора месяца для прогноза sold out.
    :param months: список (месяц, год)
    """
    now = datetime.now(DEFAULT_TIMEZONE)
    filtered = [(m, y) for m, y in months if (y, m) >= (now.year, now.month)]
    buttons = []
    for month, year in filtered:
        month_name = LEXICON_MONTHS_RU.get(
            datetime(year, month, 1).strftime('%B'), f'Месяц {month}'
        )
        buttons.append(KeyboardButton(text=f'{month_name} {year}'))
    # Разбиваем по 2 в ряд
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    keyboard.append(
        [KeyboardButton(text=LEXICON_BUTTONS_RU['/back_to_analytics_menu'])]
    )
    return ReplyKeyboardMarkup(
        keyboard=keyboard, resize_keyboard=True, is_persistent=False
    )


def analytics_months_with_alltime_keyboard(
    months: list[tuple[int, int]],
) -> ReplyKeyboardMarkup:
    now = datetime.now(DEFAULT_TIMEZONE)
    filtered = [(m, y) for m, y in months if (y, m) >= (now.year, now.month)]
    buttons = [KeyboardButton(text=LEXICON_BUTTONS_RU['/period_all_time'])]
    for month, year in filtered:
        month_name = LEXICON_MONTHS_RU.get(
            datetime(year, month, 1).strftime('%B'), f'Месяц {month}'
        )
        buttons.append(KeyboardButton(text=f'{month_name} {year}'))
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    keyboard.append(
        [KeyboardButton(text=LEXICON_BUTTONS_RU['/back_to_analytics_menu'])]
    )
    return ReplyKeyboardMarkup(
        keyboard=keyboard, resize_keyboard=True, is_persistent=False
    )
