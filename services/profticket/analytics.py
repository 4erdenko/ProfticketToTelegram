import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

import pytz

from config import settings
from telegram.db.models import Show, ShowSeatHistory


# Универсальная фильтрация по периоду и формирование buckets
def filter_data_by_period(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int],
    year: Optional[int],
) -> tuple[list[Show], dict[str, list[ShowSeatHistory]]]:
    if month is not None and year is not None:
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
        filtered_shows = list(shows)
        filtered_ids = {s.id for s in filtered_shows}
        filtered_histories = [
            h for h in histories if h.show_id in filtered_ids
        ]
    buckets = defaultdict(list)
    for h in filtered_histories:
        buckets[h.show_id].append(h)
    return filtered_shows, buckets


def check_data_exists(shows, histories):
    return bool(shows) and bool(histories)


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


def parse_show_date(date_str: str) -> Optional[datetime]:
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


# Helper to get Show object by ID
def _get_show_details(show_id: str, shows: Sequence[Show]) -> Optional[Show]:
    for s in shows:
        if s.id == show_id:
            return s
    return None


def _calculate_real_sales_from_history(
    history_for_show: Sequence[ShowSeatHistory],
) -> int:
    """
    Calculate actual ticket sales accounting for returns.
    Instead of just using first-last difference, this adds up
    all actual sales intervals (where seats decrease) separately.
    """
    if not history_for_show or len(history_for_show) < 2:
        return 0

    records = sorted(history_for_show, key=lambda r: r.timestamp)
    total_sales = 0

    for prev, curr in zip(records, records[1:]):
        # Seats decreased = tickets were sold
        if curr.seats < prev.seats:
            total_sales += prev.seats - curr.seats

    return total_sales


# Helper to calculate sales from history for a single show
def _calculate_show_sales_from_history(
    history_for_show: Sequence[ShowSeatHistory],
) -> int:
    if not history_for_show or len(history_for_show) < 2:
        return 0
    records = sorted(history_for_show, key=lambda r: r.timestamp)
    sold = records[0].seats - records[-1].seats
    return sold if sold > 0 else 0


def get_net_sales_and_returns(hist):
    sold = returned = 0
    for prev, curr in zip(hist, hist[1:]):
        diff = prev.seats - curr.seats
        if diff > 0:
            sold += diff
        elif diff < 0:
            returned += -diff
    return sold, returned


def predict_sold_out(
    history: Sequence[ShowSeatHistory],
    show_dt: Optional[datetime] = None,
    now_ts: Optional[int] = None,
) -> Optional[int]:
    if len(history) < 2:
        return None

    recs = sorted(history, key=lambda r: r.timestamp)

    if now_ts is None:
        tz = pytz.timezone(
            getattr(settings, "DEFAULT_TIMEZONE", "Europe/Moscow")
        )
        now_ts = int(datetime.now(tz).timestamp())

    # --- Окно последних 24 часов ---
    WINDOW_HOURS = 24
    window_start = recs[-1].timestamp - WINDOW_HOURS * 3600
    recs = [r for r in recs if r.timestamp >= window_start]
    if len(recs) < 3:
        return None

    MIN_INTERVAL = 30 * 60  # 30 мин
    rates = []
    for prev, curr in zip(recs, recs[1:]):
        dt = curr.timestamp - prev.timestamp
        if dt < MIN_INTERVAL:
            continue
        rate = (
            prev.seats - curr.seats
        ) / dt  # net-rate (возвраты отрицательны)
        rates.append(rate)

    pos_rates = [r for r in rates if r > 0]
    if len(pos_rates) < 3:
        return None

    pos_rates.sort()
    m = len(pos_rates)
    avg_rate = (
        pos_rates[m // 2]
        if m % 2
        else (pos_rates[m // 2 - 1] + pos_rates[m // 2]) / 2
    )
    if avg_rate <= 0:
        return None

    last = recs[-1]
    seconds_left = last.seats / avg_rate
    if seconds_left > 365 * 24 * 3600:
        return None

    prediction = last.timestamp + int(seconds_left)
    # финальная проверка: sold-out раньше показа?
    if show_dt and prediction > show_dt.timestamp():
        return None

    if prediction <= now_ts:
        return None

    return prediction


def top_shows_by_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, int, str]]:
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )
    sales_data = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        sold, returned = get_net_sales_and_returns(h_rows)
        net_sales = sold - returned
        if net_sales > 0:
            group_key = getattr(show, 'show_id', None) or show.id
            if group_key not in sales_data:
                sales_data[group_key] = {
                    'name': show.show_name,
                    'total_sold': 0,
                    'id': group_key,
                }
            sales_data[group_key]['total_sold'] += net_sales
    ordered = sorted(sales_data.values(), key=lambda x: -x['total_sold'])
    result = []
    for item in ordered[:n]:
        result.append((item['name'], item['total_sold'], item['id']))
    return result


def top_artists_by_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, int]]:
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )
    show_total_sales = defaultdict(int)
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        sold, returned = get_net_sales_and_returns(h_rows)
        net = sold - returned
        if net > 0:
            show_total_sales[show.id] = net

    # Список титулов, которые нужно пропустить или объединить
    titles_to_merge = [
        'народный артист россии',
        'народная артистка россии',
        'заслуженный артист россии',
        'заслуженная артистка россии',
        'лауреат государственных премий',
        'заслуженный деятель искусств',
        'лауреат премии',
    ]

    artist_aggregated_sales = defaultdict(int)

    for show in filtered_shows:
        sold_for_this_show = show_total_sales.get(show.id, 0)
        if sold_for_this_show > 0:
            try:
                actors_list = json.loads(show.actors) if show.actors else []
                if not isinstance(actors_list, list):
                    actors_list = []
            except json.JSONDecodeError:
                actors_list = []

            # Отфильтровываем только реальных актеров, исключая титулы
            real_actors = []
            for actor in actors_list:
                if not isinstance(actor, str) or not actor.strip():
                    continue

                actor_name = actor.strip()
                actor_lower = actor_name.lower()

                # Проверяем, не является ли строка титулом
                is_title = any(
                    title in actor_lower for title in titles_to_merge
                )

                # Добавляем только реальные имена актеров, пропускаем титулы
                if not is_title:
                    real_actors.append(actor_name)

            # Добавляем продажи только для реальных актеров
            for actor_name in real_actors:
                artist_aggregated_sales[actor_name] += sold_for_this_show

    return sorted(
        artist_aggregated_sales.items(), key=lambda x: (-x[1], x[0])
    )[:n]


def calculate_average_sales_rate_for_show(
    history_for_show: Sequence[ShowSeatHistory],
) -> Optional[float]:
    """
    Рассчитывает среднюю скорость продаж билетов в билетах/секунду.
    Улучшенная версия с фильтрацией выбросов
    и минимальным временным интервалом.
    """
    if len(history_for_show) < 2:
        return None

    records = sorted(history_for_show, key=lambda r: r.timestamp)

    MIN_INTERVAL_SECONDS = 30 * 60

    rates = []

    for prev, curr in zip(records, records[1:]):
        dt = curr.timestamp - prev.timestamp
        ds = prev.seats - curr.seats

        # Учитываем только положительные продажи
        if dt <= 0 or ds <= 0:
            continue

        # Игнорируем слишком короткие интервалы
        if dt < MIN_INTERVAL_SECONDS:
            continue

        # Рассчитываем скорость продаж в этом интервале (билетов/секунду)
        rate = ds / dt

        rates.append(rate)

    if not rates:
        return None

    # Используем медиану вместо среднего для уменьшения влияния выбросов
    rates.sort()
    n = len(rates)
    if n % 2 == 0:
        # Четное количество элементов: средняя из двух средних значений
        return (rates[n // 2 - 1] + rates[n // 2]) / 2
    else:
        # Нечетное количество элементов: середина
        return rates[n // 2]


def top_shows_by_current_sales_speed(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, float, str]]:
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )
    speed_by_key = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        records = sorted(h_rows, key=lambda r: r.timestamp)
        MIN_INTERVAL_SECONDS = 30 * 60
        rates = []
        for prev, curr in zip(records, records[1:]):
            dt = curr.timestamp - prev.timestamp
            ds = prev.seats - curr.seats
            if dt <= 0:
                continue
            if dt < MIN_INTERVAL_SECONDS:
                continue
            rate = ds / dt  # net-скорость, со знаком
            rates.append(rate)
        valid_rates = [r for r in rates if r > 0]
        if len(valid_rates) < 3:
            continue
        valid_rates.sort()
        n_rates = len(valid_rates)
        if n_rates % 2 == 0:
            median = (
                valid_rates[n_rates // 2 - 1] + valid_rates[n_rates // 2]
            ) / 2
        else:
            median = valid_rates[n_rates // 2]
        key = (show.show_name, show.id)
        speed_by_key[key] = (median, show.id, show.show_name)
    ordered = sorted(speed_by_key.values(), key=lambda x: -x[0])
    result = []
    for median, show_id, show_name in ordered[:n]:
        result.append((show_name, median, show_id))
    return result


def shows_predicted_to_sell_out_soonest(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, int, str, str]]:
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
    result = []
    for show in filtered_shows:
        show_dt = parse_show_date(show.date)
        if show_dt is None:
            continue
        if show_dt.tzinfo is None:
            show_dt = timezone.localize(show_dt)
        if show_dt < now:
            continue
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        prediction_ts = predict_sold_out(h_rows, show_dt, now_ts)
        if prediction_ts:
            result.append((show.show_name, prediction_ts, show.id, show.date))
    result.sort(key=lambda x: x[1])
    return result[:n]


# Helper to calculate ticket returns from history for a single show
def _calculate_returns_from_history(
    history_for_show: Sequence[ShowSeatHistory],
) -> int:
    """
    Calculate number of ticket returns.
    Adds up all seats increases between consecutive records.
    """
    if not history_for_show or len(history_for_show) < 2:
        return 0

    records = sorted(history_for_show, key=lambda r: r.timestamp)
    total_returns = 0

    for prev, curr in zip(records, records[1:]):
        # Seats increased = tickets were returned
        if curr.seats > prev.seats:
            total_returns += curr.seats - prev.seats

    return total_returns


def top_shows_by_returns(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, int, str]]:
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )
    returns_data = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        sold, returned = get_net_sales_and_returns(h_rows)
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
    result = []
    for item in ordered[:n]:
        result.append((item['name'], item['total_returns'], item['id']))
    return result


def top_shows_by_return_rate(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, float, str]]:
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )
    show_stats = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        sold, returned = get_net_sales_and_returns(h_rows)
        total = sold + returned
        if total == 0:
            continue
        group_key = getattr(show, 'show_id', None) or show.id
        show_stats[group_key] = (returned, total, group_key, show.show_name)
    result = []
    for key, (returned, total, show_id, show_name) in show_stats.items():
        return_rate = returned / total
        result.append((show_name, return_rate, show_id))
    result.sort(key=lambda x: -x[1])
    return result[:n]
