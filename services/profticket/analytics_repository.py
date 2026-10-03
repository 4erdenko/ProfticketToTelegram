"""Database aggregates and bounded histories for Telegram reports."""

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal

import pytz
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.profticket import analytics
from services.profticket.insights import (
    MAX_OBSERVATION_AGE,
    MAX_OBSERVATION_GAP,
    InventoryInsights,
    analyze_inventory,
)
from telegram.db.models import Show, ShowSeatHistory

type ReportKind = Literal[
    'sales',
    'artists',
    'returns',
    'return_rate',
    'calendar',
    'speed',
    'prediction',
    'trends',
]

MAX_HISTORY_POINTS = 288
LOOKBACK_SECONDS = 24 * 3600
PREDICTION_HISTORY_POINTS = 512
PREDICTION_LOOKBACK_SECONDS = 7 * LOOKBACK_SECONDS
HISTORY_BUCKET_SECONDS = 1800


@dataclass(slots=True)
class ReportData:
    results: list | dict[str, list]
    first_seen: dict[str | int, int] = field(default_factory=dict)
    artist_first_seen: dict[str, int] = field(default_factory=dict)
    show_status: dict[str | int, bool] = field(default_factory=dict)
    insights: dict[str, InventoryInsights] = field(default_factory=dict)


def _selected_shows(
    month: int | None,
    year: int | None,
    include_past_shows: bool,
) -> Select:
    query = select(Show.id)
    if month is not None and year is not None:
        query = query.where(Show.month == month, Show.year == year)
    if not include_past_shows:
        query = query.where(Show.is_deleted.is_(False))
    return query


def performance_totals_query(
    month: int | None = None,
    year: int | None = None,
    include_past_shows: bool = True,
) -> Select:
    selected = _selected_shows(month, year, include_past_shows)
    previous = func.lag(ShowSeatHistory.seats).over(
        partition_by=ShowSeatHistory.show_id,
        order_by=(ShowSeatHistory.timestamp, ShowSeatHistory.id),
    )
    snapshots = (
        select(
            ShowSeatHistory.show_id.label('event_id'),
            ShowSeatHistory.timestamp,
            (previous - ShowSeatHistory.seats).label('difference'),
        )
        .where(
            ShowSeatHistory.show_id.in_(selected),
            ShowSeatHistory.timestamp.is_not(None),
            ShowSeatHistory.seats.is_not(None),
        )
        .subquery()
    )
    totals = (
        select(
            snapshots.c.event_id,
            func.sum(
                case(
                    (snapshots.c.difference > 0, snapshots.c.difference),
                    else_=0,
                )
            ).label('sold'),
            func.sum(
                case(
                    (snapshots.c.difference < 0, -snapshots.c.difference),
                    else_=0,
                )
            ).label('returned'),
            func.min(snapshots.c.timestamp).label('first_seen'),
        )
        .group_by(snapshots.c.event_id)
        .having(func.count() >= 2)
        .subquery()
    )
    return (
        select(Show, totals.c.sold, totals.c.returned, totals.c.first_seen)
        .join(totals, totals.c.event_id == Show.id)
        .order_by(Show.id)
    )


def recent_history_query(
    month: int | None,
    year: int | None,
    now_ts: int,
    include_past_shows: bool = True,
    historical: bool = False,
    lookback_seconds: int = LOOKBACK_SECONDS,
    max_points: int = MAX_HISTORY_POINTS,
) -> Select:
    selected = _selected_shows(month, year, include_past_shows)
    query = select(
        ShowSeatHistory.id,
        func.row_number()
        .over(
            partition_by=ShowSeatHistory.show_id,
            order_by=(
                ShowSeatHistory.timestamp.desc(),
                ShowSeatHistory.id.desc(),
            ),
        )
        .label('position'),
    ).where(
        ShowSeatHistory.show_id.in_(selected),
        ShowSeatHistory.timestamp.is_not(None),
        ShowSeatHistory.seats.is_not(None),
        ShowSeatHistory.timestamp <= now_ts,
    )
    if historical:
        latest = (
            select(
                ShowSeatHistory.show_id,
                func.max(ShowSeatHistory.timestamp).label('last_seen'),
            )
            .where(
                ShowSeatHistory.show_id.in_(selected),
                ShowSeatHistory.timestamp <= now_ts,
                ShowSeatHistory.seats.is_not(None),
            )
            .group_by(ShowSeatHistory.show_id)
            .subquery()
        )
        query = query.join(
            latest, latest.c.show_id == ShowSeatHistory.show_id
        ).where(
            ShowSeatHistory.timestamp >= latest.c.last_seen - lookback_seconds
        )
    else:
        query = query.where(
            ShowSeatHistory.timestamp >= now_ts - lookback_seconds
        )
    ranked = query.subquery()
    return (
        select(ShowSeatHistory)
        .join(ranked, ranked.c.id == ShowSeatHistory.id)
        .where(ranked.c.position <= max_points)
        .order_by(
            ShowSeatHistory.show_id,
            ShowSeatHistory.timestamp,
            ShowSeatHistory.id,
        )
    )


def insights_history_query(event_ids: Sequence[str], now_ts: int) -> Select:
    """Retain history endpoints, day boundaries, quota jumps and gap edges."""
    bucket = func.floor(ShowSeatHistory.timestamp / HISTORY_BUCKET_SECONDS)
    # Materialize summaries once when PostgreSQL table statistics are missing.
    cutoffs = (
        select(
            ShowSeatHistory.show_id,
            func.max(
                case(
                    (
                        ShowSeatHistory.timestamp <= now_ts - LOOKBACK_SECONDS,
                        ShowSeatHistory.timestamp,
                    ),
                    else_=None,
                )
            ).label('current_start'),
            func.max(
                case(
                    (
                        ShowSeatHistory.timestamp
                        <= now_ts - 2 * LOOKBACK_SECONDS,
                        ShowSeatHistory.timestamp,
                    ),
                    else_=None,
                )
            ).label('previous_start'),
        )
        .where(
            ShowSeatHistory.show_id.in_(event_ids),
            ShowSeatHistory.timestamp >= now_ts - PREDICTION_LOOKBACK_SECONDS,
            ShowSeatHistory.timestamp <= now_ts,
            ShowSeatHistory.seats.is_not(None),
            ShowSeatHistory.seats >= 0,
        )
        .group_by(ShowSeatHistory.show_id)
        .cte('inventory_cutoffs')
        .prefix_with('MATERIALIZED', dialect='postgresql')
    )
    ranked = (
        select(
            ShowSeatHistory.id,
            ShowSeatHistory.show_id,
            ShowSeatHistory.timestamp,
            ShowSeatHistory.seats,
            func.row_number()
            .over(
                partition_by=(ShowSeatHistory.show_id, bucket),
                order_by=(
                    ShowSeatHistory.timestamp.desc(),
                    ShowSeatHistory.id.desc(),
                ),
            )
            .label('position'),
            func.row_number()
            .over(
                partition_by=(
                    ShowSeatHistory.show_id,
                    ShowSeatHistory.timestamp,
                ),
                order_by=ShowSeatHistory.id.desc(),
            )
            .label('time_position'),
        )
        .where(
            ShowSeatHistory.show_id.in_(event_ids),
            ShowSeatHistory.timestamp >= now_ts - PREDICTION_LOOKBACK_SECONDS,
            ShowSeatHistory.timestamp <= now_ts,
            ShowSeatHistory.seats.is_not(None),
            ShowSeatHistory.seats >= 0,
        )
        .cte('ranked_inventory')
    )
    points = select(ranked).where(ranked.c.time_position == 1).subquery()
    previous = func.lag(points.c.seats).over(
        partition_by=points.c.show_id, order_by=points.c.timestamp
    )
    transitions = (
        select(
            points.c.id,
            points.c.show_id,
            points.c.timestamp,
            points.c.seats,
            points.c.position,
            previous.label('previous'),
            func.lag(points.c.id)
            .over(partition_by=points.c.show_id, order_by=points.c.timestamp)
            .label('before_id'),
            func.lag(points.c.timestamp)
            .over(partition_by=points.c.show_id, order_by=points.c.timestamp)
            .label('previous_timestamp'),
        )
        .cte('inventory_transitions')
        .prefix_with('MATERIALIZED', dialect='postgresql')
    )
    threshold = case(
        (
            transitions.c.previous * 0.2 > 20,
            transitions.c.previous * 0.2,
        ),
        else_=20,
    )
    jumps = (
        select(
            transitions.c.show_id,
            transitions.c.timestamp,
            transitions.c.before_id,
            transitions.c.id.label('after_id'),
            func.max(
                case(
                    (
                        transitions.c.timestamp <= now_ts - LOOKBACK_SECONDS,
                        transitions.c.timestamp,
                    ),
                    else_=None,
                )
            )
            .over(partition_by=transitions.c.show_id)
            .label('previous_jump_at'),
            func.row_number()
            .over(
                partition_by=transitions.c.show_id,
                order_by=transitions.c.timestamp.desc(),
            )
            .label('jump_position'),
        )
        .where(transitions.c.seats - transitions.c.previous >= threshold)
        .subquery()
    )
    last_jump = (
        select(jumps)
        .where(jumps.c.jump_position == 1)
        .cte('inventory_last_jump')
        .prefix_with('MATERIALIZED', dialect='postgresql')
    )
    return (
        select(
            ShowSeatHistory,
            last_jump.c.timestamp.label('jump_at'),
            last_jump.c.previous_jump_at,
        )
        .join(transitions, transitions.c.id == ShowSeatHistory.id)
        .outerjoin(cutoffs, cutoffs.c.show_id == transitions.c.show_id)
        .outerjoin(last_jump, last_jump.c.show_id == transitions.c.show_id)
        .where(
            or_(
                transitions.c.position == 1,
                transitions.c.previous_timestamp.is_(None),
                transitions.c.timestamp == cutoffs.c.current_start,
                transitions.c.timestamp == cutoffs.c.previous_start,
                transitions.c.id == last_jump.c.before_id,
                transitions.c.id == last_jump.c.after_id,
                # Keep gaps from growing past the limit during sampling.
                transitions.c.timestamp - transitions.c.previous_timestamp
                > MAX_OBSERVATION_GAP - HISTORY_BUCKET_SECONDS,
            ),
        )
        .order_by(
            ShowSeatHistory.show_id,
            ShowSeatHistory.timestamp,
            ShowSeatHistory.id,
        )
    )


def daily_inventory_totals_query(
    event_ids: Sequence[str], now_ts: int
) -> Select:
    """Count every daily change before thinning model observations."""
    predecessors = (
        select(
            ShowSeatHistory.show_id,
            func.max(ShowSeatHistory.timestamp).label('timestamp'),
        )
        .where(
            ShowSeatHistory.show_id.in_(event_ids),
            ShowSeatHistory.timestamp <= now_ts - LOOKBACK_SECONDS,
            ShowSeatHistory.seats.is_not(None),
            ShowSeatHistory.seats >= 0,
        )
        .group_by(ShowSeatHistory.show_id)
        .subquery()
    )
    ranked = (
        select(
            ShowSeatHistory.show_id,
            ShowSeatHistory.timestamp,
            ShowSeatHistory.seats,
            func.row_number()
            .over(
                partition_by=(
                    ShowSeatHistory.show_id,
                    ShowSeatHistory.timestamp,
                ),
                order_by=ShowSeatHistory.id.desc(),
            )
            .label('position'),
        )
        .outerjoin(
            predecessors, predecessors.c.show_id == ShowSeatHistory.show_id
        )
        .where(
            ShowSeatHistory.show_id.in_(event_ids),
            or_(
                ShowSeatHistory.timestamp >= now_ts - LOOKBACK_SECONDS,
                ShowSeatHistory.timestamp == predecessors.c.timestamp,
            ),
            ShowSeatHistory.timestamp <= now_ts,
            ShowSeatHistory.seats.is_not(None),
            ShowSeatHistory.seats >= 0,
        )
        .subquery()
    )
    points = select(ranked).where(ranked.c.position == 1).subquery()
    previous = func.lag(points.c.seats).over(
        partition_by=points.c.show_id, order_by=points.c.timestamp
    )
    deltas = select(
        points.c.show_id,
        points.c.timestamp,
        (previous - points.c.seats).label('difference'),
        previous.label('previous'),
    ).subquery()
    threshold = case(
        (deltas.c.previous * 0.2 > 20, deltas.c.previous * 0.2), else_=20
    )
    return select(
        deltas.c.show_id,
        func.sum(
            case((deltas.c.difference > 0, deltas.c.difference), else_=0)
        ).label('decreases'),
        func.sum(
            case((deltas.c.difference < 0, -deltas.c.difference), else_=0)
        ).label('increases'),
        func.max(
            case(
                (-deltas.c.difference >= threshold, deltas.c.timestamp),
                else_=None,
            )
        ).label('jump_at'),
    ).group_by(deltas.c.show_id)


async def load_inventory_insights(
    session: AsyncSession, shows: Sequence[Show], now_ts: int
) -> dict[str, InventoryInsights]:
    """Load bounded history, exact daily facts and current inventory."""
    if not shows:
        return {}
    histories = (
        await session.execute(
            insights_history_query([show.id for show in shows], now_ts)
        )
    ).all()
    buckets: dict[str, list[ShowSeatHistory]] = defaultdict(list)
    jumps: dict[str, tuple[int, ...]] = {}
    for row, jump_at, previous_jump_at in histories:
        buckets[row.show_id].append(row)
        jumps[row.show_id] = tuple(
            timestamp
            for timestamp in (jump_at, previous_jump_at)
            if timestamp is not None
        )
    insights = await asyncio.to_thread(
        lambda: {
            show.id: analyze_inventory(
                buckets[show.id],
                now_ts,
                analytics.parse_show_date(show.date),
                jump_timestamps=jumps.get(show.id, ()),
            )
            for show in shows
        }
    )
    facts = (
        await session.execute(
            daily_inventory_totals_query([show.id for show in shows], now_ts)
        )
    ).all()
    for event_id, decreases, increases, jump_at in facts:
        item = replace(
            insights[event_id],
            decreases=int(decreases),
            increases=int(increases),
        )
        if jump_at is not None and item.quality not in (
            'stale',
            'past',
        ):
            item = replace(
                item,
                net_rate_per_day=None,
                trend='unknown',
                forecast_at=None,
                forecast_earliest=None,
                forecast_latest=None,
                quality='inventory_jump',
                reason='inventory_jump',
            )
        insights[event_id] = item
    for show in shows:
        item = insights[show.id]
        if item.quality == 'past':
            continue
        if show.seats is None or show.seats < 0:
            quality, reason = 'insufficient', 'unknown_inventory'
        elif (
            show.updated_at is None
            or show.updated_at > now_ts
            or now_ts - show.updated_at > MAX_OBSERVATION_AGE
        ):
            quality, reason = 'stale', 'stale_data'
        elif item.reason == 'no_observations':
            insights[show.id] = replace(item, latest_seats=show.seats)
            continue
        elif show.seats != item.latest_seats:
            quality, reason = 'insufficient', 'unknown_inventory'
        else:
            continue
        insights[show.id] = replace(
            item,
            latest_seats=show.seats
            if show.seats is not None and show.seats >= 0
            else None,
            net_rate_per_day=None,
            forecast_at=None,
            forecast_earliest=None,
            forecast_latest=None,
            quality=quality,
            reason=reason,
            trend='unknown',
        )
    return insights


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def available_months(self) -> list[tuple[int, int]]:
        query = (
            select(Show.month, Show.year)
            .where(Show.month.is_not(None), Show.year.is_not(None))
            .distinct()
            .order_by(Show.year, Show.month)
        )
        return [
            tuple(row) for row in (await self.session.execute(query)).all()
        ]

    async def performance_totals(
        self,
        month: int | None = None,
        year: int | None = None,
        include_past_shows: bool = True,
    ) -> list[analytics.PerformanceSales]:
        rows = (
            await self.session.execute(
                performance_totals_query(month, year, include_past_shows)
            )
        ).all()
        return [
            analytics.PerformanceSales(show, int(sold), int(returned), first)
            for show, sold, returned, first in rows
        ]

    async def report(
        self,
        kind: ReportKind,
        month: int | None = None,
        year: int | None = None,
        n: int = 10,
    ) -> ReportData:
        if kind in ('speed', 'prediction', 'trends'):
            return await self._recent_report(kind, month, year, n)

        performances = await self.performance_totals(month, year)
        functions = {
            'sales': analytics.sales_report,
            'artists': analytics.artists_report,
            'returns': analytics.returns_report,
            'return_rate': analytics.return_rate_report,
            'calendar': analytics.calendar_report,
        }
        results = await asyncio.to_thread(functions[kind], performances, n)
        tracking = performances
        if month is None and year is None:
            rows = (
                await self.session.execute(
                    select(Show, func.min(ShowSeatHistory.timestamp))
                    .join(ShowSeatHistory, ShowSeatHistory.show_id == Show.id)
                    .group_by(Show.id)
                    .order_by(Show.id)
                )
            ).all()
            tracking = [
                analytics.PerformanceSales(show, 0, 0, first)
                for show, first in rows
                if first is not None
            ]
        first_seen = {
            key: item.first_seen
            for key, item in analytics.group_sales(tracking).items()
            if item.first_seen is not None
        }
        artist_first_seen: dict[str, int] = {}
        if kind == 'artists':
            for item in tracking:
                if item.first_seen is None:
                    continue
                for actor in analytics.real_actors(item.show):
                    artist_first_seen[actor] = min(
                        artist_first_seen.get(actor, item.first_seen),
                        item.first_seen,
                    )
        return ReportData(results, first_seen, artist_first_seen)

    async def _recent_report(
        self, kind: ReportKind, month: int | None, year: int | None, n: int
    ) -> ReportData:
        timezone = pytz.timezone(settings.DEFAULT_TIMEZONE)
        now = datetime.now(timezone)
        include_past_shows = kind == 'speed'
        historical = (
            kind == 'speed'
            and month is not None
            and year is not None
            and (year, month) < (now.year, now.month)
        )
        selected = _selected_shows(month, year, include_past_shows)
        shows = (
            (
                await self.session.execute(
                    select(Show).where(Show.id.in_(selected))
                )
            )
            .scalars()
            .all()
        )
        if kind == 'trends':
            shows = [
                show
                for show in shows
                if (date := analytics.parse_show_date(show.date)) is not None
                and (timezone.localize(date) if date.tzinfo is None else date)
                > now
            ]
        histories = []
        if kind == 'speed':
            histories = (
                (
                    await self.session.execute(
                        recent_history_query(
                            month,
                            year,
                            int(now.timestamp()),
                            include_past_shows,
                            historical,
                        )
                    )
                )
                .scalars()
                .all()
            )
        insights = await load_inventory_insights(
            self.session, shows, int(now.timestamp())
        )
        if kind == 'speed':
            speed_shows = (
                shows
                if historical
                else [
                    show
                    for show in shows
                    if insights[show.id].net_rate_per_day is not None
                ]
            )
            results = await asyncio.to_thread(
                analytics.top_shows_by_current_sales_speed,
                speed_shows,
                histories,
                month,
                year,
                n,
                True,
                net_rates_per_day=None
                if historical
                else {
                    event_id: item.net_rate_per_day
                    for event_id, item in insights.items()
                },
            )
        elif kind == 'prediction':
            results = sorted(
                (
                    (show.show_name, item.forecast_at, show.id, show.date)
                    for show in shows
                    if (item := insights[show.id]).forecast_at is not None
                ),
                key=lambda row: (row[1], row[2]),
            )[:n]
        else:
            results = sorted(
                shows,
                key=lambda show: (
                    insights[show.id].net_rate_per_day is None,
                    -abs(insights[show.id].net_rate_per_day or 0),
                    -(
                        insights[show.id].decreases
                        + insights[show.id].increases
                    ),
                    show.id,
                ),
            )[:n]
        statuses: dict[str | int, bool] = {}
        for show in shows:
            key = show.show_id or show.id
            statuses[key] = statuses.get(key, True) and bool(show.is_deleted)
        return ReportData(results, show_status=statuses, insights=insights)
