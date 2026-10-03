from pathlib import Path
from textwrap import dedent

import pytest

from tests.runtime_helpers import run_runtime_script

COMMON = """
import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from config import settings
from services.subscriptions import SubscriptionService
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory, Subscription, User
from telegram.db.subscriptions import (
    SubscriptionTarget, delete_subscription, get_subscription,
    list_subscriptions, save_subscription, search_targets, update_subscription,
)

NOW = int(datetime(2026, 10, 2, 9, tzinfo=timezone.utc).timestamp())
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
sessions = sessionmaker(engine, expire_on_commit=False)
statements = []

class Session:
    def __init__(self):
        self.sync = sessions()

    async def __aenter__(self):
        return self

    async def __aexit__(self, kind, value, traceback):
        if kind:
            self.sync.rollback()
        self.sync.close()

    async def execute(self, statement):
        statements.append(statement)
        return self.sync.execute(statement)

    async def get(self, model, key):
        return self.sync.get(model, key)

    async def delete(self, row):
        self.sync.delete(row)

    async def commit(self):
        self.sync.commit()

def show(identifier='first', group=1, seats=10, actors=None, **values):
    data = dict(
        id=identifier, show_id=group, show_name='Test Show',
        date='03.10.2026, 19:00', month=10, year=2026,
        seats=seats, actors=json.dumps(actors or ['Test Actor']),
        updated_at=NOW, buy_link='https://tickets.test',
    )
    data.update(values)
    return Show(**data)

with sessions() as session:
    session.add_all([User(user_id=1), User(user_id=2), show()])
    session.commit()

TARGET = SubscriptionTarget('show', 'show:1', 'Test Show')

async def subscribe(target=TARGET, user=1, now=NOW):
    async with Session() as session:
        return await save_subscription(session, user, target, 1800, now)

def change_inventory(seats, timestamp, identifier='first'):
    with sessions() as session:
        row = session.get(Show, identifier)
        row.seats = seats
        row.updated_at = timestamp
        session.commit()

def stored(identifier):
    with sessions() as session:
        return session.get(Subscription, identifier)

bot = AsyncMock()
service = SubscriptionService(Session, bot)
"""


def test_management_is_idempotent_owner_scoped_and_rebases_resume(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            with sessions() as session:
                session.add(show('historic', group=2,
                    date='01.09.2026, 19:00', month=9, is_deleted=True,
                    actors=['Old Actor', 'Народный артист России']))
                session.add(show('fallback', group=None))
                session.commit()
            async with Session() as session:
                assert await search_targets(session, 'actor', '...', now_ts=NOW) == []
                assert await search_targets(session, 'actor', 'Народный', now_ts=NOW) == []
                actors = await search_targets(session, 'actor', 'Old', now_ts=NOW)
                assert [target.key for target in actors] == ['old actor']
                actor = await save_subscription(session, 1, actors[0], 3600, NOW)
                assert actor.baseline == {'events': {}, 'waiting': []}
                targets = await search_targets(session, 'show', 'Test', now_ts=NOW)
                assert {target.key for target in targets} == {'show:1', 'event:fallback'}
            row = await subscribe()
            same = await subscribe(now=NOW + 100)
            assert row.id == same.id
            assert same.next_due_at == NOW + 1800
            with sessions() as session:
                session.get(Show, 'first').show_name = 'Updated Show'
                session.commit()
            renamed = await subscribe(now=NOW + 200)
            assert renamed.id == row.id and renamed.label == 'Updated Show'
            async with Session() as session:
                assert len(await list_subscriptions(session, 1)) == 2
                assert await get_subscription(session, 2, row.id) is None
                assert await update_subscription(session, 2, row.id, enabled=False) is None
                assert not await delete_subscription(session, 2, row.id)
                await update_subscription(session, 1, row.id, enabled=False, now_ts=NOW + 10)
            change_inventory(7, NOW + 100)
            async with Session() as session:
                resumed = await update_subscription(session, 1, row.id, enabled=True, now_ts=NOW + 100)
                assert resumed.baseline['events']['first']['seats'] == 7
                assert resumed.next_due_at == NOW + 1900
                assert await delete_subscription(session, 1, row.id)
                assert await get_subscription(session, 1, row.id) is None
            assert not bot.send_message.await_count
        asyncio.run(check())
    """),
        tmp_path,
    )


@pytest.mark.parametrize(
    ('field', 'initial', 'concurrent'),
    [('interval_seconds', 1800, 21600), ('enabled', False, True)],
)
def test_management_refreshes_cached_settings_before_updating(
    tmp_path: Path, field: str, initial: int | bool, concurrent: int | bool
) -> None:
    run_runtime_script(
        COMMON
        + dedent(f"""
        async def check():
            row = await subscribe()
            with sessions() as session:
                setattr(session.get(Subscription, row.id), {field!r}, {initial!r})
                session.commit()
            async with Session() as pending:
                cached = await get_subscription(pending, 1, row.id)
                assert getattr(cached, {field!r}) == {initial!r}
                with sessions() as other:
                    setattr(other.get(Subscription, row.id), {field!r}, {concurrent!r})
                    other.commit()
                assert getattr(cached, {field!r}) == {initial!r}
                updated = await update_subscription(
                    pending, 1, row.id, {field}={initial!r}, now_ts=NOW + 100,
                )
                assert updated is cached
                assert getattr(stored(row.id), {field!r}) == {initial!r}
                assert updated.user_id == 1
                assert await get_subscription(pending, 2, row.id) is None
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_digests_only_include_changes_and_new_actor_dates(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            actor = await subscribe(SubscriptionTarget('actor', 'test actor', 'Test Actor'))
            assert await service.process_due(NOW + 1800) == 0
            assert not bot.send_message.await_count
            with sessions() as session:
                session.add(show('new_date', group=2, updated_at=NOW + 3600))
                session.add(show('not_exact', group=3, actors=['Test Actor Jr'], updated_at=NOW + 3600))
                session.commit()
            change_inventory(5, NOW + 3600)
            assert await service.process_due(NOW + 3600) == 1
            sent = bot.send_message.await_args
            assert sent.args[0] == 1
            assert '10 → 5' in sent.args[1]
            assert 'Новая дата' in sent.args[1]
            assert 'Изменений: 2.' in sent.args[1]
            assert sent.kwargs['request_timeout'] == 10
            assert set(stored(actor.id).baseline['events']) == {'first', 'new_date'}
            assert await service.process_due(NOW + 3601) == 0
            locks = [str(statement.compile(dialect=postgresql.dialect()))
                     for statement in statements if getattr(statement, '_for_update_arg', None) is not None]
            assert any('FOR UPDATE SKIP LOCKED' in statement for statement in locks)
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_stale_and_unknown_inventory_never_fake_a_change_or_cancellation(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            row = await subscribe()
            change_inventory(0, NOW - 10000)
            assert await service.process_due(NOW + 1800) == 0
            assert stored(row.id).baseline['events']['first']['seats'] == 10
            change_inventory(None, NOW + 3600)
            assert await service.process_due(NOW + 3600) == 0
            assert stored(row.id).baseline['events']['first']['seats'] == 10
            with sessions() as session:
                session.get(Show, 'first').is_deleted = True
                session.commit()
            assert await service.process_due(NOW + 5400) == 0
            assert not bot.send_message.await_count
            assert await service.process_due(NOW + 4 * 86400) == 0
            assert stored(row.id).baseline['events'] == {}
            with sessions() as session:
                session.add(show('stale_new', group=5, seats=8, updated_at=NOW - 10000))
                session.commit()
            target = SubscriptionTarget('show', 'show:5', 'Test Show')
            waiting = await subscribe(target)
            assert waiting.baseline['events'] == {}
            assert waiting.baseline['waiting'] == ['stale_new']
            change_inventory(4, NOW + 1800, 'stale_new')
            assert await service.process_due(NOW + 1800) == 0
            assert stored(waiting.id).baseline['events']['stale_new']['seats'] == 4
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_failed_delivery_preserves_baseline_and_retries_after_restart(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            row = await subscribe()
            initial = deepcopy(row.baseline)
            change_inventory(0, NOW + 1800)
            method = SendMessage(chat_id=1, text='Test')
            bot.send_message.side_effect = TelegramRetryAfter(method, 'Slow down', 120)
            assert await service.process_due(NOW + 1800) == 0
            failed = stored(row.id)
            assert failed.baseline == initial
            assert failed.next_due_at == NOW + 1800
            assert failed.retry_at == NOW + 1920
            assert await service.process_due(NOW + 1919) == 0
            assert bot.send_message.await_count == 1
            bot.send_message.side_effect = None
            restarted = SubscriptionService(Session, bot)
            assert await restarted.process_due(NOW + 1920) == 1
            assert stored(row.id).baseline['events']['first']['seats'] == 0
            assert stored(row.id).failure_count == 0
            change_inventory(5, NOW + 3720)
            bot.send_message.side_effect = TelegramForbiddenError(method, 'Blocked')
            assert await service.process_due(NOW + 3720) == 0
            assert stored(row.id).baseline['events']['first']['seats'] == 0
            with sessions() as session:
                user = session.get(User, 1)
                assert user.bot_blocked and user.bot_blocked_date is not None
            assert stored(row.id).needs_baseline
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_first_confirmed_inventory_is_reported_without_claiming_a_return(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            change_inventory(None, NOW)
            row = await subscribe()
            assert row.baseline['events']['first']['seats'] is None
            change_inventory(5, NOW + 1800)
            assert await service.process_due(NOW + 1800) == 1
            message = bot.send_message.await_args.args[1]
            assert '? → 5' in message
            assert 'снова' not in message
            with sessions() as session:
                session.add(show('zero', group=2, seats=None))
                session.commit()
            zero = await subscribe(SubscriptionTarget('show', 'show:2', 'Test Show'))
            change_inventory(0, NOW + 1800, 'zero')
            assert await service.process_due(NOW + 1800) == 1
            message = bot.send_message.await_args.args[1]
            assert '? → 0' in message
            assert 'больше нет' not in message
            assert stored(zero.id).baseline['events']['zero']['seats'] == 0
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_rate_limit_pauses_all_deliveries_until_retry_after(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            first = await subscribe()
            second = await subscribe(SubscriptionTarget('actor', 'test actor', 'Test Actor'))
            change_inventory(5, NOW + 1800)
            method = SendMessage(chat_id=1, text='Test')
            bot.send_message.side_effect = TelegramRetryAfter(method, 'Slow down', 120)
            assert await service.process_due(NOW + 1800) == 0
            assert bot.send_message.await_count == 1
            assert stored(first.id).baseline['events']['first']['seats'] == 10
            assert stored(second.id).baseline['events']['first']['seats'] == 10
            assert await service.process_due(NOW + 1919) == 0
            assert bot.send_message.await_count == 1
            bot.send_message.side_effect = None
            assert await service.process_due(NOW + 1920) == 2
            assert bot.send_message.await_count == 3
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_bans_blocking_maintenance_and_pause_suppress_deliveries(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            row = await subscribe()
            change_inventory(1, NOW + 1800)
            settings.MAINTENANCE = True
            assert await service.process_due(NOW + 1800) == 0
            assert stored(row.id).next_due_at == NOW + 1800
            settings.MAINTENANCE = False
            with sessions() as session:
                session.get(User, 1).banned = True
                session.commit()
            assert await service.process_due(NOW + 1800) == 0
            with sessions() as session:
                user = session.get(User, 1)
                user.banned = False
                user.bot_blocked = True
                session.commit()
            assert await service.process_due(NOW + 3600) == 0
            change_inventory(0, NOW + 5400)
            with sessions() as session:
                session.get(User, 1).bot_blocked = False
                session.commit()
            assert await service.process_due(NOW + 5400) == 0
            assert stored(row.id).baseline['events']['first']['seats'] == 0
            async with Session() as session:
                await update_subscription(session, 1, row.id, enabled=False)
            assert await service.process_due(NOW + 10000) == 0
            assert not bot.send_message.await_count
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_large_digest_preserves_every_change_across_restarts_and_new_digests(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        from html.parser import HTMLParser
        from telegram.db.models import SubscriptionDigest
        from telegram.db.subscriptions import get_digest
        from telegram.keyboards.subscription_keyboard import SubscriptionAction

        class VisibleText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = ''
            def handle_data(self, text):
                self.text += text

        async def check():
            with sessions() as session:
                session.add_all([show(f'event_{number}', show_name=f'Event <{number}> 😀')
                                 for number in range(50)])
                session.commit()
            row = await subscribe()
            with sessions() as session:
                for event in session.scalars(select(Show)):
                    event.seats = 5
                    event.updated_at = NOW + 1800
                session.commit()
            assert await service.process_due(NOW + 1800) == 1
            message = bot.send_message.await_args.args[1]
            assert 'Изменений: 51.' in message
            assert all(event['seats'] == 5 for event in stored(row.id).baseline['events'].values())
            assert bot.send_message.await_count == 1
            keyboard = bot.send_message.await_args.kwargs['reply_markup']
            action = SubscriptionAction.unpack(keyboard.inline_keyboard[0][-1].callback_data)
            assert action.action == 'digest' and action.value == '1'
            identifier = int(action.reference)
            async with Session() as fresh:
                digest = await get_digest(fresh, 1, identifier)
                assert digest is not None and len(digest.pages) > 1
                assert digest.pages[0] == message
                old_pages = list(digest.pages)
                assert await get_digest(fresh, 2, identifier) is None
            combined = ''
            for page in old_pages:
                parser = VisibleText()
                parser.feed(page)
                assert len(parser.text.encode('utf-16-le')) // 2 <= settings.MAX_MSG_LEN
                combined += parser.text
            for number in range(50):
                assert combined.count(f'Event <{number}> 😀') == 1
            assert combined.count('10 → 5') == 51

            restarted = SubscriptionService(Session, bot)
            with sessions() as session:
                for event in session.scalars(select(Show)):
                    event.seats = 2
                    event.updated_at = NOW + 3600
                session.commit()
            assert await restarted.process_due(NOW + 3600) == 1
            assert bot.send_message.await_count == 2
            async with Session() as fresh:
                assert (await get_digest(fresh, 1, identifier)).pages == old_pages
                new_digest = (await fresh.execute(select(SubscriptionDigest).where(
                    SubscriptionDigest.id != identifier))).scalar_one()
                assert '5 → 2' in ''.join(new_digest.pages)
            assert await restarted.process_due(NOW + 5400) == 0
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_digest_pages_are_durable_before_send_and_failure_keeps_baseline(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        from telegram.db.subscriptions import get_digest
        from telegram.keyboards.subscription_keyboard import SubscriptionAction

        class Stopped(BaseException):
            pass

        async def check():
            with sessions() as session:
                session.add_all([show(f'event_{number}') for number in range(50)])
                session.commit()
            row = await subscribe()
            with sessions() as session:
                for event in session.scalars(select(Show)):
                    event.seats = 5
                    event.updated_at = NOW + 1800
                session.commit()
            identifier = None
            async def stopped_send(*args, **kwargs):
                nonlocal identifier
                action = SubscriptionAction.unpack(
                    kwargs['reply_markup'].inline_keyboard[0][-1].callback_data)
                identifier = int(action.reference)
                async with Session() as fresh:
                    assert (await get_digest(fresh, 1, identifier)).pages[0] == args[1]
                raise Stopped()
            bot.send_message.side_effect = stopped_send
            try:
                await service.process_due(NOW + 1800)
            except Stopped:
                pass
            else:
                raise AssertionError('The simulated interruption must propagate')
            assert all(event['seats'] == 10 for event in stored(row.id).baseline['events'].values())
            async with Session() as fresh:
                assert await get_digest(fresh, 1, identifier) is not None
            bot.send_message.side_effect = RuntimeError('send failed')
            assert await service.process_due(NOW + 1800) == 0
            assert all(event['seats'] == 10 for event in stored(row.id).baseline['events'].values())
        asyncio.run(check())
    """),
        tmp_path,
    )


@pytest.mark.parametrize('concurrent', ['none', 'pause', 'delivered'])
def test_large_digest_uses_one_connection_and_rechecks_after_archiving(
    tmp_path: Path, concurrent: str
) -> None:
    run_runtime_script(
        COMMON.replace(
            "engine = create_engine('sqlite:///:memory:')",
            'from sqlalchemy.pool import QueuePool\n'
            "engine = create_engine('sqlite:///:memory:', poolclass=QueuePool, "
            'pool_size=1, max_overflow=0, pool_timeout=0.05)',
        )
        + f'\nCONCURRENT = {concurrent!r}\n'
        + dedent("""
        import services.subscriptions as worker

        async def check():
            with sessions() as session:
                session.add_all([show(f'event_{number}') for number in range(50)])
                session.commit()
            row = await subscribe()
            with sessions() as session:
                for event in session.scalars(select(Show)):
                    event.seats = 5
                    event.updated_at = NOW + 1800
                session.commit()
            original_save = worker.save_digest
            async def archive(*args):
                identifier = await original_save(*args)
                if CONCURRENT != 'none':
                    with sessions() as session:
                        other = session.get(Subscription, row.id)
                        if CONCURRENT == 'pause':
                            other.enabled = False
                        else:
                            baseline = deepcopy(other.baseline)
                            for event in baseline['events'].values():
                                event['seats'] = 5
                            other.baseline = baseline
                            other.next_due_at = NOW + 3600
                        session.commit()
                return identifier
            worker.save_digest = archive
            delivered = await service.process_due(NOW + 1800)
            assert delivered == (1 if CONCURRENT == 'none' else 0)
            assert bot.send_message.await_count == delivered
            assert stored(row.id).failure_count == 0
            if CONCURRENT == 'pause':
                assert not stored(row.id).enabled
                assert stored(row.id).baseline['events']['first']['seats'] == 10
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_digest_shows_nearest_dates_first_across_months(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            with sessions() as session:
                first = session.get(Show, 'first')
                first.date = '30.10.2026, 19:00'
                first.show_name = 'October'
                session.add_all([
                    show('october_31', date='2026-10-31T18:00:00+00:00',
                         show_name='October31'),
                    show('november', date='02.11.2026, 19:00', month=11,
                         show_name='November'),
                    show('december', date='01.12.2026, 19:00', month=12,
                         show_name='December'),
                    show('past', date='01.10.2026, 19:00', show_name='Past'),
                ])
                session.commit()
            row = await subscribe()
            with sessions() as session:
                for event in session.scalars(select(Show)):
                    event.seats = 5
                    event.updated_at = NOW + 1800
                session.commit()
            assert await service.process_due(NOW + 1800) == 1
            message = bot.send_message.await_args.args[1]
            positions = [message.index(f'<b>{name}</b>') for name in
                         ('October', 'October31', 'November', 'December')]
            assert positions == sorted(positions)
            assert '<b>Past</b>' not in message

            with sessions() as session:
                session.add_all([
                    show(f'late_{number}', date='02.12.2026, 19:00', month=12,
                         show_name=f'Late_{number}', updated_at=NOW + 3600)
                    for number in range(50)
                ])
                for event in session.scalars(select(Show)):
                    event.seats = 4
                    event.updated_at = NOW + 3600
                session.commit()
            settings.MAX_MSG_LEN = 700
            assert await service.process_due(NOW + 3600) == 1
            message = bot.send_message.await_args.args[1]
            assert '<b>October</b>' in message
            from html import unescape
            import re
            from telegram.db.subscriptions import get_digest
            from telegram.keyboards.subscription_keyboard import SubscriptionAction
            action = SubscriptionAction.unpack(
                bot.send_message.await_args.kwargs['reply_markup']
                .inline_keyboard[0][-1].callback_data)
            async with Session() as fresh:
                pages = (await get_digest(fresh, 1, int(action.reference))).pages
            combined = ''.join(pages)
            positions = [combined.index(f'<b>{name}</b>') for name in
                         ('October', 'October31', 'November', 'December', 'Late_0')]
            assert positions == sorted(positions)
            for page in pages:
                visible = unescape(re.sub(r'<[^>]*>', '', page))
                assert len(visible.encode('utf-16-le')) // 2 <= 700
            assert 'past' not in stored(row.id).baseline['events']
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_subscription_migration_builds_postgres_schema_offline(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        """
import io
from pathlib import Path

from alembic import command
from alembic.config import Config

root = Path(__import__('main').__file__).parent
output = io.StringIO()
config = Config(str(root / 'alembic.ini'), output_buffer=output)
config.set_main_option('script_location', str(root / 'alembic'))
command.upgrade(config, 'head', sql=True)
sql = output.getvalue()
assert 'CREATE TABLE subscriptions' in sql
assert 'UNIQUE (user_id, kind, key)' in sql
assert 'FOREIGN KEY(user_id) REFERENCES users (user_id) ON DELETE CASCADE' in sql
assert 'ix_subscriptions_due' in sql
assert 'baseline JSON NOT NULL' in sql
assert 'c920bf740e61' in sql
assert 'CREATE TABLE subscription_digests' in sql
assert 'pages JSON NOT NULL' in sql
assert 'ix_subscription_digests_user_id' in sql
assert 'd734c2a8f190' in sql

import importlib.util
from sqlalchemy import create_engine, inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations

path = root / 'alembic/versions/d734c2a8f190_add_subscription_digests.py'
spec = importlib.util.spec_from_file_location('digest_migration', path)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
engine = create_engine('sqlite:///:memory:')
with engine.begin() as connection:
    connection.exec_driver_sql('PRAGMA foreign_keys = ON')
    connection.exec_driver_sql('CREATE TABLE users (user_id INTEGER PRIMARY KEY)')
    connection.exec_driver_sql('INSERT INTO users VALUES (1)')
    migration.op = Operations(MigrationContext.configure(connection))
    migration.upgrade()
    connection.exec_driver_sql(
        'INSERT INTO subscription_digests (user_id, pages) VALUES (?, ?)',
        (1, '["first", "second"]'))
    connection.exec_driver_sql('DELETE FROM users WHERE user_id = 1')
    assert connection.exec_driver_sql('SELECT COUNT(*) FROM subscription_digests').scalar() == 0
    migration.downgrade()
    assert 'subscription_digests' not in inspect(connection).get_table_names()
engine.dispose()
""",
        tmp_path,
    )


def test_retry_cooldown_starts_when_the_request_fails(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        from unittest.mock import patch
        import services.subscriptions as worker

        async def check():
            row = await subscribe()
            change_inventory(5, NOW + 1800)
            clock = [NOW + 1800]
            method = SendMessage(chat_id=1, text='Test')
            async def slow_failure(*args, **kwargs):
                clock[0] += 50
                raise TelegramRetryAfter(method, 'Slow down', 120)
            bot.send_message.side_effect = slow_failure
            with patch.object(worker, 'now_timestamp', lambda: clock[0]):
                assert await service.process_due() == 0
            assert stored(row.id).retry_at == NOW + 1970
            assert await service.process_due(NOW + 1969) == 0
            bot.send_message.side_effect = None
            assert await service.process_due(NOW + 1970) == 1
        asyncio.run(check())
    """),
        tmp_path,
    )


def test_new_stale_event_notifies_when_its_first_fresh_snapshot_arrives(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
        async def check():
            row = await subscribe(SubscriptionTarget('actor', 'test actor', 'Test Actor'))
            with sessions() as session:
                session.add(show('new', group=2, seats=8, updated_at=NOW - 10000))
                session.commit()
            assert await service.process_due(NOW + 1800) == 0
            assert stored(row.id).baseline['waiting'] == []
            assert 'new' not in stored(row.id).baseline['events']
            change_inventory(7, NOW + 3600, 'new')
            assert await service.process_due(NOW + 3600) == 1
            assert 'Новая дата' in bot.send_message.await_args.args[1]
            assert stored(row.id).baseline['events']['new']['seats'] == 7
            assert bot.send_message.await_count == 1
        asyncio.run(check())
    """),
        tmp_path,
    )
