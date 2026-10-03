"""User-facing descriptions of observed inventory changes."""

from datetime import datetime
from typing import TYPE_CHECKING

import pytz

from config import settings
from services.profticket.analytics import parse_show_date

if TYPE_CHECKING:
    from services.profticket.insights import InventoryInsights

TREND_LABELS = {
    'depleting': 'Билетов становится меньше.',
    'replenishing': 'Билетов становится больше.',
    'stable': 'Число билетов почти не меняется.',
    'accelerating': 'Билеты уходят быстрее, чем вчера.',
    'slowing': 'Билеты уходят медленнее, чем вчера.',
    'unknown': 'Сравнить со вчера пока не получается.',
}

FORECAST_REASONS = {
    'no_observations': 'пока мало данных о билетах',
    'unknown_inventory': 'неизвестно, сколько билетов осталось',
    'insufficient_history': 'нужно собрать данные хотя бы за сутки',
    'stale_data': 'данные давно не обновлялись',
    'long_gap': 'бот долго не получал свежие данные',
    'inventory_jump': 'число билетов резко изменилось',
    'no_depletion': 'билетов не становится меньше',
    'volatile_rate': 'билеты уходят слишком неравномерно',
    'forecast_beyond_horizon': 'надёжно оценить дату пока не получается',
    'past_event': 'спектакль уже прошёл',
    'invalid_event_date': 'дата спектакля неизвестна',
    'ok': 'пока мало данных',
}

INVENTORY_EXPLANATION = (
    'Число билетов на сайте меняется не только из-за продаж.'
)


def inventory_date(timestamp: int) -> str:
    timezone = pytz.timezone(settings.DEFAULT_TIMEZONE)
    return datetime.fromtimestamp(timestamp, timezone).strftime(
        '%d.%m.%Y в %H:%M'
    )


def performance_date(value: str | None) -> str:
    """Format supported event dates consistently while preserving fallbacks."""
    parsed = parse_show_date(value)
    if parsed is None:
        return value or 'Дата уточняется'
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(pytz.timezone(settings.DEFAULT_TIMEZONE))
    return parsed.strftime('%d.%m.%Y в %H:%M')


def inventory_number(value: int | float) -> str:
    """Format display quantities using Russian decimal notation."""
    return (
        f'{value:,.2f}'.rstrip('0')
        .rstrip('.')
        .replace(',', '\u00a0')
        .replace('.', ',')
    )


def net_inventory_change(value: int) -> str:
    """Describe a signed depletion without exposing the sign convention."""
    if value == 0:
        return 'без изменений'
    direction = 'меньше' if value > 0 else 'больше'
    return f'на <b>{inventory_number(abs(value))}</b> {direction}'


def format_inventory_insights(
    insights: InventoryInsights, *, include_counts: bool = True
) -> str:
    """Describe pace and scenarios without implying order-level evidence."""
    lines = []
    if insights.forecast_at is not None:
        earliest, latest = insights.forecast_earliest, insights.forecast_latest
        if earliest is not None and latest is not None and earliest != latest:
            lines.append(
                '⏳ Билеты могут закончиться примерно\n'
                f'<b>{inventory_date(earliest)} — {inventory_date(latest)}</b>,\n'
                'если будут уходить так же.'
            )
        else:
            lines.append(
                '⏳ Билеты могут закончиться примерно '
                f'<b>{inventory_date(insights.forecast_at)}</b>,\n'
                'если будут уходить так же.'
            )
    elif insights.reason == 'no_depletion' and insights.latest_seats == 0:
        lines.append('🎟 Сейчас билетов на сайте нет.')
    else:
        lines.append(
            f'Пока без прогноза: {FORECAST_REASONS[insights.reason]}.'
        )
    if include_counts and insights.reason not in (
        'no_observations',
        'unknown_inventory',
        'stale_data',
    ):
        lines.append(
            f'За сутки: меньше на <b>{inventory_number(insights.decreases)}</b>, '
            f'больше на <b>{inventory_number(insights.increases)}</b>.'
        )
    rate = insights.net_rate_per_day
    if rate is not None and rate != 0:
        direction = 'меньше' if rate > 0 else 'больше'
        lines.append(
            f'В среднем за день: на '
            f'<b>{inventory_number(round(abs(rate), 1))}</b> {direction}.'
        )
    if insights.trend in ('accelerating', 'slowing', 'stable'):
        lines.append(TREND_LABELS[insights.trend])
    return '\n'.join(lines)
