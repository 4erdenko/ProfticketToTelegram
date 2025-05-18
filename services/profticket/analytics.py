from statistics import mean
from typing import List, Sequence, Tuple, Optional
import json
from collections import defaultdict
from datetime import datetime
import pytz
from config import settings
from telegram.db.models import Show, ShowSeatHistory

# Универсальная фильтрация по периоду и формирование buckets
def filter_data_by_period(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int],
    year: Optional[int]
) -> tuple[list[Show], dict[str, list[ShowSeatHistory]]]:
    if month is not None and year is not None:
        filtered_shows = [s for s in shows if s.month == month and s.year == year]
    else:
        filtered_shows = list(shows)
    filtered_ids = {s.id for s in filtered_shows}
    filtered_histories = [h for h in histories if h.show_id in filtered_ids]
    buckets = defaultdict(list)
    for h in filtered_histories:
        buckets[h.show_id].append(h)
    return filtered_shows, buckets

# Функция для проверки наличия данных
check_data_exists = lambda shows, histories: bool(shows) and bool(histories)

# Парсер даты спектакля (ожидает формат 'YYYY-MM-DD HH:MM' или ISO)
def parse_show_date(date_str: str) -> Optional[datetime]:
    try:
        # Попробуем ISO
        return datetime.fromisoformat(date_str)
    except Exception:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M')
        except Exception:
            return None

# Helper to get Show object by ID
def _get_show_details(show_id: str, shows: Sequence[Show]) -> Optional[Show]:
    for s in shows:
        if s.id == show_id:
            return s
    return None

# Helper to calculate sales from history for a single show
def _calculate_show_sales_from_history(history_for_show: Sequence[ShowSeatHistory]) -> int:
    if not history_for_show or len(history_for_show) < 2: # Need at least two records to calculate difference
        return 0
    records = sorted(history_for_show, key=lambda r: r.timestamp)
    # Sales = seats at earliest record - seats at latest record for the given period
    sold = records[0].seats - records[-1].seats
    return sold if sold > 0 else 0


def predict_sold_out(history: Sequence[ShowSeatHistory]) -> Optional[int]:
    if len(history) < 2:
        return None
    records = sorted(history, key=lambda r: r.timestamp)
    rates = []
    for prev, curr in zip(records, records[1:]):
        dt = curr.timestamp - prev.timestamp
        ds = prev.seats - curr.seats
        # Возвраты билетов (ds < 0) не учитываем, только продажи
        if dt > 0 and ds > 0:
            rates.append(ds / dt)
    if not rates:
        return None
    avg_rate = mean(rates)
    if avg_rate <= 0:
        return None
    last = records[-1]
    if last.seats <= 0:
        return None
    seconds_left = last.seats / avg_rate
    return last.timestamp + int(seconds_left)


def top_shows_by_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5
) -> List[Tuple[str, int, str]]:
    filtered_shows, history_buckets = filter_data_by_period(shows, histories, month, year)
    # Группируем продажи по названию спектакля
    sales_by_name = defaultdict(int)
    id_by_name = dict()  # Для ссылки на id (берём первый попавшийся)
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        sold_count = h_rows[0].seats - h_rows[-1].seats
        if sold_count > 0:
            sales_by_name[show.show_name] += sold_count
            if show.show_name not in id_by_name:
                id_by_name[show.show_name] = show.id
    ordered = sorted(sales_by_name.items(), key=lambda x: -x[1])
    result = []
    for show_name, sold_count in ordered[:n]:
        show_id = id_by_name.get(show_name, "")
        result.append((show_name, sold_count, show_id))
    return result


def top_artists_by_sales(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5
) -> List[Tuple[str, int]]:
    filtered_shows, history_buckets = filter_data_by_period(shows, histories, month, year)
    show_total_sales = defaultdict(int)
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        sold = h_rows[0].seats - h_rows[-1].seats
        if sold > 0:
            show_total_sales[show.id] = sold
    artist_aggregated_sales = defaultdict(int)
    for show in filtered_shows:
        sold_for_this_show = show_total_sales.get(show.id, 0)
        if sold_for_this_show > 0:
            try:
                actors_list = json.loads(show.actors) if show.actors else []
                if not isinstance(actors_list, list): actors_list = []
            except json.JSONDecodeError:
                actors_list = []
            for actor_name in actors_list:
                if isinstance(actor_name, str) and actor_name.strip():
                    artist_aggregated_sales[actor_name.strip()] += sold_for_this_show
    return sorted(artist_aggregated_sales.items(), key=lambda x: (-x[1], x[0]))[:n]


def calculate_average_sales_rate_for_show(history_for_show: Sequence[ShowSeatHistory]) -> Optional[float]:
    if len(history_for_show) < 2:
        return None
    records = sorted(history_for_show, key=lambda r: r.timestamp)
    rates = []
    for prev, curr in zip(records, records[1:]):
        dt = curr.timestamp - prev.timestamp
        ds = prev.seats - curr.seats
        if dt > 0 and ds > 0:
            rates.append(ds / dt)
    if not rates:
        return None
    return mean(rates) if rates else None


def top_shows_by_current_sales_speed(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5
) -> List[Tuple[str, float, str]]:
    filtered_shows, history_buckets = filter_data_by_period(shows, histories, month, year)
    # Группируем скорости по названию спектакля
    speed_by_name = defaultdict(list)
    id_by_name = dict()
    for show in filtered_shows:
        h_rows = history_buckets.get(show.id, [])
        rate = calculate_average_sales_rate_for_show(h_rows)
        if rate is not None and rate > 0:
            speed_by_name[show.show_name].append(rate)
            if show.show_name not in id_by_name:
                id_by_name[show.show_name] = show.id
    # Для каждого спектакля берём максимальную скорость (или среднюю, если так логичнее)
    agg_speed = {name: max(rates) for name, rates in speed_by_name.items()}
    ordered = sorted(agg_speed.items(), key=lambda x: -x[1])
    result = []
    for show_name, rate in ordered[:n]:
        show_id = id_by_name.get(show_name, "")
        result.append((show_name, rate, show_id))
    return result


def shows_predicted_to_sell_out_soonest(
    shows: Sequence[Show],
    histories: Sequence[ShowSeatHistory],
    month: Optional[int] = None,
    year: Optional[int] = None,
    n: int = 5
) -> List[Tuple[str, int, str]]:
    filtered_shows, history_buckets = filter_data_by_period(shows, histories, month, year)
    now = datetime.now(pytz.timezone(settings.DEFAULT_TIMEZONE))
    result = []
    for show in filtered_shows:
        # Фильтруем только будущие спектакли
        show_dt = parse_show_date(show.date)
        if not show_dt or show_dt < now:
            continue
        h_rows = history_buckets.get(show.id, [])
        if len(h_rows) < 2:
            continue
        prediction_ts = predict_sold_out(h_rows)
        if prediction_ts is not None:
            result.append((show.show_name, prediction_ts, show.id))
    result.sort(key=lambda x: x[1])
    return result[:n]
