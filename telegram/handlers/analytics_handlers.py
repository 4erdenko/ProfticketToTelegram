import json
import logging
from datetime import datetime

import pytz
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.profticket import analytics
from services.profticket.analytics import TITLES_TO_SKIP
from telegram.db.models import Show, ShowSeatHistory
from telegram.keyboards.analytics_keyboard import (
    RUS_TO_MONTH, analytics_main_menu_keyboard, analytics_months_keyboard,
    analytics_months_with_alltime_keyboard)
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
        'handler': analytics.top_shows_by_sales_detailed,
        'title': LEXICON_RU['TOP_SHOWS_SALES_REPORT_TITLE'],
    },
    LEXICON_BUTTONS_RU['/report_top_shows_speed']: {
        'handler': analytics.top_shows_by_current_sales_speed,
        'title': LEXICON_RU['TOP_SHOWS_SPEED_REPORT_TITLE'],
    },
    LEXICON_BUTTONS_RU['/report_predict_sell_out']: {
        'handler': analytics.shows_predicted_to_sell_out_soonest,
        'title': LEXICON_RU['PREDICT_SELL_OUT_REPORT_TITLE'],
    },
    LEXICON_BUTTONS_RU['/report_top_artists_sales']: {
        'handler': analytics.top_artists_by_sales,
        'title': LEXICON_RU['TOP_ARTISTS_REPORT'],
    },
    LEXICON_BUTTONS_RU['/report_calendar_pace']: {
        'handler': analytics.calendar_pace_dashboard,
        'title': LEXICON_RU['CALENDAR_PACE_REPORT_TITLE'],
    },
    # Добавляем новые отчёты по возвратам
    LEXICON_BUTTONS_RU['/report_top_shows_returns']: {
        'handler': analytics.top_shows_by_returns,
        'title': LEXICON_RU['TOP_SHOWS_RETURNS_REPORT_TITLE'],
    },
    LEXICON_BUTTONS_RU['/report_top_shows_return_rate']: {
        'handler': analytics.top_shows_by_return_rate,
        'title': LEXICON_RU['TOP_SHOWS_RETURN_RATE_REPORT_TITLE'],
    },
}


# --- Navigation Handlers ---
@analytics_router.message(F.text == LEXICON_BUTTONS_RU['/analytics_menu'])
async def cmd_analytics_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        LEXICON_RU['ANALYTICS_MENU_TITLE'],
        reply_markup=analytics_main_menu_keyboard(),
    )


@analytics_router.message(F.text == '/analytics')
async def cmd_analytics_menu_text(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        LEXICON_RU['ANALYTICS_MENU_TITLE'],
        reply_markup=analytics_main_menu_keyboard(),
    )


@analytics_router.message(
    F.text == LEXICON_BUTTONS_RU['/back_to_analytics_menu']
)
async def cmd_back_to_analytics_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        LEXICON_RU['ANALYTICS_MENU_TITLE'],
        reply_markup=analytics_main_menu_keyboard(),
    )


@analytics_router.message(F.text == LEXICON_BUTTONS_RU['/back_to_main_menu'])
async def cmd_back_to_main_menu(
    message: Message, session: AsyncSession, state: FSMContext
):
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
):
    # Получаем все доступные месяцы из базы
    shows = (await session.execute(select(Show))).scalars().all()
    months = sorted(
        set((s.month, s.year) for s in shows if s.month and s.year)
    )
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
):
    # Получаем все доступные месяцы из базы
    shows = (await session.execute(select(Show))).scalars().all()
    months = sorted(
        set((s.month, s.year) for s in shows if s.month and s.year)
    )
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
@analytics_router.message(StateFilter(AnalyticsStates.choosing_month_for_top))
async def cmd_generate_top_report_month(
    message: Message, session: AsyncSession, state: FSMContext
):
    user_data = await state.get_data()
    text = message.text.strip()
    await state.clear()
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
    analytics_func = REPORTS[report_type_key]['handler']
    report_title = REPORTS[report_type_key]['title']

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
    all_shows = (await session.execute(select(Show))).scalars().all()
    all_histories = (
        (await session.execute(select(ShowSeatHistory))).scalars().all()
    )
    if not all_shows or not all_histories:
        await message.answer(LEXICON_RU['NO_DATA_FOR_REPORT'])
        return

    if month is None and year is None:
        results = analytics_func(
            shows=all_shows,
            histories=all_histories,
            month=month,
            year=year,
            n=10,
            include_past_shows=True,
        )
    elif report_type_key == LEXICON_BUTTONS_RU['/report_top_shows_speed']:
        # Скорость продаж - всегда включаем прошедшие для анализа
        results = analytics_func(
            shows=all_shows,
            histories=all_histories,
            month=month,
            year=year,
            n=10,
            include_past_shows=True,
        )
    else:
        # Конкретный период - только активные спектакли
        results = analytics_func(
            shows=all_shows,
            histories=all_histories,
            month=month,
            year=year,
            n=10,
        )

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

    event_to_group = {
        s.id: getattr(s, 'show_id', None) or s.id for s in all_shows
    }
    first_seen: dict[str, int] = {}
    for h in all_histories:
        gkey = event_to_group.get(h.show_id)
        if not gkey:
            continue
        ts = first_seen.get(gkey)
        first_seen[gkey] = (
            h.timestamp if ts is None or h.timestamp < ts else ts
        )

    artist_first_seen: dict[str, int] = {}
    if month is None and year is None:
        titles_to_skip = TITLES_TO_SKIP
        for show in all_shows:
            gkey = getattr(show, 'show_id', None) or show.id
            ts = first_seen.get(gkey)
            if ts is None:
                continue
            try:
                actors_list = json.loads(show.actors) if show.actors else []
                if not isinstance(actors_list, list):
                    actors_list = []
            except json.JSONDecodeError:
                actors_list = []
            for actor in actors_list:
                if not isinstance(actor, str) or not actor.strip():
                    continue
                name = actor.strip()
                lower = name.lower()
                if any(title in lower for title in titles_to_skip):
                    continue
                prev = artist_first_seen.get(name)
                if prev is None or ts < prev:
                    artist_first_seen[name] = ts

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
                    index=i, name=name, gross=gross, net=net, tracking=track
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
                    index=i, name=artist, sold=sold
                )
                + track
            )
    elif report_type_key == LEXICON_BUTTONS_RU['/report_top_shows_speed']:
        # Создаем маппинг show_id -> is_deleted для определения статуса
        show_status_map = {}
        for show in all_shows:
            group_key = getattr(show, 'show_id', None) or show.id
            is_deleted = getattr(show, 'is_deleted', False)
            show_status_map[group_key] = is_deleted

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
                    name=name,
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
                    index=i, name=name, returns=returns
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
                    index=i, name=name, percent=percent
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

        # Ограничиваем количество дат для отображения
        MAX_DATES_TO_SHOW = 15  # Показываем максимум 15 дат

        # Показываем данные по датам
        for i, date in enumerate(dates[:MAX_DATES_TO_SHOW]):
            gross = gross_sales[i] if i < len(gross_sales) else 0
            net = net_sales[i] if i < len(net_sales) else 0
            refund = refunds[i] if i < len(refunds) else 0
            shows = show_names[i] if i < len(show_names) else []

            # Форматируем список спектаклей
            shows_text = ', '.join(shows[:3])  # Показываем первые 3
            if len(shows) > 3:
                shows_text += f' и ещё {len(shows) - 3}...'

            response_lines.append(
                LEXICON_RU['CALENDAR_PACE_DATE_LINE'].format(
                    date=date,
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


@analytics_router.message(StateFilter(AnalyticsStates.choosing_month))
async def cmd_generate_soldout_report(
    message: Message, session: AsyncSession, state: FSMContext
):
    await state.clear()
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
    analytics_func = REPORTS[LEXICON_BUTTONS_RU['/report_predict_sell_out']][
        'handler'
    ]
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

    all_shows = (await session.execute(select(Show))).scalars().all()
    all_histories = (
        (await session.execute(select(ShowSeatHistory))).scalars().all()
    )

    if not all_shows or not all_histories:
        await message.answer(LEXICON_RU['NO_DATA_FOR_REPORT'])
        return

    results = analytics_func(
        shows=all_shows, histories=all_histories, month=month, year=year, n=10
    )

    if not results:
        await message.answer(LEXICON_RU['NO_DATA_FOR_REPORT'] + period_text)
        return

    response_lines = [f'{report_title}{period_text}:']
    for i, (name, ts, _id, show_date) in enumerate(results, 1):
        date_str = format_timestamp_to_date(ts, include_year=True)
        response_lines.append(
            LEXICON_RU['PREDICT_SELL_OUT_LINE'].format(
                index=i, name=name, show_date=show_date, date=date_str
            )
        )
    await message.answer('\n\n'.join(response_lines))


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
