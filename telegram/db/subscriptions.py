"""Owner-scoped subscriptions and verified future event baselines."""

import json
from dataclasses import dataclass
from datetime import datetime

import pytz
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.profticket.analytics import TITLES_TO_SKIP, parse_show_date
from telegram.db.models import Show, Subscription, SubscriptionDigest, User
from telegram.tg_utils import normalize_actor_name

INTERVALS = (1800, 3600, 21600, 43200, 86400, 604800)


async def save_digest(
    session: AsyncSession, user_id: int, pages: list[str]
) -> int:
    identifier = (
        await session.execute(
            insert(SubscriptionDigest)
            .values(user_id=user_id, pages=pages)
            .returning(SubscriptionDigest.id)
        )
    ).scalar_one()
    await session.commit()
    return identifier


async def get_digest(
    session: AsyncSession, user_id: int, identifier: int
) -> SubscriptionDigest | None:
    return (
        await session.execute(
            select(SubscriptionDigest).where(
                SubscriptionDigest.id == identifier,
                SubscriptionDigest.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


@dataclass(frozen=True, slots=True)
class SubscriptionTarget:
    kind: str
    key: str
    label: str


def now_timestamp() -> int:
    return int(datetime.now().timestamp())


def future_event(show: Show, now_ts: int) -> bool:
    date = parse_show_date(show.date)
    if date is None:
        return False
    if date.tzinfo is None:
        date = pytz.timezone(settings.DEFAULT_TIMEZONE).localize(date)
    return date.timestamp() > now_ts


def fresh_event(show: Show, now_ts: int) -> bool:
    maximum_age = max(3600, 2 * settings.UPDATE_INTERVAL)
    return (
        show.updated_at is not None
        and 0 <= now_ts - show.updated_at <= maximum_age
    )


def cast_names(actors: str | None) -> list[str]:
    try:
        data = json.loads(actors or '[]')
    except TypeError, ValueError:
        return []
    excluded = {normalize_actor_name(title) for title in TITLES_TO_SKIP}
    return (
        [
            actor
            for actor in data
            if isinstance(actor, str)
            and actor.strip()
            and normalize_actor_name(actor) not in excluded
        ]
        if isinstance(data, list)
        else []
    )


def show_key(show: Show) -> str:
    return (
        f'show:{show.show_id}'
        if show.show_id is not None
        else f'event:{show.id}'
    )


def matches_target(show: Show, target: SubscriptionTarget) -> bool:
    if target.kind == 'show':
        return show_key(show) == target.key
    return target.key in {
        normalize_actor_name(actor) for actor in cast_names(show.actors)
    }


async def matching_shows(
    session: AsyncSession, target: SubscriptionTarget, now_ts: int
) -> list[Show]:
    query = select(Show).where(Show.is_deleted.is_(False))
    if target.kind == 'show':
        if target.key.startswith('show:'):
            try:
                query = query.where(Show.show_id == int(target.key[5:]))
            except ValueError:
                return []
        elif target.key.startswith('event:'):
            query = query.where(Show.id == target.key[6:])
        else:
            return []
    rows = (await session.execute(query)).scalars().all()
    return [
        show
        for show in rows
        if future_event(show, now_ts) and matches_target(show, target)
    ]


def event_state(show: Show) -> dict:
    return {
        'date': show.date,
        'seats': show.seats,
        'min_price': show.min_price,
        'max_price': show.max_price,
        'updated_at': show.updated_at,
    }


async def capture_baseline(
    session: AsyncSession, target: SubscriptionTarget, now_ts: int
) -> dict:
    shows = await matching_shows(session, target, now_ts)
    return {
        'events': {
            show.id: event_state(show)
            for show in shows
            if fresh_event(show, now_ts)
        },
        'waiting': [
            show.id for show in shows if not fresh_event(show, now_ts)
        ],
    }


async def search_targets(
    session: AsyncSession,
    kind: str,
    query: str,
    limit: int = 8,
    now_ts: int | None = None,
) -> list[SubscriptionTarget]:
    if kind not in ('show', 'actor'):
        raise ValueError('Unknown subscription kind')
    if limit <= 0:
        return []
    now_ts = now_timestamp() if now_ts is None else now_ts
    targets: dict[str, SubscriptionTarget] = {}
    needle = normalize_actor_name(query)
    if not needle:
        return []
    if kind == 'actor':
        casts = (
            (
                await session.execute(
                    select(Show.actors)
                    .where(Show.actors.is_not(None))
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        for cast in casts:
            for actor in cast_names(cast):
                key = normalize_actor_name(actor)
                if key and needle in key:
                    targets.setdefault(
                        key, SubscriptionTarget(kind, key, actor.strip())
                    )
    else:
        shows = (
            (
                await session.execute(
                    select(Show)
                    .where(Show.is_deleted.is_(False))
                    .order_by(Show.id)
                )
            )
            .scalars()
            .all()
        )
        for show in shows:
            if (
                future_event(show, now_ts)
                and show.show_name
                and needle in normalize_actor_name(show.show_name)
            ):
                key = show_key(show)
                targets.setdefault(
                    key, SubscriptionTarget(kind, key, show.show_name)
                )
    return sorted(
        targets.values(), key=lambda row: (row.label.casefold(), row.key)
    )[:limit]


async def list_subscriptions(
    session: AsyncSession, user_id: int
) -> list[Subscription]:
    return list(
        (
            await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .order_by(Subscription.id)
            )
        )
        .scalars()
        .all()
    )


async def get_subscription(
    session: AsyncSession, user_id: int, id: int
) -> Subscription | None:
    return (
        await session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id, Subscription.id == id
            )
        )
    ).scalar_one_or_none()


def _validate_interval(interval_seconds: int) -> None:
    if interval_seconds not in INTERVALS:
        raise ValueError('Unknown notification interval')


async def save_subscription(
    session: AsyncSession,
    user_id: int,
    target: SubscriptionTarget,
    interval_seconds: int,
    now_ts: int | None = None,
) -> Subscription:
    _validate_interval(interval_seconds)
    now_ts = now_timestamp() if now_ts is None else now_ts
    if await session.get(User, user_id) is None:
        raise ValueError('Unknown subscription owner')
    if target.kind == 'show':
        shows = await matching_shows(session, target, now_ts)
        verified = (
            SubscriptionTarget('show', target.key, shows[0].show_name)
            if shows and shows[0].show_name
            else None
        )
    else:
        known = await search_targets(
            session, target.kind, target.key, limit=10000, now_ts=now_ts
        )
        verified = next((row for row in known if row.key == target.key), None)
    if verified is None:
        raise ValueError('Unknown subscription target')
    baseline = await capture_baseline(session, verified, now_ts)
    await session.execute(
        insert(Subscription)
        .values(
            user_id=user_id,
            kind=verified.kind,
            key=verified.key,
            label=verified.label,
            interval_seconds=interval_seconds,
            enabled=True,
            created_at=now_ts,
            next_due_at=now_ts + interval_seconds,
            baseline=baseline,
            failure_count=0,
            needs_baseline=False,
        )
        .on_conflict_do_nothing(index_elements=['user_id', 'kind', 'key'])
    )
    row = (
        await session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.kind == verified.kind,
                Subscription.key == verified.key,
            )
            .with_for_update()
        )
    ).scalar_one()
    if not row.enabled:
        row.baseline = baseline
        row.enabled = True
        row.needs_baseline = False
        row.retry_at = None
        row.failure_count = 0
        row.next_due_at = now_ts + interval_seconds
    elif row.interval_seconds != interval_seconds:
        row.next_due_at = now_ts + interval_seconds
    row.interval_seconds = interval_seconds
    row.label = verified.label
    await session.commit()
    return row


async def update_subscription(
    session: AsyncSession,
    user_id: int,
    id: int,
    interval_seconds: int | None = None,
    enabled: bool | None = None,
    now_ts: int | None = None,
) -> Subscription | None:
    if interval_seconds is not None:
        _validate_interval(interval_seconds)
    now_ts = now_timestamp() if now_ts is None else now_ts
    row = (
        await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.id == id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    if (
        interval_seconds is not None
        and row.interval_seconds != interval_seconds
    ):
        row.interval_seconds = interval_seconds
        row.next_due_at = now_ts + interval_seconds
    if enabled is not None and row.enabled != enabled:
        row.enabled = enabled
        if enabled:
            row.baseline = await capture_baseline(
                session,
                SubscriptionTarget(row.kind, row.key, row.label),
                now_ts,
            )
            row.next_due_at = now_ts + row.interval_seconds
            row.needs_baseline = False
            row.retry_at = None
            row.failure_count = 0
    await session.commit()
    return row


async def delete_subscription(
    session: AsyncSession, user_id: int, id: int
) -> bool:
    row = (
        await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, Subscription.id == id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True
