import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pytz

from config import settings
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
    month: Optional[int],
    year: Optional[int],
) -> tuple[list[Show], dict[str, list[ShowSeatHistory]]]:
    """Универсальная фильтрация по периоду и формирование buckets"""
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


def get_net_sales_and_returns(
    hist: Sequence[ShowSeatHistory],
) -> tuple[int, int]:
    """Подсчёт продаж и возвратов из истории"""
    if len(hist) < 2:
        return 0, 0

    sorted_hist = sorted(hist, key=lambda r: r.timestamp)
    sold = returned = 0

    for prev, curr in zip(sorted_hist, sorted_hist[1:]):
        diff = prev.seats - curr.seats
        if diff > 0:
            sold += diff
        elif diff < 0:
            returned += -diff

    return sold, returned


def top_shows_by_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, int, str]]:
    """Топ шоу по общим продажам (без учёта возвратов)"""
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

    ordered = sorted(sales_data.values(), key=lambda x: -x['total_sold'])
    return [
        (item['name'], item['total_sold'], item['id']) for item in ordered[:n]
    ]


def calculate_current_sales_rate(
    history: Sequence[ShowSeatHistory], lookback_hours: int = 24
) -> Optional[float]:
    """
    Расчёт текущей скорости продаж с учётом последних N часов
    и взвешиванием по времени (более свежие данные важнее)
    """
    if len(history) < 2:
        return None

    records = sorted(history, key=lambda r: r.timestamp)
    current_ts = records[-1].timestamp
    lookback_seconds = lookback_hours * 3600
    cutoff_ts = current_ts - lookback_seconds

    # Фильтруем записи за последние lookback_hours
    recent_records = [r for r in records if r.timestamp >= cutoff_ts]
    if len(recent_records) < 2:
        return None

    rates = []
    weights = []

    for prev, curr in zip(recent_records, recent_records[1:]):
        dt = curr.timestamp - prev.timestamp
        if dt < 300:  # Игнорируем интервалы менее 5 минут
            continue

        # Чистая скорость (с учётом возвратов)
        rate = (prev.seats - curr.seats) / dt

        # Вес на основе давности (экспоненциальное убывание)
        age_hours = (current_ts - curr.timestamp) / 3600
        weight = np.exp(-age_hours / (lookback_hours / 2))

        rates.append(rate)
        weights.append(weight)

    if not rates:
        return None

    # Взвешенное среднее
    return np.average(rates, weights=weights)


def top_shows_by_current_sales_speed(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, float, str]]:
    """Топ шоу по текущей скорости продаж"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )

    speed_data = []

    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 3:  # Нужно минимум 3 записи для адекватной оценки
            continue

        # Используем последние 24 часа для оценки текущей скорости
        current_rate = calculate_current_sales_rate(h_rows, lookback_hours=24)
        if current_rate is not None and current_rate > 0:
            speed_data.append((show.show_name, current_rate, show.id))

    # Сортируем по скорости
    speed_data.sort(key=lambda x: -x[1])
    return speed_data[:n]


def predict_sold_out_advanced(
    history: Sequence[ShowSeatHistory],
    show_dt: Optional[datetime] = None,
    now_ts: Optional[int] = None,
) -> Optional[int]:
    """
    Улучшенное предсказание sold-out с учётом тренда
    и адаптивной оценкой скорости
    """
    if len(history) < 3:
        return None

    records = sorted(history, key=lambda r: r.timestamp)

    if now_ts is None:
        tz = pytz.timezone(
            getattr(settings, 'DEFAULT_TIMEZONE', 'Europe/Moscow')
        )
        now_ts = int(datetime.now(tz).timestamp())

    # Анализируем последние 7 дней или всю историю, если она короче
    lookback_seconds = 7 * 24 * 3600
    cutoff_ts = max(records[0].timestamp, now_ts - lookback_seconds)
    recent_records = [r for r in records if r.timestamp >= cutoff_ts]

    if len(recent_records) < 3:
        recent_records = records[-10:]  # Берём последние 10 записей

    # Собираем временные ряды
    timestamps = []
    seats = []

    for rec in recent_records:
        timestamps.append(rec.timestamp)
        seats.append(rec.seats)

    # Полиномиальная регрессия для учёта тренда
    if len(timestamps) >= 4:
        # Нормализуем время для численной стабильности
        t_min = min(timestamps)
        t_normalized = [(t - t_min) / 3600 for t in timestamps]  # в часах

        # Используем полином 2-й степени
        coeffs = np.polyfit(t_normalized, seats, 2)
        poly = np.poly1d(coeffs)

        # Предсказываем, когда seats = 0
        # Решаем квадратное уравнение ax² + bx + c = 0
        a, b, c = coeffs
        discriminant = b**2 - 4 * a * c

        if discriminant >= 0 and a != 0:
            # Берём положительный корень
            t_sold_out = (-b - np.sqrt(discriminant)) / (2 * a)
            if t_sold_out > t_normalized[-1]:  # Прогноз в будущее
                sold_out_ts = t_min + int(t_sold_out * 3600)

                # Проверки на адекватность
                if show_dt and sold_out_ts > show_dt.timestamp():
                    return None
                if sold_out_ts <= now_ts:
                    return None
                if sold_out_ts > now_ts + 365 * 24 * 3600:  # Более года
                    return None

                return sold_out_ts

    # Fallback: линейная экстраполяция по последним точкам
    if len(recent_records) >= 2:
        last_rec = recent_records[-1]
        # Средняя скорость за последние записи
        total_time = recent_records[-1].timestamp - recent_records[0].timestamp
        total_sold = recent_records[0].seats - recent_records[-1].seats

        if total_time > 0 and total_sold > 0:
            avg_rate = total_sold / total_time
            seconds_left = last_rec.seats / avg_rate

            if seconds_left > 0 and seconds_left < 365 * 24 * 3600:
                prediction = last_rec.timestamp + int(seconds_left)
                if show_dt and prediction <= show_dt.timestamp():
                    if prediction > now_ts:
                        return prediction

    return None


def shows_predicted_to_sell_out_soonest(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, int, str, str]]:
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


def parse_show_date(date_str: str) -> Optional[datetime]:
    """Парсинг даты шоу из разных форматов"""
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
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, int, str]]:
    """Топ шоу по количеству возвратов"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
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
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, float, str]]:
    """Топ шоу по проценту возвратов"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )

    show_stats = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue

        sold, returned = get_net_sales_and_returns(h_rows)
        total_transactions = sold + returned

        # Фильтруем шоу с малым количеством транзакций
        if total_transactions < 10:  # Минимальный порог
            continue

        return_rate = (
            returned / total_transactions if total_transactions > 0 else 0
        )

        group_key = getattr(show, 'show_id', None) or show.id
        if group_key not in show_stats:
            show_stats[group_key] = {
                'name': show.show_name,
                'return_rate': return_rate,
                'total_transactions': total_transactions,
                'id': group_key,
            }
        else:
            # Если уже есть, пересчитываем средневзвешенный процент
            existing = show_stats[group_key]
            new_total = existing['total_transactions'] + total_transactions
            new_rate = (
                existing['return_rate'] * existing['total_transactions']
                + return_rate * total_transactions
            ) / new_total
            existing['return_rate'] = new_rate
            existing['total_transactions'] = new_total

    # Сортируем по проценту возвратов
    result = [
        (stats['name'], stats['return_rate'], stats['id'])
        for stats in show_stats.values()
    ]
    result.sort(key=lambda x: -x[1])
    return result[:n]


def top_artists_by_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5,
) -> List[Tuple[str, int]]:
    """Топ артистов по продажам"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year
    )

    show_total_sales = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue

        sold, _ = get_net_sales_and_returns(h_rows)
        if sold > 0:
            show_total_sales[show.id] = sold

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
                    title in actor_lower for title in TITLES_TO_SKIP
                )

                if not is_title:
                    real_actors.append(actor_name)

            # Добавляем продажи только для реальных актеров
            for actor_name in real_actors:
                artist_aggregated_sales[actor_name] += sold_for_this_show

    return sorted(
        artist_aggregated_sales.items(), key=lambda x: (-x[1], x[0])
    )[:n]
