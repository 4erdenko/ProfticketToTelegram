"""
Analytics module for ProfTicket data

Этот модуль предоставляет аналитические функции с поддержкой gross/net метрик:

### Где показывать оба числа (gross / net):

1. **Топ спектаклей по продажам** - классический кейс «208 / 194»
(gross выдано / net чистые):
   top_shows_by_sales_detailed(shows, histories)  # Возвращает
   (name, gross, net, id)
   top_shows_by_sales(shows, histories)
   # Обратная совместимость - только gross

2. **Календарный pace-дашборд** - кривая спроса строится по gross, рядом
идёт net и отдельная строчка «refunds»:
   calendar_pace_dashboard(shows, histories, month=5, year=2024)
   # Возвращает: {'gross_sales': [...], 'net_sales': [...],
   'refunds': [...], ...}

3. **Финансовые сводки по конкретным шоу** - отчёт в бухгалтерию и royalty
видит net, маркетинг смотрит gross:
   show_financial_summary(show_id, shows, histories)
   # Возвращает: {'gross_sales': 208, 'net_sales': 194,
   'total_refunds': 14, ...}

### Где обычно достаточно одного значения:

- **Топ артистов** - берут net (чистые билеты, уже без возвратов)
- **Возвраты и return-rate** - само собой показывают только возвраты/процент
- **Заполняемость (occupancy) и прогноз sold-out** -
считают по net-остатку мест
- **Скорость текущих продаж** - используют gross-транзакции,
но выводят одну цифру «билетов/час»

### API совместимость:

- Все существующие функции сохранили свою сигнатуру
для обратной совместимости
- Новые функции с gross/net имеют суффикс `_detailed`
или являются отдельными функциями
"""

import json
import logging
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

import pytz

from config import settings
from services.profticket.insights import analyze_inventory, time_weighted_rate
from telegram.db.models import Show, ShowSeatHistory

# Common list of titles and awards to ignore when processing actors
TITLES_TO_SKIP = [
    'народный артист россии',
    'народная артистка россии',
    'заслуженный артист россии',
    'заслуженная артистка россии',
    'лауреат государственных премий',
    'заслуженный деятель искусств',
    'лауреат премии',
]

MONTHS_RU = {
    'января': 1,
    'февраля': 2,
    'марта': 3,
    'апреля': 4,
    'мая': 5,
    'июня': 6,
    'июля': 7,
    'августа': 8,
    'сентября': 9,
    'октября': 10,
    'ноября': 11,
    'декабря': 12,
}


def filter_data_by_period(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None,
    year: int | None,
    include_past_shows: bool = False,
) -> tuple[list[Show], dict[str, list[ShowSeatHistory]]]:
    """
    Универсальная фильтрация по периоду и формирование buckets

    Args:
        include_past_shows: если True, включает прошедшие
        (is_deleted=True) спектакли.
        Полезно для анализа скорости продаж и исторических данных.
    """
    if month is not None and year is not None:
        if include_past_shows:
            # Включаем все спектакли, даже прошедшие
            filtered_shows = [
                s for s in shows if s.month == month and s.year == year
            ]
        else:
            # Стандартная логика - исключаем прошедшие
            filtered_shows = [
                s
                for s in shows
                if s.month == month
                and s.year == year
                and not getattr(s, 'is_deleted', False)
            ]
        filtered_ids = {s.id for s in filtered_shows}
        filtered_histories = [
            h for h in histories if h.show_id in filtered_ids
        ]
    else:
        if include_past_shows:
            # За все время - включаем все спектакли
            filtered_shows = list(shows)
        else:
            # За все время - исключаем прошедшие
            filtered_shows = [
                s for s in shows if not getattr(s, 'is_deleted', False)
            ]
        filtered_ids = {s.id for s in filtered_shows}
        filtered_histories = [
            h for h in histories if h.show_id in filtered_ids
        ]

    buckets = defaultdict(list)
    for h in filtered_histories:
        buckets[h.show_id].append(h)

    return filtered_shows, buckets


def get_net_sales_and_returns(
    hist: Sequence[ShowSeatHistory],
) -> tuple[int, int]:
    """Count observed sales and returns in deterministic snapshot order."""
    records = sorted(
        (
            row
            for row in hist
            if row.timestamp is not None and row.seats is not None
        ),
        key=lambda row: (row.timestamp, getattr(row, 'id', None) or 0),
    )
    sold = returned = 0
    for previous, current in zip(records, records[1:], strict=False):
        difference = previous.seats - current.seats
        sold += max(difference, 0)
        returned += max(-difference, 0)
    return sold, returned


@dataclass(slots=True)
class PerformanceSales:
    show: Show
    sold: int
    returned: int
    first_seen: int | None = None


def _performance_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None,
    year: int | None,
    include_past_shows: bool,
) -> list[PerformanceSales]:
    selected, buckets = filter_data_by_period(
        shows, histories, month, year, include_past_shows
    )
    result = []
    for show in selected:
        records = [
            row
            for row in buckets.get(show.id, [])
            if row.timestamp is not None and row.seats is not None
        ]
        if len(records) >= 2:
            sold, returned = get_net_sales_and_returns(records)
            result.append(
                PerformanceSales(
                    show,
                    sold,
                    returned,
                    min(row.timestamp for row in records),
                )
            )
    return result


def group_sales(
    performances: Sequence[PerformanceSales],
) -> dict[str | int, PerformanceSales]:
    """Combine all performances before applying report thresholds."""
    groups: dict[str | int, PerformanceSales] = {}
    for item in performances:
        key = getattr(item.show, 'show_id', None) or item.show.id
        if key not in groups:
            groups[key] = PerformanceSales(item.show, 0, 0, item.first_seen)
        group = groups[key]
        group.sold += item.sold
        group.returned += item.returned
        if item.first_seen is not None:
            group.first_seen = min(
                group.first_seen
                if group.first_seen is not None
                else item.first_seen,
                item.first_seen,
            )
    return groups


def real_actors(show: Show) -> list[str]:
    """Return unique names, excluding titles and malformed actor data."""
    try:
        names = json.loads(show.actors) if show.actors else []
    except json.JSONDecodeError, TypeError:
        return []
    if not isinstance(names, list):
        return []
    return sorted(
        {
            name.strip()
            for name in names
            if isinstance(name, str)
            and name.strip()
            and not any(title in name.lower() for title in TITLES_TO_SKIP)
        }
    )


def sales_report(
    performances: Sequence[PerformanceSales],
    n: int = 10,
) -> list[tuple[str, int, int, str | int]]:
    groups = group_sales(performances)
    ordered = sorted(
        groups.items(), key=lambda item: (-item[1].sold, str(item[0]))
    )
    return [
        (item.show.show_name, item.sold, item.sold - item.returned, key)
        for key, item in ordered
        if item.sold > 0
    ][:n]


def returns_report(
    performances: Sequence[PerformanceSales],
    n: int = 10,
) -> list[tuple[str, int, str | int]]:
    groups = group_sales(performances)
    ordered = sorted(
        groups.items(), key=lambda item: (-item[1].returned, str(item[0]))
    )
    return [
        (item.show.show_name, item.returned, key)
        for key, item in ordered
        if item.returned > 0
    ][:n]


def return_rate_report(
    performances: Sequence[PerformanceSales],
    n: int = 10,
) -> list[tuple[str, float, str | int]]:
    result = [
        (item.show.show_name, item.returned / item.sold, key)
        for key, item in group_sales(performances).items()
        if item.sold >= 10
    ]
    return sorted(result, key=lambda item: (-item[1], str(item[2])))[:n]


def artists_report(
    performances: Sequence[PerformanceSales],
    n: int = 10,
) -> list[tuple[str, int]]:
    totals: dict[str, int] = defaultdict(int)
    for item in performances:
        for actor in real_actors(item.show):
            totals[actor] += item.sold - item.returned
    return sorted(
        ((actor, total) for actor, total in totals.items() if total > 0),
        key=lambda item: (-item[1], item[0]),
    )[:n]


def calendar_report(
    performances: Sequence[PerformanceSales],
    n: int = 10,
) -> dict[str, list]:
    groups: dict[str, dict] = {}
    for item in performances:
        date = item.show.date or ''
        group = groups.setdefault(
            date, {'sold': 0, 'returned': 0, 'names': []}
        )
        group['sold'] += item.sold
        group['returned'] += item.returned
        group['names'].append(item.show.show_name)

    def date_key(value: str) -> tuple[int, str]:
        parsed = parse_show_date(value)
        return (0, parsed.isoformat()) if parsed is not None else (1, value)

    result = {
        key: []
        for key in (
            'dates',
            'gross_sales',
            'net_sales',
            'refunds',
            'show_names',
        )
    }
    for date in sorted(groups, key=date_key):
        group = groups[date]
        result['dates'].append(date)
        result['gross_sales'].append(group['sold'])
        result['net_sales'].append(group['sold'] - group['returned'])
        result['refunds'].append(group['returned'])
        result['show_names'].append(group['names'])
    return result


def top_shows_by_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 5,
) -> list[tuple[str, int, str]]:
    """Топ шоу по gross продажам (обратная совместимость)"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )

    sales_data = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue

        sold, _ = get_net_sales_and_returns(h_rows)
        if sold > 0:
            group_key = getattr(show, 'show_id', None) or show.id
            if group_key not in sales_data:
                sales_data[group_key] = {
                    'name': show.show_name,
                    'total_sold': 0,
                    'id': group_key,
                }
            sales_data[group_key]['total_sold'] += sold

    # Сортируем по gross продажам
    ordered = sorted(sales_data.values(), key=lambda x: -x['total_sold'])

    # Возвращаем только gross продажи для обратной совместимости
    return [
        (item['name'], item['total_sold'], item['id']) for item in ordered[:n]
    ]


def calculate_current_sales_rate(
    history: Sequence[ShowSeatHistory], lookback_hours: int = 24
) -> float | None:
    """Return time-weighted net inventory depletion in seats per second."""
    timestamps = [
        row.timestamp
        for row in history
        if row.timestamp is not None
        and row.seats is not None
        and row.seats >= 0
    ]
    if not timestamps:
        return None
    rate = time_weighted_rate(history, max(timestamps), lookback_hours * 3600)
    return rate / 86400 if rate is not None else None


def _count_valid_intervals(
    history: Sequence[ShowSeatHistory],
    lookback_hours: int = 24,
    min_dt: int = 900,
) -> int:
    if len(history) < 2:
        return 0
    records = sorted(
        (
            row
            for row in history
            if row.timestamp is not None and row.seats is not None
        ),
        key=lambda row: (row.timestamp, getattr(row, 'id', None) or 0),
    )
    if len(records) < 2:
        return 0
    current_ts = records[-1].timestamp
    cutoff_ts = current_ts - lookback_hours * 3600
    recent = [r for r in records if r.timestamp >= cutoff_ts]
    if len(recent) < 2:
        return 0
    count = 0
    last = recent[0]
    for rec in recent[1:]:
        dt = rec.timestamp - last.timestamp
        if dt >= min_dt:
            count += 1
            last = rec
    return count


def top_shows_by_current_sales_speed(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 5,
    include_past_shows: bool = True,
    *,
    net_rates_per_day: Mapping[str, float | None] | None = None,
) -> list[tuple[str, float, str]]:
    """
    Топ шоу по текущей скорости продаж

    Показывает одну цифру «билетов/секунду» на основе net скорости
    изменения количества мест (gross активность, net результат).

    Args:
        include_past_shows: если True, включает прошедшие спектакли в анализ.
        Полезно для понимания исторических паттернов скорости продаж.
        :param shows:
        :param histories:
        :param month:
        :param include_past_shows:
        :param n:
        :param year:
    """
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year, include_past_shows=include_past_shows
    )

    # Агрегируем по group_key (show_id или id):
    # считаем средневзвешенную скорость с весом по числу валидных интервалов
    agg_by_group: dict[str, dict[str, float | str]] = {}

    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if net_rates_per_day is None:
            if len(h_rows) < 3:
                continue
            current_rate = calculate_current_sales_rate(
                h_rows, lookback_hours=24
            )
        else:
            daily_rate = net_rates_per_day.get(show.id)
            current_rate = (
                daily_rate / 86400 if daily_rate is not None else None
            )
        if current_rate is not None:
            group_key = getattr(show, 'show_id', None) or show.id
            weight = _count_valid_intervals(
                h_rows, lookback_hours=24, min_dt=900
            )
            if weight <= 0:
                weight = 1
            rec = agg_by_group.get(group_key)
            if rec is None:
                agg_by_group[group_key] = {
                    'name': show.show_name,
                    'rate_sum': current_rate * weight,
                    'w_sum': float(weight),
                }
            else:
                rec['rate_sum'] = (
                    float(rec['rate_sum']) + current_rate * weight
                )
                rec['w_sum'] = float(rec['w_sum']) + float(weight)

    # Сортируем по скорости
    speed_data = []
    for gid, payload in agg_by_group.items():
        name = str(payload['name'])
        rate = float(payload['rate_sum']) / float(payload['w_sum'])
        if rate > 0:
            speed_data.append((name, rate, gid))
    speed_data.sort(key=lambda x: -x[1])
    return speed_data[:n]


def predict_sold_out_advanced(
    history: Sequence[ShowSeatHistory],
    show_dt: datetime | None = None,
    now_ts: int | None = None,
) -> int | None:
    """Return a conditional depletion date supported by observations."""
    if now_ts is None:
        timezone = pytz.timezone(settings.DEFAULT_TIMEZONE)
        now_ts = int(datetime.now(timezone).timestamp())
    return analyze_inventory(history, now_ts, show_dt).forecast_at


def shows_predicted_to_sell_out_soonest(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 5,
) -> list[tuple[str, int, str, str]]:
    """Шоу, которые прогнозируются к sold-out в ближайшее время"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )

    DEFAULT_TZ_STR = getattr(settings, 'DEFAULT_TIMEZONE', 'Europe/Moscow')
    try:
        timezone = pytz.timezone(DEFAULT_TZ_STR)
        now = datetime.now(timezone)
    except Exception:
        timezone = pytz.timezone('Europe/Moscow')
        now = datetime.now(timezone)

    now_ts = int(now.timestamp())
    predictions = []

    for show in filtered_shows:
        show_dt = parse_show_date(show.date)
        if show_dt is None:
            continue

        if show_dt.tzinfo is None:
            show_dt = timezone.localize(show_dt)

        if show_dt < now:
            continue

        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 3:
            continue

        prediction_ts = predict_sold_out_advanced(h_rows, show_dt, now_ts)
        if prediction_ts:
            predictions.append(
                (show.show_name, prediction_ts, show.id, show.date)
            )

    # Сортируем по времени предсказания
    predictions.sort(key=lambda x: x[1])
    return predictions[:n]


def parse_show_date(date_str: str | None) -> datetime | None:
    """Parse current numeric dates and legacy Profticket dates."""
    if date_str is None:
        return None
    try:
        return datetime.strptime(date_str, '%d.%m.%Y, %H:%M')
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(date_str)
    except Exception:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M')
        except Exception:
            # Попробуем русский формат: 20 мая 2025, вт, 20:00
            try:
                match = re.match(
                    r'(\d{1,2}) (\w+) (\d{4}), [^,]+, (\d{2}):(\d{2})',
                    date_str,
                )
                if match:
                    day, month_ru, year, hour, minute = match.groups()
                    month = MONTHS_RU.get(month_ru.lower())
                    if month:
                        return datetime(
                            int(year), month, int(day), int(hour), int(minute)
                        )
            except Exception as e:
                logging.warning(
                    f'parse_show_date: failed to parse "{date_str}": {e}'
                )
            logging.warning(
                f'parse_show_date: failed to parse "{date_str}" (all formats)'
            )
            return None


def top_shows_by_returns(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 5,
    include_past_shows: bool = False,
) -> list[tuple[str, int, str]]:
    """Топ шоу по количеству возвратов"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year, include_past_shows=include_past_shows
    )

    returns_data = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue

        _, returned = get_net_sales_and_returns(h_rows)
        if returned > 0:
            group_key = getattr(show, 'show_id', None) or show.id
            if group_key not in returns_data:
                returns_data[group_key] = {
                    'name': show.show_name,
                    'total_returns': 0,
                    'id': group_key,
                }
            returns_data[group_key]['total_returns'] += returned

    ordered = sorted(returns_data.values(), key=lambda x: -x['total_returns'])
    return [
        (item['name'], item['total_returns'], item['id'])
        for item in ordered[:n]
    ]


def top_shows_by_return_rate(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 5,
    include_past_shows: bool = False,
) -> list[tuple[str, float, str | int]]:
    """Rank grouped performances by returns divided by observed sales."""
    return return_rate_report(
        _performance_sales(
            shows,
            histories,
            month,
            year,
            include_past_shows,
        ),
        n,
    )


def top_artists_by_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 5,
    include_past_shows: bool = False,
) -> list[tuple[str, int]]:
    """Rank artists by net sales across all their performances."""
    return artists_report(
        _performance_sales(
            shows,
            histories,
            month,
            year,
            include_past_shows,
        ),
        n,
    )


def calendar_pace_dashboard(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 10,
    include_past_shows: bool = False,
) -> dict[str, list]:
    """Group observed sales and returns by performance date."""
    return calendar_report(
        _performance_sales(
            shows,
            histories,
            month,
            year,
            include_past_shows,
        ),
        n,
    )


def show_financial_summary(
    show_id: str,
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    n: int = 10,
) -> dict | None:
    """Summarize grouped sales; retain unused n for API compatibility."""
    target_shows = [
        s
        for s in shows
        if (getattr(s, 'show_id', None) or s.id) == show_id
        and not getattr(s, 'is_deleted', False)
    ]
    if not target_shows:
        return None

    total_gross = 0
    total_net = 0
    total_refunds = 0
    rate_sum = 0.0
    rate_weight = 0
    show_dates = []
    show_names = set()

    for show in target_shows:
        h_rows = [h for h in histories if h.show_id == show.id]
        if len(h_rows) < 2:
            continue

        sold, returned = get_net_sales_and_returns(h_rows)
        net_sales = sold - returned

        total_gross += sold
        total_refunds += returned
        total_net += net_sales
        show_dates.append(show.date)
        show_names.add(show.show_name)
        current_rate = calculate_current_sales_rate(h_rows, lookback_hours=24)
        if current_rate is not None:
            weight = max(_count_valid_intervals(h_rows), 1)
            rate_sum += current_rate * weight
            rate_weight += weight

    if total_gross == 0:
        return None

    refund_rate = total_refunds / total_gross
    current_sales_rate = rate_sum / rate_weight if rate_weight else None

    return {
        'show_id': show_id,
        'show_names': list(show_names),
        'show_dates': show_dates,
        'gross_sales': total_gross,
        'net_sales': total_net,
        'total_refunds': total_refunds,
        'refund_rate': round(refund_rate * 100, 2),
        'current_sales_rate_per_hour': round(current_sales_rate * 3600, 2)
        if current_sales_rate is not None
        else None,
        'total_performances': len(target_shows),
    }


def top_shows_by_sales_detailed(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 5,
    include_past_shows: bool = False,
) -> list[tuple[str, int, int, str | int]]:
    """Rank grouped gross sales while including every performance's returns."""
    return sales_report(
        _performance_sales(
            shows,
            histories,
            month,
            year,
            include_past_shows,
        ),
        n,
    )
