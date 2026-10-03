from pathlib import Path

from tests.runtime_helpers import run_runtime_script


def test_current_speed_uses_the_same_window_as_inventory_trends(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timedelta, timezone
from math import isclose
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from services.profticket import analytics, analytics_repository as repository
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return now.astimezone(tz)
repository.datetime = analytics.datetime = Clock

cases = [
    [(now_ts - 300 - index * 1800, 200 if index == 48 else 100)
     for index in range(49)],
    [(now_ts - 1200 - index * 1900, 100 + index) for index in range(48)],
    [(now_ts - index * 60, 100 + index // 30 + max(index - 500, 0) // 5)
     for index in range(1442)],
    [(now_ts - 300, 100), (now_ts - 3900, 105)],
]

async def check(points, index):
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Show(id='test', show_id=1, show_name='Test', month=10,
                         year=2026, date=(now + timedelta(days=3)).isoformat(),
                         seats=100, updated_at=points[0][0]))
        session.commit()
        session.execute(ShowSeatHistory.__table__.insert(), [
            {'show_id': 'test', 'timestamp': stamp, 'seats': seats}
            for stamp, seats in points
        ])
        session.commit()
        class Adapter:
            async def execute(self, query):
                return session.execute(query)
        repo = repository.AnalyticsRepository(Adapter())
        trends = await repo.report('trends', 10, 2026)
        speed = await repo.report('speed', 10, 2026)
        rate = trends.insights['test'].net_rate_per_day
        assert rate is not None and rate > 0, (index, trends.insights)
        assert len(speed.results) == 1, (index, speed.results)
        assert isclose(speed.results[0][1] * 86400, rate), (index, rate, speed.results)
        if index == 0:
            assert rate == 100
    engine.dispose()

async def run():
    for index, points in enumerate(cases):
        await check(points, index)
asyncio.run(run())

shows = [Show(id=key, show_id=1, show_name='Combined') for key in ('down', 'up')]
history = [ShowSeatHistory(show_id=key, timestamp=stamp, seats=seats)
           for key, points in [('down', [(0, 100), (1800, 95), (3600, 90)]),
                               ('up', [(0, 20), (3600, 25)])]
           for stamp, seats in points]
result = analytics.top_shows_by_current_sales_speed(
    shows, history, net_rates_per_day={'down': 100, 'up': -40})
assert isclose(result[0][1] * 86400, (100 * 2 - 40) / 3)
""",
        tmp_path,
    )


def test_sql_reports_preserve_refunds_and_historical_performances(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
import json
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from services.profticket import analytics
from services.profticket.analytics_repository import AnalyticsRepository
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
session = Session(engine, expire_on_commit=False)
shows = [
    Show(id='a', show_id=17, show_name='Alpha', month=1, year=2024,
         date='2024-01-01 19:00', actors=json.dumps(['Actor', 'Actor'])),
    Show(id='b', show_id=17, show_name='Alpha', month=1, year=2024,
         date='2024-01-01 19:00', actors=json.dumps(['Actor']),
         is_deleted=True),
    Show(id='c', show_id=22, show_name='Beta', month=1, year=2024,
         date='2024-01-02 19:00', actors=json.dumps(['Actor'])),
    Show(id='d', show_id=22, show_name='Beta', month=1, year=2024,
         date='2024-01-02 19:00', actors=json.dumps(['Actor'])),
    Show(id='other', show_id=17, show_name='Other month', month=2,
         year=2024, date='2024-02-01 19:00', actors='[]'),
]
session.add_all(shows)
session.commit()
snapshots = [
    ('a', 1000, 100), ('a', 2000, 90), ('a', 2000, 80),
    ('a', 1500, None), ('a', None, 1000),
    ('b', 1000, 80), ('b', 2000, 90),
    ('c', 1000, 10), ('c', 2000, 5), ('c', 3000, 7),
    ('d', 1000, 50), ('d', 2000, 45),
]
snapshots.extend(('other', 1000 + index, 5000 - index)
                 for index in range(5000))
session.execute(ShowSeatHistory.__table__.insert(), [
    {'id': index, 'show_id': event, 'timestamp': timestamp, 'seats': seats}
    for index, (event, timestamp, seats) in enumerate(snapshots, 1)
])
session.commit()

class AsyncAdapter:
    async def execute(self, query):
        return session.execute(query)

async def run():
    repository = AnalyticsRepository(AsyncAdapter())
    assert await repository.available_months() == [(1, 2024), (2, 2024)]
    totals = await repository.performance_totals(1, 2024)
    assert len(totals) == 4
    assert not any(isinstance(row, ShowSeatHistory)
                   for row in session.identity_map.values())
    reports = {
        kind: (await repository.report(kind, 1, 2024)).results
        for kind in ('sales', 'returns', 'return_rate', 'artists', 'calendar')
    }
    assert reports['sales'] == [('Alpha', 20, 10, 17), ('Beta', 10, 8, 22)]
    assert reports['returns'] == [('Alpha', 10, 17), ('Beta', 2, 22)]
    assert reports['return_rate'] == [('Alpha', 0.5, 17), ('Beta', 0.2, 22)]
    assert reports['artists'] == [('Actor', 18)]
    assert reports['calendar']['gross_sales'] == [20, 10]
    assert reports['calendar']['net_sales'] == [10, 8]
    assert reports['calendar']['refunds'] == [10, 2]
    tracking = await repository.report('artists', 1, 2024)
    assert tracking.first_seen == {17: 1000, 22: 1000}
    assert tracking.artist_first_seen == {'Actor': 1000}
    histories = session.scalars(select(ShowSeatHistory)).all()
    functions = {
        'sales': analytics.top_shows_by_sales_detailed,
        'returns': analytics.top_shows_by_returns,
        'return_rate': analytics.top_shows_by_return_rate,
        'artists': analytics.top_artists_by_sales,
        'calendar': analytics.calendar_pace_dashboard,
    }
    for kind, function in functions.items():
        assert function(shows, histories, 1, 2024, n=10,
                        include_past_shows=True) == reports[kind]
    assert len(await repository.performance_totals(1, 2024, False)) == 3
    session.add(Show(id='earliest', show_id=17, show_name='Alpha', month=12,
                     year=2023, actors=json.dumps(['Actor']), is_deleted=True))
    session.commit()
    session.execute(ShowSeatHistory.__table__.insert(), {
        'show_id': 'earliest', 'timestamp': 1, 'seats': 100,
    })
    session.commit()
    assert (await repository.report('sales')).first_seen[17] == 1
    assert (await repository.report('artists')).artist_first_seen['Actor'] == 1

asyncio.run(run())
session.close()
engine.dispose()
""",
        tmp_path,
    )


def test_history_queries_are_bounded_and_current_reports_ignore_stale_data(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timedelta
import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from services.profticket.analytics_repository import (
    AnalyticsRepository, MAX_HISTORY_POINTS, recent_history_query,
)
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

timezone = pytz.timezone('Europe/Moscow')
now = datetime.now(timezone)
now_ts = int(now.timestamp())
past = now - timedelta(days=60)
future = now + timedelta(days=30)
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
session = Session(engine, expire_on_commit=False)
session.add_all([
    Show(id='current', show_id=1, show_name='Current', month=now.month,
         year=now.year, date=future.isoformat(), seats=10, updated_at=now_ts),
    Show(id='stale', show_id=2, show_name='Stale', month=now.month,
         year=now.year, date=future.isoformat()),
    Show(id='past', show_id=3, show_name='Past', month=past.month,
         year=past.year, date=past.isoformat(), is_deleted=True),
])
session.commit()
records = [
    {'show_id': 'current', 'timestamp': now_ts - index * 60,
     'seats': index + 10} for index in range(400)
]
records += [
    {'show_id': event, 'timestamp': now_ts - 40 * 86400 - index * 1800,
     'seats': index + 10} for event in ('stale', 'past')
    for index in range(100)
]
records += [
    {'show_id': 'current', 'timestamp': None, 'seats': 5},
    {'show_id': 'current', 'timestamp': now_ts + 60, 'seats': 0},
    {'show_id': 'current', 'timestamp': now_ts, 'seats': None},
]
session.execute(ShowSeatHistory.__table__.insert(), records)
session.commit()
current = session.scalars(recent_history_query(None, None, now_ts)).all()
assert len(current) == MAX_HISTORY_POINTS
assert {row.show_id for row in current} == {'current'}
assert min(row.timestamp for row in current) >= now_ts - 86400
assert max(row.timestamp for row in current) <= now_ts
historical = session.scalars(recent_history_query(
    past.month, past.year, now_ts, historical=True
)).all()
assert len(historical) == 49
assert {row.show_id for row in historical} == {'past'}
assert historical[-1].timestamp - historical[0].timestamp == 86400

class AsyncAdapter:
    async def execute(self, query):
        return session.execute(query)

async def run():
    repository = AnalyticsRepository(AsyncAdapter())
    speed = await repository.report('speed', now.month, now.year)
    assert [row[0] for row in speed.results] == ['Current']
    historic_speed = await repository.report('speed', past.month, past.year)
    assert [row[0] for row in historic_speed.results] == ['Past']
    session.query(ShowSeatHistory).filter_by(show_id='current').delete()
    session.commit()
    assert not (await repository.report('speed', now.month, now.year)).results
    assert not (await repository.report('prediction', now.month, now.year)).results

asyncio.run(run())
session.close()
engine.dispose()
""",
        tmp_path,
    )


def test_calendar_route_and_photo_period_preserve_fsm(tmp_path: Path) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, PhotoSize, Update, User
from services.profticket.analytics_repository import AnalyticsRepository, ReportData
from telegram.handlers import analytics_handlers as handlers
from telegram.keyboards.analytics_keyboard import analytics_main_menu_keyboard
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_RU

class OfflineSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests = []
    async def close(self):
        pass
    async def stream_content(self, *args, **kwargs):
        yield b''
    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        return Message(message_id=10, date=datetime.now(timezone.utc),
                       chat=Chat(id=5, type='private'), text=method.text)

async def run():
    offline = OfflineSession()
    bot = Bot('1:test', session=offline)
    dp = Dispatcher()
    dp.include_router(handlers.analytics_router)
    AnalyticsRepository.available_months = AsyncMock(return_value=[(1, 2024)])
    AnalyticsRepository.report = AsyncMock(return_value=ReportData({
        'dates': ['2024-01-01 19:00'], 'gross_sales': [20],
        'net_sales': [10], 'refunds': [10], 'show_names': [['Alpha <foo>']],
    }))
    calendar = LEXICON_BUTTONS_RU['/report_calendar_pace']
    assert calendar in [button.text for row in
                        analytics_main_menu_keyboard().keyboard for button in row]
    state = dp.fsm.get_context(bot, chat_id=5, user_id=5)
    async def feed(identifier, text=None, photo=None):
        message = Message(message_id=identifier, date=datetime.now(timezone.utc),
                          chat=Chat(id=5, type='private'),
                          from_user=User(id=5, is_bot=False, first_name='user'),
                          text=text, photo=photo)
        await dp.feed_update(bot, Update(update_id=identifier, message=message),
                             session=None)
    await feed(1, calendar)
    assert await state.get_state() == handlers.AnalyticsStates.choosing_month_for_top.state
    assert 'Январь 2024' in [button.text for row in
                            offline.requests[-1].reply_markup.keyboard for button in row]
    photo = [PhotoSize(file_id='test', file_unique_id='test', width=1, height=1)]
    await feed(2, photo=photo)
    assert await state.get_state() == handlers.AnalyticsStates.choosing_month_for_top.state
    assert offline.requests[-1].text == LEXICON_RU['CHOOSE_REPORT_PERIOD']
    AnalyticsRepository.report.assert_not_awaited()
    await feed(3, 'Январь 2024')
    assert await state.get_state() is None
    assert AnalyticsRepository.report.await_args.args == ('calendar', 1, 2024)
    assert LEXICON_RU['CALENDAR_PACE_REPORT_TITLE'] in offline.requests[-1].text
    assert 'Alpha &lt;foo&gt;' in offline.requests[-1].text
    await state.set_state(handlers.AnalyticsStates.choosing_month)
    await feed(4, photo=photo)
    assert await state.get_state() == handlers.AnalyticsStates.choosing_month.state
    await dp.storage.close()
    await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_admin_navigation_bypasses_report_period_handlers(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, Update, User

import telegram.filters.month_filter as month_filter
from telegram.handlers import analytics_handlers as handlers
from telegram.lexicon.lexicon_ru import LEXICON_BUTTONS_RU, LEXICON_RU
from telegram.utils.startup import setup_dispatcher

class OfflineSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests = []
    async def close(self):
        pass
    async def stream_content(self, *args, **kwargs):
        yield b''
    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        return Message(message_id=100, date=datetime.now(timezone.utc),
                       chat=Chat(id=1, type='private'), text=method.text)

class EmptyResult:
    def scalar_one(self):
        return 0
    def scalars(self):
        return self
    def all(self):
        return []

async def run():
    offline = OfflineSession()
    bot = Bot('1:test', session=offline)
    dispatcher = await setup_dispatcher()
    month_filter.get_available_months = AsyncMock(return_value=[])
    session = SimpleNamespace(
        execute=AsyncMock(return_value=EmptyResult()),
        get=AsyncMock(side_effect=lambda model, user_id:
                      SimpleNamespace(admin=user_id == 2)),
    )
    commands = {
        '/admin_menu': 'ADMIN_MENU_TITLE',
        '/admin_stats': 'ADMIN_STATS_TITLE',
        '/admin_users': 'ADMIN_USERS_TITLE',
        '/admin_prefs': 'ADMIN_PREFS_TITLE',
        '/admin_db': 'ADMIN_DB_TITLE',
    }
    identifier = 0
    try:
        for period_state in (handlers.AnalyticsStates.choosing_month_for_top,
                             handlers.AnalyticsStates.choosing_month):
            for user_id in (1, 2, 3):
                state = dispatcher.fsm.get_context(
                    bot, chat_id=user_id, user_id=user_id
                )
                for command, title in commands.items():
                    await state.set_state(period_state)
                    await state.update_data(report_type_to_generate=
                        LEXICON_BUTTONS_RU['/report_top_shows_sales'])
                    offline.requests.clear()
                    identifier += 1
                    message = Message(
                        message_id=identifier, date=datetime.now(timezone.utc),
                        chat=Chat(id=user_id, type='private'),
                        from_user=User(id=user_id, is_bot=False,
                                       first_name='User'),
                        text=LEXICON_BUTTONS_RU[command],
                    )
                    await dispatcher.feed_update(
                        bot, Update(update_id=identifier, message=message),
                        session=session,
                    )
                    if user_id in (1, 2):
                        assert len(offline.requests) == 1
                        assert LEXICON_RU[title] in offline.requests[0].text
                        if command == '/admin_menu':
                            assert await state.get_state() is None
                            assert await state.get_data() == {}
                    else:
                        assert not offline.requests
                        assert await state.get_state() == period_state.state
    finally:
        await dispatcher.storage.close()
        await bot.session.close()

asyncio.run(run())
""",
        tmp_path,
    )


def test_prediction_uses_continuous_history_and_guarded_insights(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timedelta, timezone
import pytz
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from services.profticket import analytics
from services.profticket import analytics_repository as repository_module
from services.profticket.analytics_repository import AnalyticsRepository
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return now.astimezone(tz)
analytics.datetime = repository_module.datetime = Clock
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
session = Session(engine, expire_on_commit=False)
show = Show(id='daily', show_id=1, show_name='Regular snapshots',
            month=now.month, year=now.year,
            date=(now + timedelta(days=20)).isoformat(),
            seats=100, updated_at=now_ts)
session.add(show)
session.commit()
session.execute(ShowSeatHistory.__table__.insert(), [
    {'show_id': 'daily', 'timestamp': now_ts - index * 1800,
     'seats': 100 + index} for index in range(193)
])
session.commit()
history = session.scalars(select(ShowSeatHistory)).all()
expected = analytics.shows_predicted_to_sell_out_soonest(
    [show], history, now.month, now.year, n=10
)
assert expected

class AsyncAdapter:
    async def execute(self, query):
        return session.execute(query)

async def run():
    result = await AnalyticsRepository(AsyncAdapter()).report(
        'prediction', now.month, now.year
    )
    assert result.results == expected
    assert result.insights['daily'].quality == 'good'
    assert result.insights['daily'].net_rate_per_day == 48
    assert result.insights['daily'].forecast_at == now_ts + 180000
    show.seats = None
    session.commit()
    result = await AnalyticsRepository(AsyncAdapter()).report(
        'prediction', now.month, now.year
    )
    assert not result.results
    assert result.insights['daily'].reason == 'unknown_inventory'

asyncio.run(run())
session.close()
engine.dispose()
""",
        tmp_path,
    )


def test_speed_groups_include_negative_net_rates(tmp_path: Path) -> None:
    run_runtime_script(
        r"""
from services.profticket import analytics
from telegram.db.models import Show, ShowSeatHistory

shows = [Show(id=event, show_id=1, show_name='Combined')
         for event in ('sold', 'returned')]
histories = [
    ShowSeatHistory(show_id=event, timestamp=index * 1800, seats=seats)
    for event, values in [('sold', [100, 90, 80]),
                          ('returned', [100, 105, 110])]
    for index, seats in enumerate(values)
]
result = analytics.top_shows_by_current_sales_speed(shows, histories)
assert len(result) == 1
assert abs(result[0][1] - 5 / 3600) < 1e-10
""",
        tmp_path,
    )


def test_financial_summary_rates_keep_performance_baselines(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
from services.profticket import analytics
from telegram.db.models import Show, ShowSeatHistory

shows = [Show(id=event, show_id=1, show_name='Combined')
         for event in ('large', 'small')]

def history(event, points):
    return [ShowSeatHistory(show_id=event, timestamp=timestamp, seats=seats)
            for timestamp, seats in points]

large = history('large', [(0, 1000), (1800, 990), (3600, 980)])
small = history('small', [(0, 100), (1800, 95), (3600, 90)])
summary = analytics.show_financial_summary(1, shows, large + small)
grouped = analytics.top_shows_by_current_sales_speed(shows, large + small)
assert summary['current_sales_rate_per_hour'] == 15.0
assert summary['current_sales_rate_per_hour'] == round(grouped[0][1] * 3600, 2)
assert summary['gross_sales'] == summary['net_sales'] == 30

# A two-point performance retains one interval's weight.
small = history('small', [(0, 100), (3600, 95)])
summary = analytics.show_financial_summary(1, shows, large + small)
assert summary['current_sales_rate_per_hour'] == 15.0
large = history('large', [(0, 1000), (3600, 980)])
summary = analytics.show_financial_summary(1, shows, large + small)
assert summary['current_sales_rate_per_hour'] == 12.5

# Refunds cancel an equal sales rate without erasing a measured zero.
small = history('small', [(0, 100), (3600, 120)])
summary = analytics.show_financial_summary(1, shows, large + small)
assert summary['current_sales_rate_per_hour'] == 0.0
assert summary['net_sales'] == 0
""",
        tmp_path,
    )
