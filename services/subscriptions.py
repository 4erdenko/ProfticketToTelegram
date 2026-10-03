"""Deliver change digests independently of source collection."""

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from html import escape

import pytz
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import LinkPreviewOptions
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import settings
from services.profticket.analytics import parse_show_date
from services.profticket.analytics_repository import load_inventory_insights
from telegram.analytics_messages import (
    INVENTORY_EXPLANATION,
    format_inventory_insights,
    inventory_date,
    inventory_number,
    performance_date,
)
from telegram.db.models import Show, Subscription, User
from telegram.db.subscriptions import (
    SubscriptionTarget,
    capture_baseline,
    event_state,
    fresh_event,
    future_event,
    matching_shows,
    now_timestamp,
    save_digest,
)
from telegram.keyboards.subscription_keyboard import (
    subscription_digest_keyboard,
)
from telegram.lexicon.subscriptions import LEXICON_SUBSCRIPTIONS as TEXT
from telegram.tg_utils import split_message_by_separator

logger = logging.getLogger(__name__)
TICK_SECONDS = 60
MAX_SUBSCRIPTIONS_PER_TICK = 100


def _delivery_state(subscription: Subscription) -> tuple:
    return (
        subscription.baseline,
        subscription.next_due_at,
        subscription.retry_at,
        subscription.interval_seconds,
        subscription.enabled,
        subscription.needs_baseline,
        subscription.kind,
        subscription.key,
        subscription.label,
    )


@dataclass(slots=True)
class EventChange:
    show: Show
    previous: dict | None
    state: dict
    kinds: list[str]


async def detect_changes(
    session: AsyncSession, subscription: Subscription, now_ts: int
) -> tuple[list[EventChange], dict]:
    target = SubscriptionTarget(
        subscription.kind, subscription.key, subscription.label
    )
    shows = await matching_shows(session, target, now_ts)
    old = subscription.baseline or {}
    events = {key: dict(value) for key, value in old.get('events', {}).items()}
    waiting = set(old.get('waiting', []))
    changes = []
    for key, value in list(events.items()):
        if not future_event(Show(date=value.get('date')), now_ts):
            events.pop(key)
    for show in shows:
        if not fresh_event(show, now_ts):
            continue
        current = event_state(show)
        previous = events.get(show.id)
        if show.id in waiting:
            waiting.remove(show.id)
            events[show.id] = current
            continue
        kinds = []
        if previous is None:
            kinds.append('new')
        else:
            if previous.get('date') != current['date']:
                kinds.append('date')
            old_seats, seats = previous.get('seats'), current['seats']
            if seats is not None and old_seats != seats:
                kinds.append('seats')
            if seats is None:
                current['seats'] = old_seats
            for field in ('min_price', 'max_price'):
                before, after = previous.get(field), current[field]
                if (
                    before is not None
                    and after is not None
                    and before != after
                    and 'prices' not in kinds
                ):
                    kinds.append('prices')
                if after is None:
                    current[field] = before
        if kinds:
            changes.append(EventChange(show, previous, current, kinds))
        events[show.id] = current
    return changes, {'events': events, 'waiting': sorted(waiting)}


async def render_digest(
    session: AsyncSession,
    subscription: Subscription,
    changes: list[EventChange],
    now_ts: int,
) -> list[str]:
    insights_by_event = await load_inventory_insights(
        session, [change.show for change in changes], now_ts
    )
    header = TEXT['digest_title'].format(
        label=escape(subscription.label[:200])
    )
    footer = '\n\n<i>' + INVENTORY_EXPLANATION + '</i>'
    if subscription.kind == 'actor':
        footer += '\n' + TEXT['actor_disclaimer']
    footer += '\n' + TEXT['updated_at'].format(
        date=inventory_date(max(change.show.updated_at for change in changes))
    )
    blocks = []
    maximum = min(settings.MAX_MSG_LEN, 4096)
    summary = TEXT['digest_summary'].format(total=len(changes))

    def date_key(change: EventChange) -> tuple[float, str]:
        date = parse_show_date(change.show.date)
        if date is None:
            return float('inf'), change.show.id
        if date.tzinfo is None:
            date = pytz.timezone(settings.DEFAULT_TIMEZONE).localize(date)
        return date.timestamp(), change.show.id

    for change in sorted(changes, key=date_key):
        show, previous = change.show, change.previous
        lines = [
            f'<b>{escape((show.show_name or subscription.label)[:200])}</b>',
            f'📅 {escape(performance_date(show.date))}',
        ]
        if 'new' in change.kinds:
            lines.append(TEXT['event_new'])
            lines.append(
                TEXT['inventory_unknown']
                if show.seats is None
                else TEXT['event_seats'].format(
                    previous='?', current=inventory_number(show.seats)
                )
            )
        if 'date' in change.kinds:
            lines.append(
                TEXT['event_date'].format(
                    previous=escape(performance_date(previous['date'])),
                    current=escape(performance_date(show.date)),
                )
            )
        if 'seats' in change.kinds:
            if previous['seats'] is None:
                lines.append(
                    TEXT['event_seats'].format(
                        previous='?', current=inventory_number(show.seats)
                    )
                )
            elif show.seats == 0:
                lines.append(TEXT['event_sold_out'])
            elif previous['seats'] == 0:
                lines.append(
                    TEXT['event_available'].format(
                        seats=inventory_number(show.seats)
                    )
                )
            else:
                lines.append(
                    TEXT['event_seats'].format(
                        previous=inventory_number(previous['seats']),
                        current=inventory_number(show.seats),
                    )
                )
        if 'prices' in change.kinds:
            lines.append(
                TEXT['event_prices'].format(
                    minimum=inventory_number(change.state['min_price'])
                    if change.state['min_price'] is not None
                    else '?',
                    maximum=inventory_number(change.state['max_price'])
                    if change.state['max_price'] is not None
                    else '?',
                )
            )
        if show.seats is not None:
            insights = insights_by_event[show.id]
            if insights.reason != 'unknown_inventory':
                lines.append(
                    format_inventory_insights(insights, include_counts=False)
                )
        if show.buy_link and show.buy_link.startswith('https://'):
            lines.append(
                f'<a href="{escape(show.buy_link, quote=True)}">{TEXT["buy"]}</a>'
            )
        blocks.append('\n'.join(lines))
    return split_message_by_separator(
        '\n\n'.join([header, summary, *blocks]) + footer,
        max_length=maximum,
    )


class SubscriptionService:
    def __init__(
        self, session_pool: async_sessionmaker[AsyncSession], bot: Bot
    ) -> None:
        self.session_pool = session_pool
        self.bot = bot
        self._delivery_blocked_until = 0

    async def run(self) -> None:
        while True:
            try:
                await self.process_due()
            except Exception:
                logger.exception('Subscription iteration failed')
            await asyncio.sleep(TICK_SECONDS)

    async def process_due(self, now_ts: int | None = None) -> int:
        if settings.MAINTENANCE:
            return 0
        supplied_now = now_ts
        now_ts = now_timestamp() if now_ts is None else now_ts
        if now_ts < self._delivery_blocked_until:
            return 0
        delivered = 0
        for _ in range(MAX_SUBSCRIPTIONS_PER_TICK):
            if supplied_now is None:
                now_ts = now_timestamp()
            async with self.session_pool() as session:
                row = (
                    await session.execute(
                        select(Subscription)
                        .where(
                            Subscription.enabled.is_(True),
                            Subscription.next_due_at <= now_ts,
                            or_(
                                Subscription.retry_at.is_(None),
                                Subscription.retry_at <= now_ts,
                            ),
                        )
                        .order_by(Subscription.next_due_at, Subscription.id)
                        .limit(1)
                        .with_for_update(skip_locked=True)
                    )
                ).scalar_one_or_none()
                if row is None:
                    break
                user = await session.get(User, row.user_id)
                if user is None:
                    await session.delete(row)
                    await session.commit()
                    continue
                if user.banned or user.bot_blocked:
                    row.needs_baseline = True
                    row.next_due_at = now_ts + row.interval_seconds
                    row.retry_at = None
                    await session.commit()
                    continue
                try:
                    if row.needs_baseline:
                        row.baseline = await capture_baseline(
                            session,
                            SubscriptionTarget(row.kind, row.key, row.label),
                            now_ts,
                        )
                        row.needs_baseline = False
                        changes = []
                        baseline = row.baseline
                    else:
                        changes, baseline = await detect_changes(
                            session, row, now_ts
                        )
                    if changes:
                        pages = await render_digest(
                            session, row, changes, now_ts
                        )
                        keyboard = None
                        if len(pages) > 1:
                            previous_state = _delivery_state(row)
                            subscription_id = row.id
                            # Persist pages using the same connection.
                            identifier = await save_digest(
                                session, row.user_id, pages
                            )
                            # The commit released the lock; recheck ownership.
                            row = (
                                await session.execute(
                                    select(Subscription)
                                    .where(Subscription.id == subscription_id)
                                    .with_for_update(skip_locked=True)
                                    .execution_options(populate_existing=True)
                                )
                            ).scalar_one_or_none()
                            if (
                                row is None
                                or _delivery_state(row) != previous_state
                            ):
                                continue
                            user = (
                                await session.execute(
                                    select(User)
                                    .where(User.user_id == row.user_id)
                                    .execution_options(populate_existing=True)
                                )
                            ).scalar_one_or_none()
                            if user is None or user.banned or user.bot_blocked:
                                continue
                            keyboard = subscription_digest_keyboard(
                                identifier, 0, len(pages)
                            )
                        await self.bot.send_message(
                            row.user_id,
                            pages[0],
                            parse_mode='HTML',
                            reply_markup=keyboard,
                            link_preview_options=LinkPreviewOptions(
                                is_disabled=True
                            ),
                            request_timeout=10,
                        )
                        row.last_sent_at = (
                            now_ts
                            if supplied_now is not None
                            else now_timestamp()
                        )
                        delivered += 1
                except Exception as error:
                    failed_at = (
                        now_ts if supplied_now is not None else now_timestamp()
                    )
                    row.failure_count += 1
                    delay = min(
                        3600,
                        max(1, settings.ERROR_RETRY_INTERVAL)
                        * 2 ** min(row.failure_count - 1, 6),
                    )
                    if isinstance(error, TelegramRetryAfter):
                        delay = max(1, error.retry_after)
                        self._delivery_blocked_until = failed_at + math.ceil(
                            delay
                        )
                    if isinstance(error, TelegramForbiddenError):
                        user.bot_blocked = True
                        user.bot_blocked_date = datetime.fromtimestamp(
                            now_ts, pytz.timezone(settings.DEFAULT_TIMEZONE)
                        )
                        row.needs_baseline = True
                    row.retry_at = failed_at + math.ceil(delay)
                    logger.warning(
                        'Subscription %s failed: %s',
                        row.id,
                        type(error).__name__,
                    )
                    await session.commit()
                    if isinstance(error, TelegramRetryAfter):
                        return delivered
                    continue
                row.baseline = baseline
                completed_at = (
                    now_ts if supplied_now is not None else now_timestamp()
                )
                row.next_due_at = completed_at + row.interval_seconds
                row.retry_at = None
                row.failure_count = 0
                await session.commit()
        return delivered
