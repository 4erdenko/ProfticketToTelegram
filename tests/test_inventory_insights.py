from pathlib import Path

from tests.runtime_helpers import run_runtime_script


def test_sampled_history_keeps_the_first_observation_of_a_new_event(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from services.profticket import analytics_repository as repository
from services.profticket.insights import analyze_inventory
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

now = datetime(2026, 10, 3, 12, 30, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
event = now + timedelta(days=3)
class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return now.astimezone(tz)
repository.datetime = Clock
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
with Session(engine, expire_on_commit=False) as session:
    show = Show(id='new', show_id=1, show_name='New', seats=90,
                date=event.isoformat(), month=10, year=2026, updated_at=now_ts)
    session.add(show)
    session.commit()
    records = [
        {'show_id': show.id, 'timestamp': now_ts - 5400, 'seats': 200},
        {'show_id': show.id, 'timestamp': now_ts - 5400, 'seats': 100},
    ] + [
        {'show_id': show.id, 'timestamp': now_ts - 5400 + index * 600, 'seats': 90}
        for index in range(1, 10)
    ]
    session.execute(ShowSeatHistory.__table__.insert(), records)
    session.commit()
    raw = session.scalars(select(ShowSeatHistory)).all()
    expected = analyze_inventory(raw, now_ts, event)
    assert expected.net_rate_per_day == 160
    assert expected.trend == 'depleting'
    sampled = session.scalars(repository.insights_history_query([show.id], now_ts)).all()
    assert sampled[0].timestamp == now_ts - 5400
    assert sampled[0].seats == 100
    assert len(sampled) == len({point.timestamp for point in sampled})

    class Adapter:
        async def execute(self, query):
            return session.execute(query)

    async def check():
        loaded = await repository.load_inventory_insights(Adapter(), [show], now_ts)
        assert loaded[show.id] == expected
        speed = await repository.AnalyticsRepository(Adapter()).report('speed', 10, 2026)
        assert len(speed.results) == 1
        assert speed.results[0][1] * 86400 == 160
    asyncio.run(check())
engine.dispose()
""",
        tmp_path,
        {'UPDATE_INTERVAL': '600'},
    )


def test_rates_use_elapsed_time_and_facts_keep_both_directions(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from services.profticket.insights import analyze_inventory, time_weighted_rate

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
def row(hours, seats, identifier=1):
    return SimpleNamespace(timestamp=now_ts + hours * 3600,
                           seats=seats, id=identifier)
history = [row(-6, 100), row(-5, 90), row(0, 80)]
assert time_weighted_rate(history, now_ts) == 80
result = analyze_inventory(history, now_ts, now + timedelta(days=10))
assert result.net_rate_per_day == 80
assert (result.decreases, result.increases) == (20, 0)
assert result.forecast_at is None
assert result.reason == 'insufficient_history'

history = [row(-3, 100), row(-2, 90), row(-1, 95), row(0, 85)]
result = analyze_inventory(history, now_ts)
assert (result.decreases, result.increases) == (20, 5)
assert result.net_rate_per_day == 120
assert result.trend == 'depleting'

history = [row(-2, 100), row(0, 80, 2), row(0, 90, 3), row(1, 0),
           row(-1, None), row(-1, -5),
           SimpleNamespace(timestamp=None, seats=0, id=8)]
result = analyze_inventory(list(reversed(history)), now_ts)
assert result.latest_seats == 90
assert (result.decreases, result.increases) == (10, 0)
assert result.net_rate_per_day == 120
assert analyze_inventory([], now_ts).reason == 'no_observations'

# The predecessor belongs to the actual observed interval across the boundary.
history = [row(-25, 100), row(-23, 96), row(-18, 86),
           row(-12, 74), row(-6, 62), row(0, 50)]
result = analyze_inventory(history, now_ts)
assert result.decreases == 50
assert result.net_rate_per_day == 48
""",
        tmp_path,
    )


def test_forecasts_require_fresh_continuous_stable_history(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytz
from services.profticket.insights import (
    MAX_OBSERVATION_AGE, analyze_inventory,
)

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
event = now + timedelta(days=10)
history = [SimpleNamespace(timestamp=now_ts - index * 3600,
                           seats=100 + index, id=index)
           for index in range(97)]
result = analyze_inventory(history, now_ts, event)
assert result.quality == 'good'
assert result.reason == 'ok'
assert result.net_rate_per_day == result.previous_rate_per_day == 24
assert result.forecast_at == now_ts + 100 * 3600
assert result.forecast_earliest == result.forecast_latest == result.forecast_at
naive_event = event.astimezone(pytz.timezone('Europe/Moscow')).replace(tzinfo=None)
assert analyze_inventory(history, now_ts, naive_event) == result

stale = analyze_inventory(history, now_ts + MAX_OBSERVATION_AGE + 1, event)
assert stale.quality == 'stale'
assert stale.net_rate_per_day is None and stale.forecast_at is None
past = analyze_inventory(history, now_ts, now - timedelta(seconds=1))
assert past.quality == 'past' and past.forecast_at is None
assert analyze_inventory(history, now_ts, now + timedelta(hours=4)).reason == 'forecast_beyond_horizon'

gapped = [row for row in history if not 4 <= row.id < 24]
result = analyze_inventory(gapped, now_ts, event)
assert result.quality == 'gapped' and result.forecast_at is None
jumped = history + [SimpleNamespace(timestamp=now_ts, seats=200, id=1000)]
result = analyze_inventory(jumped, now_ts, event)
assert result.quality == 'inventory_jump' and result.forecast_at is None

# A quota change before a clean day no longer invalidates the new segment.
recovered = history[:31] + [SimpleNamespace(
    timestamp=now_ts - 31 * 3600, seats=80, id=1001,
)]
result = analyze_inventory(recovered, now_ts, event)
assert result.quality == 'good' and result.forecast_at is not None
assert result.previous_rate_per_day is None
recovered = history[:31] + [SimpleNamespace(
    timestamp=now_ts - 48 * 3600, seats=200, id=1001,
)]
result = analyze_inventory(recovered, now_ts, event)
assert result.quality == 'good' and result.forecast_at is not None

flat = [SimpleNamespace(timestamp=row.timestamp, seats=100, id=row.id)
        for row in history]
result = analyze_inventory(flat, now_ts, event)
assert result.net_rate_per_day == 0
assert result.trend == 'stable' and result.reason == 'no_depletion'
returns = [SimpleNamespace(timestamp=row.timestamp, seats=200 - row.id,
                           id=row.id) for row in history[:25]]
result = analyze_inventory(returns, now_ts, event)
assert result.net_rate_per_day == -24
assert result.trend == 'replenishing' and result.forecast_at is None
empty = history + [SimpleNamespace(timestamp=now_ts, seats=0, id=1000)]
assert analyze_inventory(empty, now_ts, event).forecast_at is None

volatile = [SimpleNamespace(timestamp=now_ts - index * 3600,
                           seats=100 + (20 if index >= 12 else 0), id=index)
            for index in range(25)]
result = analyze_inventory(volatile, now_ts, event)
assert result.reason == 'volatile_rate' and result.forecast_at is None
""",
        tmp_path,
    )


def test_comparable_days_explain_acceleration_and_slowdown(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from services.profticket.insights import analyze_inventory

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
def history(current_per_hour, previous_per_hour):
    return [SimpleNamespace(
        timestamp=now_ts - index * 3600,
        seats=100 + min(index, 24) * current_per_hour
            + max(index - 24, 0) * previous_per_hour,
        id=index,
    ) for index in range(49)]
accelerated = analyze_inventory(history(2, 1), now_ts,
                                now + timedelta(days=10))
assert accelerated.trend == 'accelerating'
assert accelerated.net_rate_per_day == 48
assert accelerated.previous_rate_per_day == 24
assert accelerated.forecast_earliest == now_ts + 50 * 3600
assert accelerated.forecast_latest == now_ts + 100 * 3600
slower = analyze_inventory(history(1, 2), now_ts, now + timedelta(days=10))
assert slower.trend == 'slowing'
assert slower.net_rate_per_day == 24
assert slower.previous_rate_per_day == 48
partial = analyze_inventory(history(2, 1)[:26], now_ts,
                            now + timedelta(days=10))
assert partial.previous_rate_per_day is None
assert partial.trend == 'depleting'
""",
        tmp_path,
    )


def test_freshness_follows_the_configured_polling_interval(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from services.profticket.insights import MAX_OBSERVATION_AGE, analyze_inventory

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
assert MAX_OBSERVATION_AGE == 14400
history = [SimpleNamespace(timestamp=now_ts - (3 + index * 2) * 3600,
                           seats=100 + index * 2, id=index)
           for index in range(37)]
result = analyze_inventory(history, now_ts, now + timedelta(days=10))
assert result.quality == 'good'
assert result.forecast_at == now_ts + 97 * 3600
assert result.net_rate_per_day == 24
""",
        tmp_path,
        {'UPDATE_INTERVAL': '7200'},
    )


def test_bounded_repository_keeps_daily_facts_and_unknown_events(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from services.profticket import analytics_repository as module
from services.profticket.analytics_repository import (
    AnalyticsRepository, daily_inventory_totals_query, insights_history_query,
)
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return now.astimezone(tz)
module.datetime = Clock
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
session = Session(engine, expire_on_commit=False)
future = (now + timedelta(days=10)).isoformat()
session.add_all([
    Show(id='clean', show_id=1, show_name='Clean', date=future, month=10,
         year=2026, seats=100, updated_at=now_ts),
    Show(id='unknown', show_id=2, show_name='Unknown', date=future, month=10,
         year=2026, seats=None, updated_at=now_ts),
    Show(id='new', show_id=6, show_name='New', date=future, month=10,
         year=2026, seats=5, updated_at=now_ts),
    Show(id='stale', show_id=3, show_name='Stale', date=future, month=10,
         year=2026, seats=100, updated_at=now_ts - 86400),
    Show(id='past', show_id=4, show_name='Past', month=10, year=2026,
         date=(now - timedelta(hours=1)).isoformat(), seats=100,
         updated_at=now_ts),
    Show(id='removed', show_id=5, show_name='Removed', date=future, month=10,
         year=2026, seats=100, updated_at=now_ts, is_deleted=True),
])
session.commit()
session.execute(ShowSeatHistory.__table__.insert(), [
    {'show_id': 'clean', 'timestamp': now_ts - index * 600,
     'seats': 100 + index} for index in range(1153)
])
session.commit()
sampled = session.scalars(insights_history_query(['clean'], now_ts)).all()
assert len(sampled) <= 340
assert sampled[0].timestamp == now_ts - 7 * 86400
assert sampled[-1].timestamp - sampled[0].timestamp >= 6 * 86400
assert {row.show_id for row in sampled} == {'clean'}
assert {now_ts - 86400, now_ts - 2 * 86400} <= {
    row.timestamp for row in sampled
}
for query in (insights_history_query(['clean'], now_ts),
              daily_inventory_totals_query(['clean'], now_ts)):
    str(query.compile(dialect=postgresql.dialect()))

class Adapter:
    async def execute(self, statement):
        return session.execute(statement)
async def run():
    repository = AnalyticsRepository(Adapter())
    report = await repository.report('trends', 10, 2026, n=10)
    assert [show.id for show in report.results] == ['clean', 'new', 'stale', 'unknown']
    item = report.insights['clean']
    assert item.net_rate_per_day == 144
    assert item.decreases == 144
    assert item.increases == 0
    assert item.forecast_at is not None
    assert report.insights['unknown'].reason == 'unknown_inventory'
    assert report.insights['new'].latest_seats == 5
    assert report.insights['new'].reason == 'no_observations'
    assert report.insights['new'].forecast_at is None
    assert report.insights['stale'].forecast_at is None
    assert report.insights['stale'].reason == 'stale_data'
    assert not (await repository.report('trends', 9, 2026)).results
    assert [row[0] for row in (await repository.report('speed', 10, 2026)).results] == ['Clean']
    session.get(Show, 'clean').updated_at = now_ts - 7200
    session.commit()
    assert not (await repository.report('speed', 10, 2026)).results
    session.get(Show, 'clean').updated_at = now_ts
    session.commit()

    # A return/quota move inside one bucket must remain visible in daily facts.
    session.execute(ShowSeatHistory.__table__.insert(), [
        {'show_id': 'clean', 'timestamp': now_ts - 300, 'seats': 150},
        {'show_id': 'clean', 'timestamp': now_ts - 300, 'seats': 160},
        {'show_id': 'clean', 'timestamp': now_ts + 60, 'seats': 0},
    ])
    session.commit()
    report = await repository.report('trends', 10, 2026)
    item = report.insights['clean']
    assert item.decreases == 203
    assert item.increases == 59
    assert item.reason == 'inventory_jump'
    assert item.forecast_at is None
    assert item.latest_seats == 100

asyncio.run(run())
session.close()
engine.dispose()
""",
        tmp_path,
    )


def test_bounded_history_preserves_previous_day_quota_reset(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from services.profticket.analytics_repository import (
    insights_history_query, load_inventory_insights,
)
from services.profticket.insights import analyze_inventory
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
session = Session(engine, expire_on_commit=False)
show = Show(id='reset', seats=100, updated_at=now_ts,
            date=(now + timedelta(days=10)).isoformat())
session.add(show)
session.commit()
session.execute(ShowSeatHistory.__table__.insert(), [
    {'show_id': show.id, 'timestamp': now_ts - index * 600,
     'seats': 100 + 2 * min(index // 3, 48) + max(index // 3 - 48, 0)}
    for index in range(1153)
])

# The latest value at each timestamp wins before detecting quota changes.
session.execute(ShowSeatHistory.__table__.insert(), [
    {'show_id': show.id, 'timestamp': now_ts - 30 * 3600 + 600, 'seats': 508},
    {'show_id': show.id, 'timestamp': now_ts - 30 * 3600 + 600, 'seats': 408},
    {'show_id': show.id, 'timestamp': now_ts - 30 * 3600 + 1200, 'seats': 208},
    {'show_id': show.id, 'timestamp': now_ts - 6 * 3600 + 600, 'seats': 900},
    {'show_id': show.id, 'timestamp': now_ts - 6 * 3600 + 600, 'seats': 122},
])
session.commit()
full_history = session.scalars(select(ShowSeatHistory)).all()
expected = analyze_inventory(full_history, now_ts,
                             now + timedelta(days=10))
query = insights_history_query([show.id], now_ts)
postgresql_sql = str(query.compile(dialect=postgresql.dialect()))
assert 'inventory_cutoffs AS MATERIALIZED' in postgresql_sql
assert 'inventory_last_jump AS MATERIALIZED' in postgresql_sql
assert 'MATERIALIZED' not in str(query.compile(dialect=engine.dialect))
sampled = session.scalars(query).all()
assert len(sampled) <= 342
assert sampled[0].timestamp == now_ts - 7 * 86400
assert len(sampled) == len({row.timestamp for row in sampled})
assert not any(row.seats in (508, 900) for row in sampled)
assert {(row.timestamp, row.seats) for row in sampled} >= {
    (now_ts - 30 * 3600, 208),
    (now_ts - 30 * 3600 + 600, 408),
}
assert expected.previous_rate_per_day is None
assert expected.trend == 'depleting'
assert expected.forecast_at is not None

class Adapter:
    async def execute(self, statement):
        return session.execute(statement)

async def run():
    item = (await load_inventory_insights(Adapter(), [show], now_ts))[show.id]
    assert item.previous_rate_per_day is None
    assert item.trend == expected.trend
    assert item.net_rate_per_day == expected.net_rate_per_day == 96
    assert item.reason == expected.reason == 'ok'
    assert item.forecast_at == expected.forecast_at
    assert item.forecast_earliest == expected.forecast_earliest
    assert item.forecast_latest == expected.forecast_latest
    assert item.decreases == 96 and item.increases == 0

    # A newer jump must not hide the reset in the previous trend window.
    session.execute(ShowSeatHistory.__table__.insert(), [
        {'show_id': show.id, 'timestamp': now_ts - 6 * 3600 + 600, 'seats': 422},
        {'show_id': show.id, 'timestamp': now_ts - 6 * 3600 + 1200, 'seats': 122},
    ])
    session.commit()
    raw = analyze_inventory(session.scalars(select(ShowSeatHistory)).all(),
                            now_ts, now + timedelta(days=10))
    item = (await load_inventory_insights(Adapter(), [show], now_ts))[show.id]
    assert item == raw
    assert item.previous_rate_per_day is None
    assert item.reason == 'inventory_jump'
    assert item.net_rate_per_day is None
    assert item.forecast_at is None

asyncio.run(run())
session.close()
engine.dispose()
""",
        tmp_path,
        {'UPDATE_INTERVAL': '600'},
    )


def test_bounded_history_does_not_merge_small_increases_into_quota_jump(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from services.profticket.analytics_repository import (
    insights_history_query, load_inventory_insights,
)
from services.profticket.insights import analyze_inventory
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
event = now + timedelta(days=10)
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
session = Session(engine, expire_on_commit=False)
shows = []
expected = {}
for event_id, start, base in (
    ('current_day', 144, 200), ('previous_day', 288, 240),
):
    show = Show(id=event_id, seats=base + 63 - start,
                updated_at=now_ts, date=event.isoformat())
    shows.append(show)
    session.add(show)
    session.flush()
    rows = []
    for index in range(1009):
        elapsed = start - index
        seats = (base - elapsed if elapsed <= 0 else
                 base + elapsed * 20 if elapsed <= 3 else
                 base + 60 - (elapsed - 3))
        rows.append({'show_id': event_id,
                     'timestamp': now_ts - index * 600, 'seats': seats})
    session.execute(ShowSeatHistory.__table__.insert(), rows)
    session.commit()
    raw = session.scalars(select(ShowSeatHistory).where(
        ShowSeatHistory.show_id == event_id)).all()
    expected[event_id] = analyze_inventory(raw, now_ts, event)
    sampled = session.scalars(insights_history_query([event_id], now_ts)).all()
    assert len(sampled) <= 341
    assert len(sampled) < len(raw)
    assert expected[event_id].reason == 'ok'
    assert expected[event_id].forecast_at is not None

class Adapter:
    async def execute(self, statement):
        return session.execute(statement)

async def run():
    loaded = await load_inventory_insights(Adapter(), shows, now_ts)
    for show in shows:
        assert loaded[show.id] == expected[show.id], (
            show.id, loaded[show.id], expected[show.id])
    assert loaded['current_day'].net_rate_per_day == 81
    assert loaded['current_day'].trend == 'slowing'
    assert loaded['previous_day'].previous_rate_per_day == 81
    assert loaded['previous_day'].trend == 'accelerating'

asyncio.run(run())
session.close()
engine.dispose()
""",
        tmp_path,
        {'UPDATE_INTERVAL': '600'},
    )


def test_bounded_history_preserves_gap_boundaries(tmp_path: Path) -> None:
    run_runtime_script(
        r"""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from services.profticket.analytics_repository import (
    insights_history_query, load_inventory_insights,
)
from services.profticket.insights import analyze_inventory
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
now_ts = int(now.timestamp())
event = now + timedelta(days=10)
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
session = Session(engine, expire_on_commit=False)
shows, expected = [], {}
for key, intervals in (
    ('current_valid', [(0, 21000)]),
    ('just_below', [(0, 21599)]),
    ('at_limit', [(0, 21600)]),
    ('just_above', [(0, 21601)]),
    ('previous_valid', [(86400, 21000)]),
    ('previous_invalid', [(86400, 21601)]),
    ('recovered', [(2 * 86400, 21601)]),
    ('multiple', [(0, 21000), (86400, 21601), (2 * 86400, 21000)]),
):
    show = Show(id=key, date=event.isoformat(), seats=100, updated_at=now_ts)
    shows.append(show)
    session.add(show)
    session.flush()
    timestamps = set(range(now_ts - 7 * 86400, now_ts + 1, 600))
    boundaries = []
    for shift, length in intervals:
        before = now_ts - 7 * 3600 - 15 * 60 - shift
        after = before + length
        timestamps = {time for time in timestamps if not before < time < after}
        timestamps.update((before, after))
        boundaries.append((before, after))
    rows = [{'show_id': key, 'timestamp': time,
             'seats': 100 + round((now_ts - time) / 3600)}
            for time in sorted(timestamps)]
    session.execute(ShowSeatHistory.__table__.insert(), rows)
    for _, after in boundaries:
        session.execute(ShowSeatHistory.__table__.insert(), [
            {'show_id': key, 'timestamp': after, 'seats': 900},
            {'show_id': key, 'timestamp': after,
             'seats': 100 + round((now_ts - after) / 3600)},
        ])
    session.commit()
    raw = session.scalars(select(ShowSeatHistory).where(
        ShowSeatHistory.show_id == key)).all()
    expected[key] = analyze_inventory(raw, now_ts, event)
    sampled = session.scalars(insights_history_query([key], now_ts)).all()
    assert len(sampled) <= 341
    assert len(sampled) == len({row.timestamp for row in sampled})
    selected = {row.timestamp for row in sampled}
    for before, after in boundaries:
        assert {before, after} <= selected, (key, before, after)
    assert not any(row.seats == 900 for row in sampled)

class Adapter:
    async def execute(self, statement):
        return session.execute(statement)

async def run():
    loaded = await load_inventory_insights(Adapter(), shows, now_ts)
    for key, raw in expected.items():
        assert loaded[key] == raw, (key, loaded[key], raw)
    assert loaded['current_valid'].quality == 'good'
    assert loaded['current_valid'].net_rate_per_day == 24
    assert loaded['current_valid'].forecast_at == now_ts + 100 * 3600
    assert loaded['at_limit'].reason == 'ok'
    assert loaded['just_above'].reason == 'long_gap'
    assert loaded['just_above'].net_rate_per_day is None
    assert loaded['previous_invalid'].previous_rate_per_day is None
    assert loaded['multiple'].previous_rate_per_day is None

asyncio.run(run())
session.close()
engine.dispose()
""",
        tmp_path,
        {'UPDATE_INTERVAL': '600'},
    )
