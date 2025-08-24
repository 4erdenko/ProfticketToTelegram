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
from collections.abc import Sequence
from datetime import datetime

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
    """Подсчёт продаж и возвратов из истории"""
    if len(hist) < 2:
        return 0, 0

    sorted_hist = sorted(hist, key=lambda r: r.timestamp)
    sold = returned = 0

    for prev, curr in zip(sorted_hist, sorted_hist[1:], strict=False):
        diff = prev.seats - curr.seats
        if diff > 0:
            sold += diff
        elif diff < 0:
            returned += -diff

    return sold, returned


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
    """
    Устойчивый расчёт текущей скорости продаж:
    - Окно lookback_hours (по умолчанию 24 часа)
    - Игнорируем интервалы короче MIN_DT (15 мин)
    - Для достаточного числа точек (>= 7) используем линейную регрессию
    seats(t)
      с одноразовым клиппингом выбросов по остаткам;
      иначе — EWMA по интервалам.

    Возвращает билетов/секунду (умножить на 3600 для билетов/час,
    на 86400 для билетов/день).
    """
    if len(history) < 2:
        return None

    MIN_DT = 900  # 15 минут — минимальный шаг между соседними точками

    records = sorted(history, key=lambda r: r.timestamp)
    current_ts = records[-1].timestamp
    lookback_seconds = lookback_hours * 3600
    cutoff_ts = current_ts - lookback_seconds

    # Фильтруем записи за последние lookback_hours
    recent_records = [r for r in records if r.timestamp >= cutoff_ts]
    if len(recent_records) < 2:
        return None

    # Оставляем только точки с шагом >= MIN_DT
    filtered: list[ShowSeatHistory] = []
    for rec in recent_records:
        if not filtered:
            filtered.append(rec)
            continue
        if rec.timestamp - filtered[-1].timestamp >= MIN_DT:
            filtered.append(rec)

    if len(filtered) < 2:
        return None

    # Если точек >= 7 (интервалов >= 6): линейная регрессия ( seats = a*t + b )
    # Примечание: t в часах для численной стабильности; rate_sec = -a/3600
    if len(filtered) >= 7:
        t0 = filtered[0].timestamp
        t_hours = np.array(
            [(r.timestamp - t0) / 3600 for r in filtered], dtype=float
        )
        y_seats = np.array([r.seats for r in filtered], dtype=float)

        # Первичная оценка
        a1, b1 = np.polyfit(t_hours, y_seats, 1)
        resid = y_seats - (a1 * t_hours + b1)
        med = np.median(resid)
        mad = np.median(np.abs(resid - med)) if np.any(resid) else 0.0

        # Порог клиппинга: 3*MAD (или 2*STD при MAD==0)
        if mad > 0:
            thr = 3.0 * mad
        else:
            std = np.std(resid)
            thr = 2.0 * std

        if thr > 0:
            mask = np.abs(resid - med) <= thr
            if mask.sum() >= 2:
                a2, b2 = np.polyfit(t_hours[mask], y_seats[mask], 1)
                slope = a2
            else:
                slope = a1
        else:
            slope = a1

        rate_sec = max(0.0, -slope / 3600.0)
        return rate_sec if rate_sec > 0 else None

    # Иначе — EWMA по интервалам (как раньше), но с MIN_DT=15 мин
    rates: list[float] = []
    weights: list[float] = []
    for prev, curr in zip(filtered, filtered[1:], strict=False):
        dt = curr.timestamp - prev.timestamp
        if dt < MIN_DT:
            continue
        rate = (prev.seats - curr.seats) / dt
        age_hours = (current_ts - curr.timestamp) / 3600
        weight = np.exp(-age_hours / (lookback_hours / 2))
        rates.append(rate)
        weights.append(weight)

    if not rates:
        return None
    return float(np.average(rates, weights=weights))


def _count_valid_intervals(
    history: Sequence[ShowSeatHistory],
    lookback_hours: int = 24,
    min_dt: int = 900,
) -> int:
    if len(history) < 2:
        return 0
    records = sorted(history, key=lambda r: r.timestamp)
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
        if len(h_rows) < 3:  # Нужно минимум 3 записи для адекватной оценки
            continue

        # Используем последние 24 часа для оценки текущей скорости
        current_rate = calculate_current_sales_rate(h_rows, lookback_hours=24)
        if current_rate is not None and current_rate > 0:
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
        speed_data.append((name, rate, gid))
    speed_data.sort(key=lambda x: -x[1])
    return speed_data[:n]


def predict_sold_out_advanced(
    history: Sequence[ShowSeatHistory],
    show_dt: datetime | None = None,
    now_ts: int | None = None,
) -> int | None:
    """
    Улучшенное предсказание sold-out с учётом тренда
    и адаптивной оценкой скорости
    """
    # Требуем минимум 4 точки (>= 3 интервалов)
    if len(history) < 4:
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

    # Отфильтровываем слишком короткие интервалы (<5 минут) — шум
    MIN_DT = 300  # 5 минут
    filtered: list[ShowSeatHistory] = []
    for rec in recent_records:
        if not filtered:
            filtered.append(rec)
            continue
        if rec.timestamp - filtered[-1].timestamp >= MIN_DT:
            filtered.append(rec)

    # Если после фильтрации точек меньше 4, попробуем взять хвост истории
    # с требованием соблюдения минимального шага
    if len(filtered) < 4:
        tail_filtered: list[ShowSeatHistory] = []
        for rec in records[-10:]:  # ограничим хвост десятью записями
            if not tail_filtered:
                tail_filtered.append(rec)
                continue
            if rec.timestamp - tail_filtered[-1].timestamp >= MIN_DT:
                tail_filtered.append(rec)
        filtered = tail_filtered

    # Требуем минимум 4 точки (>=3 интервала) после фильтрации
    if len(filtered) < 4:
        return None

    # Собираем временные ряды
    timestamps = []
    seats = []

    for rec in filtered:
        timestamps.append(rec.timestamp)
        seats.append(rec.seats)

    # Полиномиальная регрессия для учёта тренда
    if len(timestamps) >= 4:
        # Нормализуем время для численной стабильности
        t_min = min(timestamps)
        t_normalized = [(t - t_min) / 3600 for t in timestamps]  # в часах

        # Используем полином 2-й степени
        coeffs = np.polyfit(t_normalized, seats, 2)

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
    if len(filtered) >= 4:
        last_rec = filtered[-1]
        # Средняя скорость по чистому изменению за период
        total_time = filtered[-1].timestamp - filtered[0].timestamp
        total_sold = filtered[0].seats - filtered[-1].seats

        if total_time > 0 and total_sold > 0:
            avg_rate = total_sold / total_time
            seconds_left = last_rec.seats / avg_rate

            if 0 < seconds_left < 365 * 24 * 3600:
                prediction = last_rec.timestamp + int(seconds_left)
                if (
                    show_dt
                    and prediction <= show_dt.timestamp()
                    and prediction > now_ts
                ):
                    return prediction

    return None


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


def parse_show_date(date_str: str) -> datetime | None:
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
) -> list[tuple[str, float, str]]:
    """Топ шоу по проценту возвратов"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year, include_past_shows=include_past_shows
    )

    show_stats = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue

        sold, returned = get_net_sales_and_returns(h_rows)

        # Используем базу по продажам: return-rate = returned / sold
        # Фильтруем шоу с малым количеством продаж
        MIN_SOLD = 10
        if sold < MIN_SOLD:
            continue

        return_rate = returned / sold if sold > 0 else 0.0

        group_key = getattr(show, 'show_id', None) or show.id
        if group_key not in show_stats:
            show_stats[group_key] = {
                'name': show.show_name,
                'return_rate': return_rate,
                'total_sold': sold,
                'id': group_key,
            }
        else:
            # Если уже есть, пересчитываем средневзвешенный процент
            existing = show_stats[group_key]
            new_total = existing['total_sold'] + sold
            new_rate = (
                existing['return_rate'] * existing['total_sold']
                + return_rate * sold
            ) / new_total
            existing['return_rate'] = new_rate
            existing['total_sold'] = new_total

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
    month: int | None = None,
    year: int | None = None,
    n: int = 5,
    include_past_shows: bool = False,
) -> list[tuple[str, int]]:
    """Топ артистов по net продажам (продажи минус возвраты)"""
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year, include_past_shows=include_past_shows
    )

    show_net_sales = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue

        sold, returned = get_net_sales_and_returns(h_rows)
        net_sales = sold - returned
        if net_sales > 0:  # Учитываем только положительные net продажи
            show_net_sales[show.id] = net_sales

    artist_aggregated_sales = defaultdict(int)

    for show in filtered_shows:
        net_sales_for_this_show = show_net_sales.get(show.id, 0)
        if net_sales_for_this_show > 0:
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

            # Добавляем net продажи только для реальных актеров
            for actor_name in real_actors:
                artist_aggregated_sales[actor_name] += net_sales_for_this_show

    return sorted(
        artist_aggregated_sales.items(), key=lambda x: (-x[1], x[0])
    )[:n]


def calendar_pace_dashboard(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: int | None = None,
    year: int | None = None,
    n: int = 10,  # Добавляем для совместимости API (не используется)
    include_past_shows: bool = False,
) -> dict:
    """
    Календарный pace-дашборд с разделением gross/net/refunds
    Возвращает данные для построения кривых спроса

    Args:
        n: параметр для совместимости API
        (не используется, т.к. возвращаем данные по дням)
    """
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year, include_past_shows=include_past_shows
    )

    # Группируем по датам шоу
    date_groups = defaultdict(
        lambda: {
            'shows': [],
            'total_gross': 0,
            'total_net': 0,
            'total_refunds': 0,
            'histories': [],
        }
    )

    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue

        sold, returned = get_net_sales_and_returns(h_rows)
        net_sales_amount = sold - returned  # Чистая сумма продаж без возвратов

        show_date = show.date
        date_groups[show_date]['shows'].append(show.show_name)
        date_groups[show_date]['total_gross'] += sold  # Gross = все продажи
        date_groups[show_date]['total_net'] += (
            net_sales_amount  # Net = продажи - возвраты
        )
        date_groups[show_date]['total_refunds'] += returned
        date_groups[show_date]['histories'].extend(h_rows)

    # Сортируем по дате (распарсиваем строковые даты в datetime)
    # Для неподдающихся парсингу — сортируем по строковому значению после дат
    sortable: list[tuple[int, object, str, dict]] = []
    for date_str, data in date_groups.items():
        dt = parse_show_date(date_str)
        if dt is not None:
            sortable.append((0, dt, date_str, data))
        else:
            sortable.append((1, date_str, date_str, data))

    sorted_dates = [
        (date_str, data) for _, _, date_str, data in sorted(sortable)
    ]

    # Валидация: если нет данных, возвращаем пустую структуру
    if not sorted_dates:
        return {
            'dates': [],
            'gross_sales': [],
            'net_sales': [],
            'refunds': [],
            'show_names': [],
        }

    result = {
        'dates': [],
        'gross_sales': [],
        'net_sales': [],
        'refunds': [],
        'show_names': [],
    }

    for date, data in sorted_dates:
        result['dates'].append(date)
        result['gross_sales'].append(data['total_gross'])
        result['net_sales'].append(data['total_net'])
        result['refunds'].append(data['total_refunds'])
        result['show_names'].append(data['shows'])

    return result


def show_financial_summary(
    show_id: str,
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    n: int = 10,  # Добавляем для совместимости API (не используется)
) -> dict | None:
    """
    Финансовая сводка по конкретному шоу
    Показывает gross/net для бухгалтерии и маркетинга

    Args:
        n: параметр для совместимости API
        (не используется для сводки конкретного шоу)
    """
    # Находим все шоу с данным show_id (исключая удаленные)
    target_shows = [
        s
        for s in shows
        if (getattr(s, 'show_id', None) or s.id) == show_id
        and not getattr(s, 'is_deleted', False)
    ]
    if not target_shows:
        return None

    # Собираем всю историю для этого шоу
    all_histories = []
    total_gross = 0
    total_net = 0
    total_refunds = 0
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
        all_histories.extend(h_rows)

    if total_gross == 0:
        return None

    # Рассчитываем дополнительную аналитику
    refund_rate = total_refunds / total_gross

    # Текущая скорость продаж
    current_sales_rate = None
    if all_histories:
        current_sales_rate = calculate_current_sales_rate(
            all_histories, lookback_hours=24
        )

    return {
        'show_id': show_id,
        'show_names': list(show_names),
        'show_dates': show_dates,
        'gross_sales': total_gross,  # для маркетинга
        'net_sales': total_net,  # для бухгалтерии и royalty
        'total_refunds': total_refunds,
        'refund_rate': round(refund_rate * 100, 2),  # в процентах
        'current_sales_rate_per_hour': round(current_sales_rate * 3600, 2)
        if current_sales_rate
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
) -> list[tuple[str, int, int, str]]:
    """
    Топ шоу по продажам с детализацией gross/net
    Возвращает: (name, gross_sales, net_sales, id)
    """
    filtered_shows, history_buckets = filter_data_by_period(
        shows, histories, month, year, include_past_shows=include_past_shows
    )

    sales_data = {}
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue

        sold, returned = get_net_sales_and_returns(h_rows)
        if sold > 0:
            group_key = getattr(show, 'show_id', None) or show.id
            if group_key not in sales_data:
                sales_data[group_key] = {
                    'name': show.show_name,
                    'total_sold': 0,
                    'total_returned': 0,
                    'id': group_key,
                }
            sales_data[group_key]['total_sold'] += sold
            sales_data[group_key]['total_returned'] += returned

    # Сортируем по gross продажам
    ordered = sorted(sales_data.values(), key=lambda x: -x['total_sold'])

    return [
        (
            item['name'],
            item['total_sold'],  # gross
            item['total_sold'] - item['total_returned'],  # net
            item['id'],
        )
        for item in ordered[:n]
    ]
