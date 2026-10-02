"""Database aggregates and bounded histories for Telegram reports."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pytz
from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.profticket import analytics
from telegram.db.models import Show, ShowSeatHistory

type ReportKind = Literal[
    'sales',
    'artists',
    'returns',
    'return_rate',
    'calendar',
    'speed',
    'prediction',
]

MAX_HISTORY_POINTS = 288
LOOKBACK_SECONDS = 24 * 3600
PREDICTION_HISTORY_POINTS = 512
PREDICTION_LOOKBACK_SECONDS = 7 * LOOKBACK_SECONDS


@dataclass(slots=True)
class ReportData:
    results: list | dict[str, list]
    first_seen: dict[str | int, int] = field(default_factory=dict)
    artist_first_seen: dict[str, int] = field(default_factory=dict)
    show_status: dict[str | int, bool] = field(default_factory=dict)


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
        if kind in ('speed', 'prediction'):
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
        histories = (
            (
                await self.session.execute(
                    recent_history_query(
                        month,
                        year,
                        int(now.timestamp()),
                        include_past_shows,
                        historical,
                        PREDICTION_LOOKBACK_SECONDS
                        if kind == 'prediction'
                        else LOOKBACK_SECONDS,
                        PREDICTION_HISTORY_POINTS
                        if kind == 'prediction'
                        else MAX_HISTORY_POINTS,
                    )
                )
            )
            .scalars()
            .all()
        )
        if kind == 'speed':
            results = await asyncio.to_thread(
                analytics.top_shows_by_current_sales_speed,
                shows,
                histories,
                month,
                year,
                n,
                True,
            )
        else:
            results = await asyncio.to_thread(
                analytics.shows_predicted_to_sell_out_soonest,
                shows,
                histories,
                month,
                year,
                n,
            )
        statuses: dict[str | int, bool] = {}
        for show in shows:
            key = show.show_id or show.id
            statuses[key] = statuses.get(key, True) and bool(show.is_deleted)
        return ReportData(results, show_status=statuses)
