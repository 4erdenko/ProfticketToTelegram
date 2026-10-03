"""Observed inventory changes and conditional depletion scenarios."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import pytz

from config import settings

DAY_SECONDS = 24 * 3600
HISTORY_SECONDS = 7 * DAY_SECONDS
MAX_OBSERVATION_AGE = max(3600, 2 * getattr(settings, 'UPDATE_INTERVAL', 1800))
MAX_OBSERVATION_GAP = max(
    6 * 3600, 3 * getattr(settings, 'UPDATE_INTERVAL', 1800)
)
MIN_RATE_SPAN = 3600
MIN_TREND_SPAN = 18 * 3600
FORECAST_INTERVAL = 6 * 3600
MAX_FORECAST_SECONDS = 14 * DAY_SECONDS

type Trend = Literal[
    'depleting', 'replenishing', 'stable', 'accelerating', 'slowing', 'unknown'
]
type Quality = Literal[
    'good',
    'limited',
    'insufficient',
    'stale',
    'gapped',
    'inventory_jump',
    'past',
]
type Reason = Literal[
    'ok',
    'no_observations',
    'insufficient_history',
    'stale_data',
    'long_gap',
    'inventory_jump',
    'no_depletion',
    'volatile_rate',
    'forecast_beyond_horizon',
    'past_event',
    'invalid_event_date',
    'unknown_inventory',
]


class InventoryObservation(Protocol):
    timestamp: int | None
    seats: int | None


@dataclass(frozen=True, slots=True)
class InventoryInsights:
    latest_seats: int | None = None
    decreases: int = 0
    increases: int = 0
    net_rate_per_day: float | None = None
    previous_rate_per_day: float | None = None
    trend: Trend = 'unknown'
    forecast_at: int | None = None
    forecast_earliest: int | None = None
    forecast_latest: int | None = None
    quality: Quality = 'insufficient'
    reason: Reason = 'no_observations'


@dataclass(frozen=True, slots=True)
class _Point:
    timestamp: int
    seats: int


def _points(
    history: Sequence[InventoryObservation], now_ts: int
) -> list[_Point]:
    ordered = sorted(
        (
            row
            for row in history
            if row.timestamp is not None
            and row.timestamp <= now_ts
            and row.seats is not None
            and row.seats >= 0
        ),
        key=lambda row: (row.timestamp, getattr(row, 'id', None) or 0),
    )
    unique: dict[int, _Point] = {}
    for row in ordered:
        unique[row.timestamp] = _Point(row.timestamp, row.seats)
    return list(unique.values())


def _rate(points: Sequence[_Point]) -> float | None:
    if len(points) < 2:
        return None
    elapsed = points[-1].timestamp - points[0].timestamp
    if elapsed < MIN_RATE_SPAN:
        return None
    if any(
        current.timestamp - previous.timestamp > MAX_OBSERVATION_GAP
        for previous, current in zip(points, points[1:], strict=False)
    ):
        return None
    return (points[0].seats - points[-1].seats) * DAY_SECONDS / elapsed


def _window(points: Sequence[_Point], start: int, end: int) -> list[_Point]:
    selected = [point for point in points if start <= point.timestamp <= end]
    predecessor = next(
        (point for point in reversed(points) if point.timestamp < start),
        None,
    )
    if predecessor is not None and selected and selected[0].timestamp > start:
        selected.insert(0, predecessor)
    return selected


def time_weighted_rate(
    history: Sequence[InventoryObservation],
    now_ts: int,
    lookback_seconds: int = DAY_SECONDS,
) -> float | None:
    """Return signed net changes per day over the actual observed duration."""
    points = _window(
        _points(history, now_ts), now_ts - lookback_seconds, now_ts
    )
    return _rate(points)


def _large_increase(previous: _Point, current: _Point) -> bool:
    return current.seats - previous.seats >= max(20, previous.seats * 0.2)


def _independent_rates(points: Sequence[_Point]) -> list[float]:
    anchors = [points[0]]
    for point in points[1:]:
        if point.timestamp - anchors[-1].timestamp >= FORECAST_INTERVAL:
            anchors.append(point)
    if points[-1].timestamp - anchors[-1].timestamp >= MIN_RATE_SPAN:
        anchors.append(points[-1])
    return [
        (previous.seats - current.seats)
        * DAY_SECONDS
        / (current.timestamp - previous.timestamp)
        for previous, current in zip(anchors, anchors[1:], strict=False)
    ]


def _event_timestamp(show_dt: datetime | None) -> int | None:
    if show_dt is None:
        return None
    if show_dt.tzinfo is None:
        show_dt = pytz.timezone(settings.DEFAULT_TIMEZONE).localize(show_dt)
    return int(show_dt.timestamp())


def analyze_inventory(
    history: Sequence[InventoryObservation],
    now_ts: int,
    show_dt: datetime | None = None,
    *,
    jump_timestamps: Sequence[int] | None = None,
) -> InventoryInsights:
    """Keep inventory facts separate from a scenario, without probabilities.

    Sampled histories must supply quota jumps detected from raw transitions.
    """
    points = _points(history, now_ts)
    if not points:
        return InventoryInsights()
    jumps = (
        set(jump_timestamps)
        if jump_timestamps is not None
        else {
            after.timestamp
            for before, after in zip(points, points[1:], strict=False)
            if _large_increase(before, after)
        }
    )
    latest = points[-1]
    recent = _window(points, now_ts - DAY_SECONDS, now_ts)
    previous = _window(points, now_ts - 2 * DAY_SECONDS, now_ts - DAY_SECONDS)
    differences = [
        before.seats - after.seats
        for before, after in zip(recent, recent[1:], strict=False)
    ]
    values = {
        'latest_seats': latest.seats,
        'decreases': sum(max(change, 0) for change in differences),
        'increases': sum(max(-change, 0) for change in differences),
        'net_rate_per_day': _rate(recent),
        'previous_rate_per_day': _rate(previous),
    }
    if (
        len(previous) < 2
        or previous[-1].timestamp - previous[0].timestamp < MIN_TREND_SPAN
        or any(
            previous[0].timestamp < timestamp <= previous[-1].timestamp
            for timestamp in jumps
        )
    ):
        values['previous_rate_per_day'] = None

    def result(
        quality: Quality, reason: Reason, **extra: object
    ) -> InventoryInsights:
        return InventoryInsights(
            **values, quality=quality, reason=reason, **extra
        )

    show_ts = _event_timestamp(show_dt)
    if show_ts is not None and show_ts <= now_ts:
        return result('past', 'past_event')
    if now_ts - latest.timestamp > MAX_OBSERVATION_AGE:
        values['net_rate_per_day'] = None
        return result('stale', 'stale_data')

    segment_start = 0
    disruption: Reason | None = None
    for index, (before, after) in enumerate(
        zip(points, points[1:], strict=False), 1
    ):
        if after.timestamp - before.timestamp > MAX_OBSERVATION_GAP:
            segment_start, disruption = index, 'long_gap'
        elif after.timestamp in jumps:
            segment_start, disruption = index, 'inventory_jump'
    segment = [
        p
        for p in points[segment_start:]
        if p.timestamp >= now_ts - HISTORY_SECONDS
    ]
    if disruption and points[segment_start].timestamp > now_ts - DAY_SECONDS:
        if disruption == 'inventory_jump':
            values['net_rate_per_day'] = None
            return result('inventory_jump', disruption)
        return result('gapped', disruption)

    rate = values['net_rate_per_day']
    if rate is None:
        return result('insufficient', 'insufficient_history')
    old_rate = values['previous_rate_per_day']
    trend: Trend = (
        'depleting' if rate > 0 else 'replenishing' if rate < 0 else 'stable'
    )
    if (
        rate > 0
        and old_rate is not None
        and old_rate > 0
        and recent[-1].timestamp - recent[0].timestamp >= MIN_TREND_SPAN
    ):
        threshold = max(1.0, abs(old_rate) * 0.2)
        if rate - old_rate > threshold:
            trend = 'accelerating'
        elif old_rate - rate > threshold:
            trend = 'slowing'
    if latest.seats == 0 or rate <= 0:
        return result('good', 'no_depletion', trend=trend)
    if show_ts is None:
        return result('limited', 'invalid_event_date', trend=trend)
    if (
        len(segment) < 5
        or segment[-1].timestamp - segment[0].timestamp < DAY_SECONDS
    ):
        return result('limited', 'insufficient_history', trend=trend)
    block_rates = _independent_rates(segment)
    if len(block_rates) < 4:
        return result('limited', 'insufficient_history', trend=trend)
    ordered = sorted(block_rates)
    slow = ordered[len(ordered) // 4]
    fast = ordered[min(3 * len(ordered) // 4, len(ordered) - 1)]
    if slow <= 0 or fast > 2 * slow:
        return result('limited', 'volatile_rate', trend=trend)
    scenario_rates = [rate, slow, fast]
    if old_rate is not None:
        if old_rate <= 0:
            return result('limited', 'volatile_rate', trend=trend)
        scenario_rates.append(old_rate)
    slow, fast = min(scenario_rates), max(scenario_rates)
    if fast > 2 * slow:
        return result('limited', 'volatile_rate', trend=trend)
    center = latest.timestamp + round(latest.seats * DAY_SECONDS / rate)
    earliest = latest.timestamp + round(latest.seats * DAY_SECONDS / fast)
    latest_forecast = latest.timestamp + round(
        latest.seats * DAY_SECONDS / slow
    )
    if earliest <= now_ts or latest_forecast > min(
        show_ts, now_ts + MAX_FORECAST_SECONDS
    ):
        return result('limited', 'forecast_beyond_horizon', trend=trend)
    return result(
        'good',
        'ok',
        trend=trend,
        forecast_at=center,
        forecast_earliest=earliest,
        forecast_latest=latest_forecast,
    )
