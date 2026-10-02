import logging
from datetime import datetime
from html import escape

import pytz
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.profticket.analytics_repository import AnalyticsRepository
from telegram.keyboards.analytics_keyboard import (
    RUS_TO_MONTH,
    analytics_main_menu_keyboard,
    analytics_months_keyboard,
    analytics_months_with_alltime_keyboard,
)
from telegram.keyboards.main_keyboard import main_keyboard
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_RU
from telegram.tg_utils import MONTHS_GENITIVE_RU, send_chunks_answer

logger = logging.getLogger(__name__)
analytics_router = Router(name='analytics_router')

# Настройка часового пояса
try:
    DEFAULT_TIMEZONE = pytz.timezone(settings.DEFAULT_TIMEZONE)
except Exception:
    DEFAULT_TIMEZONE = None


# FSM for choosing report period
class AnalyticsStates(StatesGroup):
    choosing_period = State()
    choosing_month = State()
    choosing_month_for_top = State()


# REPORTS объединённый
REPORTS = {
    LEXICON_BUTTONS_RU['/report_top_shows_sales']: {
        'kind': 'sales',
        'title': LEXICON_RU['TOP_SHOWS_SALES_REPORT_TITLE'],
    },
    LEXICON_BUTTONS_RU['/report_top_shows_speed']: {
        'kind': 'speed',
        'title': LEXICON_RU['TOP_SHOWS_SPEED_REPORT_TITLE'],
    },
    LEXICON_BUTTONS_RU['/report_predict_sell_out']: {
        'kind': 'prediction',
        'title': LEXICON_RU['PREDICT_SELL_OUT_REPORT_TITLE'],
    },
    LEXICON_BUTTONS_RU['/report_top_artists_sales']: {
        'kind': 'artists',
        'title': LEXICON_RU['TOP_ARTISTS_REPORT'],
    },
    LEXICON_BUTTONS_RU['/report_calendar_pace']: {
        'kind': 'calendar',
        'title': LEXICON_RU['CALENDAR_PACE_REPORT_TITLE'],
    },
    # Добавляем новые отчёты по возвратам
    LEXICON_BUTTONS_RU['/report_top_shows_returns']: {
        'kind': 'returns',
        'title': LEXICON_RU['TOP_SHOWS_RETURNS_REPORT_TITLE'],
    },
    LEXICON_BUTTONS_RU['/report_top_shows_return_rate']: {
        'kind': 'return_rate',
        'title': LEXICON_RU['TOP_SHOWS_RETURN_RATE_REPORT_TITLE'],
    },
}

ADMIN_NAVIGATION = {
    text
    for command, text in LEXICON_BUTTONS_RU.items()
    if command.startswith('/admin_')
}


# --- Navigation Handlers ---
@analytics_router.message(F.text == LEXICON_BUTTONS_RU['/analytics_menu'])
async def cmd_analytics_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        LEXICON_RU['ANALYTICS_MENU_TITLE'],
        reply_markup=analytics_main_menu_keyboard(),
    )


@analytics_router.message(F.text == '/analytics')
async def cmd_analytics_menu_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        LEXICON_RU['ANALYTICS_MENU_TITLE'],
        reply_markup=analytics_main_menu_keyboard(),
    )


@analytics_router.message(
    F.text == LEXICON_BUTTONS_RU['/back_to_analytics_menu']
)
async def cmd_back_to_analytics_menu(
    message: Message, state: FSMContext
) -> None:
    await state.clear()
    await message.answer(
        LEXICON_RU['ANALYTICS_MENU_TITLE'],
        reply_markup=analytics_main_menu_keyboard(),
    )


@analytics_router.message(F.text == LEXICON_BUTTONS_RU['/back_to_main_menu'])
async def cmd_back_to_main_menu(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await message.answer(
        LEXICON_RU['MAIN_MENU'],
        reply_markup=await main_keyboard(message, session),
    )


# --- Report Type Selection (initiates period choice) ---
@analytics_router.message(
    F.text.in_(
        [
            LEXICON_BUTTONS_RU['/report_top_shows_sales'],
            LEXICON_BUTTONS_RU['/report_calendar_pace'],
            LEXICON_BUTTONS_RU['/report_top_shows_speed'],
            LEXICON_BUTTONS_RU['/report_top_artists_sales'],
            # Добавляем новые отчёты в обработчик
            LEXICON_BUTTONS_RU['/report_top_shows_returns'],
            LEXICON_BUTTONS_RU['/report_top_shows_return_rate'],
        ]
    )
)
async def cmd_select_report_type(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    months = await AnalyticsRepository(session).available_months()
    if not months:
        await message.answer(LEXICON_RU['NO_DATA_FOR_REPORT'])
        return
    await state.set_state(AnalyticsStates.choosing_month_for_top)
    await state.update_data(report_type_to_generate=message.text)
    await message.answer(
        LEXICON_RU['CHOOSE_REPORT_PERIOD'],
        reply_markup=analytics_months_with_alltime_keyboard(months),
    )


@analytics_router.message(
    F.text == LEXICON_BUTTONS_RU['/report_predict_sell_out']
)
async def cmd_select_soldout_report(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    months = await AnalyticsRepository(session).available_months()
    if not months:
        await message.answer(LEXICON_RU['NO_DATA_FOR_REPORT'])
        return
    await state.set_state(AnalyticsStates.choosing_month)
    await state.update_data(report_type_to_generate=message.text)
    await message.answer(
        LEXICON_RU['CHOOSE_REPORT_PERIOD'],
        reply_markup=analytics_months_keyboard(months),
    )


# --- Period Selection & Report Generation ---
@analytics_router.message(
    StateFilter(AnalyticsStates.choosing_month_for_top),
    F.text,
    ~F.text.in_(ADMIN_NAVIGATION),
)
async def cmd_generate_top_report_month(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if not message.text:
        await message.answer(LEXICON_RU['CHOOSE_REPORT_PERIOD'])
        return
    user_data = await state.get_data()
    text = message.text.strip()
    if text == LEXICON_BUTTONS_RU['/period_all_time']:
        month, year = None, None
        period_text = ' (за всё время)'
    else:
        try:
            text_parts = text.split()
            if len(text_parts) != 2:
                await message.answer(LEXICON_RU['ERROR_MSG'])
                return
            rus_month_name = text_parts[0]
            year = int(text_parts[1])
            month = RUS_TO_MONTH.get(rus_month_name)
            if not month:
                await message.answer(LEXICON_RU['ERROR_MSG'])
                return
            period_text = f' (за {text})'
        except Exception:
            await message.answer(LEXICON_RU['ERROR_MSG'])
            return
    report_type_key = user_data.get('report_type_to_generate')
    if report_type_key not in REPORTS:
        await message.answer(LEXICON_RU['ERROR_MSG'])
        return
    report_title = REPORTS[report_type_key]['title']
    await state.clear()

    # Логгирование запроса аналитики
    period = (
        text if text != LEXICON_BUTTONS_RU['/period_all_time'] else 'all time'
    )
    logger.info(
        f'User {message.from_user.full_name} (@{message.from_user.username}, '
        f'id={message.from_user.id}) '
        f"analytics '{report_type_key}' for {period}"
    )

    await message.answer(
        LEXICON_RU['WAIT_MSG'], reply_markup=analytics_main_menu_keyboard()
    )
    report_data = await AnalyticsRepository(session).report(
        REPORTS[report_type_key]['kind'], month, year, n=10
    )
    results = report_data.results

    # Проверяем результаты с учётом типа отчёта
    if report_type_key == LEXICON_BUTTONS_RU['/report_calendar_pace']:
        # calendar_pace возвращает dict, а не list
        if not results or not results.get('dates'):
            await message.answer(
                LEXICON_RU['NO_DATA_FOR_REPORT'] + period_text
            )
            return
    elif not results:
        await message.answer(LEXICON_RU['NO_DATA_FOR_REPORT'] + period_text)
        return

    response_lines = [f'<b>{report_title}{period_text}:</b>']

    # Добавляем пояснение формата для отчета продаж
    if report_type_key == LEXICON_BUTTONS_RU['/report_top_shows_sales']:
        response_lines.append(
            f'<i>{LEXICON_RU["TOP_SHOWS_SALES_FORMAT_EXPLANATION"]}</i>'
        )
    elif report_type_key == LEXICON_BUTTONS_RU['/report_top_shows_speed']:
        response_lines.append(
            f'<i>{LEXICON_RU["TOP_SHOWS_SPEED_FORMAT_EXPLANATION"]}</i>'
        )
    elif report_type_key == LEXICON_BUTTONS_RU['/report_calendar_pace']:
        response_lines.append(
            f'<i>{LEXICON_RU["CALENDAR_PACE_FORMAT_EXPLANATION"]}</i>'
        )

    first_seen = report_data.first_seen
    artist_first_seen = report_data.artist_first_seen

    # Форматирование результата в зависимости от типа отчёта
    if report_type_key == LEXICON_BUTTONS_RU['/report_top_shows_sales']:
        for i, (name, gross, net, _id) in enumerate(results, 1):
            track = ''
            if month is None and year is None:
                ts = first_seen.get(_id)
                if ts:
                    date_str = format_timestamp_to_date(ts, include_year=True)
                    track = LEXICON_RU['TRACKING_SINCE'].format(date=date_str)
            response_lines.append(
                LEXICON_RU['TOP_SHOWS_SALES_LINE'].format(
                    index=i,
                    name=escape(str(name)),
                    gross=gross,
                    net=net,
                    tracking=track,
                )
            )
    elif report_type_key == LEXICON_BUTTONS_RU['/report_top_artists_sales']:
        for i, (artist, sold) in enumerate(results, 1):
            track = ''
            if month is None and year is None:
                ts = artist_first_seen.get(artist)
                if ts:
                    date_str = format_timestamp_to_date(ts, include_year=True)
                    track = LEXICON_RU['TRACKING_SINCE'].format(date=date_str)
            response_lines.append(
                LEXICON_RU['TOP_ARTISTS_SALES_LINE'].format(
                    index=i, name=escape(str(artist)), sold=sold
                )
                + track
            )
    elif report_type_key == LEXICON_BUTTONS_RU['/report_top_shows_speed']:
        show_status_map = report_data.show_status

        for i, (name, rate_sec, _id) in enumerate(results, 1):
            rate_day = rate_sec * 60 * 60 * 24

            # Определяем статус спектакля
            is_past = show_status_map.get(_id, False)
            status = (
                LEXICON_RU['SHOW_STATUS_PAST']
                if is_past
                else LEXICON_RU['SHOW_STATUS_CURRENT']
            )

            response_lines.append(
                LEXICON_RU['TOP_SHOWS_SPEED_LINE'].format(
                    index=i,
                    name=escape(str(name)),
                    status=status,
                    speed=rate_day,
                    unit=LEXICON_RU['SALES_SPEED_UNIT_PER_DAY'],
                )
            )
    # Добавляем форматирование для новых отчётов
    elif report_type_key == LEXICON_BUTTONS_RU['/report_top_shows_returns']:
        for i, (name, returns, _id) in enumerate(results, 1):
            track = ''
            if month is None and year is None:
                ts = first_seen.get(_id)
                if ts:
                    date_str = format_timestamp_to_date(ts, include_year=True)
                    track = LEXICON_RU['TRACKING_SINCE'].format(date=date_str)
            response_lines.append(
                LEXICON_RU['TOP_SHOWS_RETURNS_LINE'].format(
                    index=i, name=escape(str(name)), returns=returns
                )
                + track
            )
    elif (
        report_type_key == LEXICON_BUTTONS_RU['/report_top_shows_return_rate']
    ):
        for i, (name, rate, _id) in enumerate(results, 1):
            # Форматируем процент с одним знаком после запятой
            percent = rate * 100
            track = ''
            if month is None and year is None:
                ts = first_seen.get(_id)
                if ts:
                    date_str = format_timestamp_to_date(ts, include_year=True)
                    track = LEXICON_RU['TRACKING_SINCE'].format(date=date_str)
            response_lines.append(
                LEXICON_RU['TOP_SHOWS_RETURN_RATE_LINE'].format(
                    index=i, name=escape(str(name)), percent=percent
                )
                + track
            )
    elif report_type_key == LEXICON_BUTTONS_RU['/report_calendar_pace']:
        # Календарный дашборд возвращает словарь, а не список
        dates = results.get('dates', [])
        gross_sales = results.get('gross_sales', [])
        net_sales = results.get('net_sales', [])
        refunds = results.get('refunds', [])
        show_names = results.get('show_names', [])

        # Limit the displayed dates while retaining totals for the full period.
        MAX_DATES_TO_SHOW = 15

        # Показываем данные по датам
        for i, date in enumerate(dates[:MAX_DATES_TO_SHOW]):
            gross = gross_sales[i] if i < len(gross_sales) else 0
            net = net_sales[i] if i < len(net_sales) else 0
            refund = refunds[i] if i < len(refunds) else 0
            shows = show_names[i] if i < len(show_names) else []

            # Display the first three names with the remaining count.
            shows_text = ', '.join(escape(str(name)) for name in shows[:3])
            if len(shows) > 3:
                shows_text += f' и ещё {len(shows) - 3}...'

            response_lines.append(
                LEXICON_RU['CALENDAR_PACE_DATE_LINE'].format(
                    date=escape(str(date)),
                    gross=gross,
                    net=net,
                    refunds=refund,
                    shows=shows_text,
                )
            )

        if len(dates) > MAX_DATES_TO_SHOW:
            response_lines.append(
                f'\n<i>Показаны первые '
                f'{MAX_DATES_TO_SHOW} дат из {len(dates)}</i>'
            )

        # Добавляем сводку
        if dates:
            total_gross = sum(gross_sales)
            total_net = sum(net_sales)
            total_refunds = sum(refunds)
            avg_gross = total_gross / len(dates) if dates else 0

            response_lines.append(
                LEXICON_RU['CALENDAR_PACE_SUMMARY'].format(
                    total_gross=total_gross,
                    total_net=total_net,
                    total_refunds=total_refunds,
                    avg_gross=avg_gross,
                )
            )

    if len(response_lines) > 1:
        full_text = '\n\n'.join(response_lines)
        await send_chunks_answer(message, full_text)
    else:
        await message.answer(LEXICON_RU['NO_DATA_FOR_REPORT'] + period_text)


@analytics_router.message(
    StateFilter(AnalyticsStates.choosing_month),
    F.text,
    ~F.text.in_(ADMIN_NAVIGATION),
)
async def cmd_generate_soldout_report(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    if not message.text:
        await message.answer(LEXICON_RU['CHOOSE_REPORT_PERIOD'])
        return
    try:
        text = message.text.strip()
        text_parts = text.split()
        if len(text_parts) != 2:
            await message.answer(LEXICON_RU['ERROR_MSG'])
            return
        rus_month_name = text_parts[0]
        year = int(text_parts[1])
        month = RUS_TO_MONTH.get(rus_month_name)
        if not month:
            await message.answer(LEXICON_RU['ERROR_MSG'])
            return
    except Exception:
        await message.answer(LEXICON_RU['ERROR_MSG'])
        return
    await state.clear()
    report_title = REPORTS[LEXICON_BUTTONS_RU['/report_predict_sell_out']][
        'title'
    ]
    period_text = f' (за {text})'

    # Логгирование запроса аналитики
    period = (
        text if text != LEXICON_BUTTONS_RU['/period_all_time'] else 'all time'
    )
    logger.info(
        f'User {message.from_user.full_name} (@{message.from_user.username}, '
        f"id={message.from_user.id}) analytics '{report_title}' for {period}"
    )

    await message.answer(
        LEXICON_RU['WAIT_MSG'], reply_markup=analytics_main_menu_keyboard()
    )

    report_data = await AnalyticsRepository(session).report(
        'prediction', month, year, n=10
    )
    results = report_data.results

    if not results:
        await message.answer(LEXICON_RU['NO_DATA_FOR_REPORT'] + period_text)
        return

    response_lines = [f'{report_title}{period_text}:']
    for i, (name, ts, _id, show_date) in enumerate(results, 1):
        date_str = format_timestamp_to_date(ts, include_year=True)
        response_lines.append(
            LEXICON_RU['PREDICT_SELL_OUT_LINE'].format(
                index=i,
                name=escape(str(name)),
                show_date=escape(str(show_date)),
                date=date_str,
            )
        )
    await send_chunks_answer(message, '\n\n'.join(response_lines))


@analytics_router.message(
    StateFilter(
        AnalyticsStates.choosing_month_for_top, AnalyticsStates.choosing_month
    ),
    ~F.text.in_(ADMIN_NAVIGATION),
)
async def cmd_invalid_report_period(message: Message) -> None:
    await message.answer(LEXICON_RU['CHOOSE_REPORT_PERIOD'])


# Функция для форматирования timestamp в читаемую дату
def format_timestamp_to_date(timestamp: int, include_year: bool = True) -> str:
    """Return formatted date in Russian."""
    try:
        dt_object = datetime.fromtimestamp(timestamp)
        if DEFAULT_TIMEZONE:
            dt_object = dt_object.astimezone(DEFAULT_TIMEZONE)

        months = {v: k for k, v in MONTHS_GENITIVE_RU.items()}
        month_name = months.get(dt_object.month, '')

        if include_year:
            return f'{dt_object.day} {month_name} {dt_object.year}'
        return f'{dt_object.day} {month_name}'
    except Exception as e:
        logger.error(f'Error formatting timestamp {timestamp}: {e}')
        return f'{timestamp} (ошибка форматирования)'
