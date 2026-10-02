from pathlib import Path
from textwrap import dedent

from tests.runtime_helpers import run_runtime_script

COMMON = """
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession, sessionmaker

from config import settings
from services.profticket import profticket_api as api_module
from services.profticket.profticket_api import (
    InvalidResponseFormat,
    ProfticketAPIError,
    ProfticketsInfo,
    RateLimitError,
)
from services.profticket.profticket_snapshoter import ShowUpdateService
from telegram.db import Base
from telegram.db.models import Show, ShowSeatHistory

EVENT = {
    'id': 'e1',
    'show': {'show_id': '1'},
    'show_name': 'Test Show',
    'date_formatted': '20.10.2026, 19:00',
}
SNAPSHOT = {
    'show_id': '1', 'theater': 'Theater', 'scene': 'Main',
    'show_name': 'Test Show', 'date': '20.10.2026, 19:00',
    'duration': None, 'age': None, 'seats': 7, 'image': None,
    'annotation': None, 'min_price': None, 'max_price': None,
    'pushkin': False, 'buy_link': 'https://tickets.test', 'actors': ['Actor'],
}

def response(data: object) -> httpx.Response:
    return httpx.Response(
        200, json=data, request=httpx.Request('GET', 'https://source.test')
    )

class Source:
    def __init__(self, data: dict[str, dict[str, Any]]) -> None:
        self.data = data

    def set_date(self, month: int, year: int) -> None:
        pass

    async def collect_full_info(self) -> dict[str, dict[str, Any]]:
        return self.data

class Session:
    def __init__(self, session: OrmSession) -> None:
        self.session = session

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self.session.execute(*args, **kwargs)

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()
"""


def test_partial_schedule_preserves_saved_rows(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                engine = create_engine('sqlite:///:memory:')
                Base.metadata.create_all(engine)
                maker = sessionmaker(engine)
                source = Source({'e1': SNAPSHOT, 'e2': SNAPSHOT})
                service = ShowUpdateService(maker, source, AsyncMock())
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                try:
                    with maker() as sync_session:
                        session = Session(sync_session)
                        assert await service._update_month_data(
                            session, 10, 2026
                        )
                        api._make_request = AsyncMock(side_effect=[
                            response({'response': {'items': [
                                {'events': [EVENT]}
                            ]}}),
                            ProfticketAPIError('Second page unavailable'),
                        ])
                        service.profticket = api
                        with patch('asyncio.sleep', new=AsyncMock()):
                            assert not await service._update_month_data(
                                session, 10, 2026
                            )
                        sync_session.expire_all()
                        saved = sync_session.scalars(select(Show)).all()
                        assert {row.id for row in saved} == {'e1', 'e2'}
                        assert all(not row.is_deleted for row in saved)
                        assert all(row.seats == 7 for row in saved)
                        histories = sync_session.scalars(
                            select(ShowSeatHistory)
                        ).all()
                        assert [row.seats for row in histories] == [7, 7]
                finally:
                    await api.client.aclose()
                    engine.dispose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_pagination_rejects_missing_or_malformed_items(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                try:
                    invalid = [
                        {}, {'response': {}}, {'response': None},
                        {'response': {'items': None}},
                        {'response': {'items': {}}},
                        {'response': {'items': [None]}},
                    ]
                    with patch('asyncio.sleep', new=AsyncMock()):
                        for data in invalid:
                            api._make_request = AsyncMock(side_effect=[
                                response({'response': {'items': [
                                    {'events': [EVENT]}
                                ]}}),
                                response(data),
                            ])
                            with pytest.raises(InvalidResponseFormat):
                                await api._load_data()
                        api._make_request = AsyncMock(side_effect=[
                            response({'response': {'items': [
                                {'events': [EVENT]}
                            ]}}),
                            response({'response': {'items': []}}),
                        ])
                        assert await api._load_data() == [{'events': [EVENT]}]
                finally:
                    await api.client.aclose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_malformed_events_reject_the_whole_collection(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                api._places = AsyncMock()
                api._get_show_details = AsyncMock()
                try:
                    invalid = [
                        None, {}, {**EVENT, 'id': None},
                        {**EVENT, 'show': {}},
                        {**EVENT, 'show': {'show_id': 'invalid'}},
                        {**EVENT, 'show_name': None},
                        {**EVENT, 'date_formatted': ''},
                        {**EVENT, 'pushkin_card': 'invalid'},
                    ]
                    for event in invalid:
                        api._load_data = AsyncMock(return_value=[
                            {'events': [EVENT, event]}
                        ])
                        with pytest.raises(ProfticketAPIError):
                            await api.collect_full_info()
                    api._load_data = AsyncMock(return_value=[
                        {'events': [EVENT, deepcopy(EVENT)]}
                    ])
                    with pytest.raises(ProfticketAPIError):
                        await api.collect_full_info()
                    api._load_data = AsyncMock(return_value=[{}])
                    with pytest.raises(ProfticketAPIError):
                        await api.collect_full_info()
                    api._places.assert_not_awaited()
                    api._get_show_details.assert_not_awaited()
                finally:
                    await api.client.aclose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_unknown_inventory_never_creates_zero_history(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                api._load_data = AsyncMock(return_value=[{'events': [EVENT]}])
                async def request(url: str) -> httpx.Response:
                    if 'events-data' in url:
                        return response({'events': {}})
                    return response({'response': {'show_detail': {
                        'actors': ['Actor']
                    }}})
                api._make_request = request
                engine = create_engine('sqlite:///:memory:')
                Base.metadata.create_all(engine)
                maker = sessionmaker(engine)
                try:
                    with patch('asyncio.sleep', new=AsyncMock()):
                        collected = await api.collect_full_info()
                    assert collected['e1']['seats'] is None
                    service = ShowUpdateService(
                        maker, Source({'e1': SNAPSHOT}), AsyncMock()
                    )
                    with maker() as sync_session:
                        session = Session(sync_session)
                        assert await service._update_month_data(
                            session, 10, 2026
                        )
                        service.profticket = Source(collected)
                        assert await service._update_month_data(
                            session, 10, 2026
                        )
                        sync_session.expire_all()
                        row = sync_session.scalars(select(Show)).one()
                        assert row.seats is None
                        assert row.previous_seats is None
                        histories = sync_session.scalars(
                            select(ShowSeatHistory)
                        ).all()
                        assert [row.seats for row in histories] == [7]
                finally:
                    await api.client.aclose()
                    engine.dispose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_invalid_inventory_is_rejected(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                try:
                    invalid = [{}, {'events': None}, {'events': {'e1': 0}}]
                    invalid += [
                        {'events': {'e1': {'seats': value}}}
                        for value in [-1, True, '5', 1.5]
                    ]
                    for payload in invalid:
                        api._make_request = AsyncMock(
                            return_value=response(payload)
                        )
                        with pytest.raises(ProfticketAPIError):
                            await api._places()
                        assert api.free_places == {}
                    api._make_request = AsyncMock(return_value=response({
                        'events': {'e1': {}, 'e2': {'seats': 0}}
                    }))
                    await api._places()
                    assert api.free_places == {'e1': None, 'e2': 0}
                finally:
                    await api.client.aclose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_actor_cache_refreshes_and_rejects_invalid_details(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                api._load_data = AsyncMock(return_value=[{'events': [EVENT]}])
                casts = [['Old Actor'], ['New Actor']]
                async def request(url: str) -> httpx.Response:
                    if 'events-data' in url:
                        return response({'events': {'e1': {'seats': 7}}})
                    return response({'response': {'show_detail': {
                        'actors': casts.pop(0)
                    }}})
                api._make_request = request
                try:
                    with patch('asyncio.sleep', new=AsyncMock()):
                        first = await api.collect_full_info()
                        second = await api.collect_full_info()
                    assert first['e1']['actors'] == ['Old Actor']
                    assert second['e1']['actors'] == ['New Actor']
                    assert casts == []
                    api.clear_cache()
                    api._make_request = AsyncMock(return_value=response({}))
                    with pytest.raises(InvalidResponseFormat):
                        await api._get_show_details('1')
                    assert api._show_cache == {}
                    api._make_request = AsyncMock(return_value=response({
                        'response': {'show_detail': {'actors': False}}
                    }))
                    with pytest.raises(InvalidResponseFormat):
                        await api._get_show_details('1')
                    assert api._show_cache == {}
                finally:
                    await api.client.aclose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_source_client_verifies_tls(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            import ssl
            async def check() -> None:
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                try:
                    context = api.client._transport._pool._ssl_context
                    assert context.verify_mode == ssl.CERT_REQUIRED
                    assert context.check_hostname
                finally:
                    await api.client.aclose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_rate_limits_and_timeouts_retry_with_retry_after(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                calls = []
                async def handler(request: httpx.Request) -> httpx.Response:
                    calls.append(request)
                    if len(calls) == 1:
                        return httpx.Response(429, headers={'Retry-After': '11'})
                    if len(calls) == 2:
                        raise httpx.ConnectTimeout('Transient timeout')
                    return httpx.Response(200, json={'ok': True})
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                await api.client.aclose()
                api.client = httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                )
                try:
                    with patch('asyncio.sleep', new=AsyncMock()) as sleep:
                        result = await api._make_request('https://source.test')
                    assert result.json() == {'ok': True}
                    assert len(calls) == 3
                    assert [call.args[0] for call in sleep.await_args_list] == [
                        11.0, 4.0
                    ]
                    fixed = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
                    with patch.object(api_module, 'datetime', SimpleNamespace(
                        now=lambda tz: fixed
                    )):
                        assert api_module._retry_after(
                            'Fri, 02 Oct 2026 12:00:30 GMT'
                        ) == 30
                    for invalid in [None, 'invalid', 'NaN', 'inf']:
                        assert api_module._retry_after(invalid) == 5
                    calls.clear()
                    api.client.get = AsyncMock(return_value=httpx.Response(
                        429, headers={'Retry-After': '0'},
                        request=httpx.Request('GET', 'https://source.test')
                    ))
                    with patch('asyncio.sleep', new=AsyncMock()):
                        with pytest.raises(RateLimitError):
                            await api._make_request('https://source.test')
                    assert api.client.get.await_count == 3
                finally:
                    await api.client.aclose()
            asyncio.run(check())
        """),
        tmp_path,
        {'STOP_AFTER_ATTEMPT': '3'},
    )


def test_failed_month_retries_without_refetching_fresh_months(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                @asynccontextmanager
                async def maker() -> AsyncIterator[Any]:
                    yield AsyncMock()
                service = ShowUpdateService(maker, Source({}), AsyncMock())
                service._archive_past_months = AsyncMock()
                service._check_data_freshness = AsyncMock(side_effect=[
                    False, True, False, False, True, True
                ])
                service._update_month_data = AsyncMock(side_effect=[
                    False, True, True
                ])
                delays = []
                async def sleep(delay: float) -> None:
                    delays.append(delay)
                    if len(delays) == 2:
                        raise asyncio.CancelledError()
                with patch('asyncio.sleep', new=sleep):
                    with pytest.raises(asyncio.CancelledError):
                        await service.update_loop()
                assert delays == [
                    settings.ERROR_RETRY_INTERVAL, settings.UPDATE_INTERVAL
                ]
                updates = service._update_month_data.await_args_list
                assert len(updates) == 3
                assert updates[0].args[1:] == updates[2].args[1:]
                assert updates[1].args[1:] != updates[0].args[1:]
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_past_month_archival_preserves_history(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                engine = create_engine('sqlite:///:memory:')
                Base.metadata.create_all(engine)
                maker = sessionmaker(engine)
                with maker() as sync_session:
                    rows = [
                        Show(id='older_year', month=12, year=2025),
                        Show(id='previous', month=9, year=2026),
                        Show(id='current', month=10, year=2026),
                        Show(id='future', month=11, year=2026),
                        Show(id='next_year', month=1, year=2027),
                    ]
                    sync_session.add_all(rows)
                    sync_session.add(ShowSeatHistory(
                        show_id='previous', timestamp=1, seats=7
                    ))
                    sync_session.commit()
                    service = ShowUpdateService(maker, Source({}), AsyncMock())
                    await service._archive_past_months(
                        Session(sync_session), datetime(2026, 10, 1)
                    )
                    sync_session.expire_all()
                    archived = {
                        row.id: row.is_deleted
                        for row in sync_session.scalars(select(Show))
                    }
                    assert archived == {
                        'older_year': True, 'previous': True,
                        'current': False, 'future': False, 'next_year': False,
                    }
                    histories = sync_session.scalars(
                        select(ShowSeatHistory)
                    ).all()
                    assert len(histories) == 1
                    assert histories[0].seats == 7
                engine.dispose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_event_dates_must_match_the_requested_month(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                engine = create_engine('sqlite:///:memory:')
                Base.metadata.create_all(engine)
                maker = sessionmaker(engine)
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                api._places = AsyncMock()
                api._make_request = AsyncMock(return_value=response({
                    'response': {'show_detail': {'actors': []}}
                }))
                service = ShowUpdateService(
                    maker, Source({'e1': SNAPSHOT}), AsyncMock()
                )
                try:
                    with maker() as sync_session:
                        session = Session(sync_session)
                        assert await service._update_month_data(
                            session, 10, 2026
                        )
                        service.profticket = api
                        for value in [
                            'not a date', '20.11.2026, 19:00',
                            '20.10.2025, 19:00', '31.02.2026, 19:00',
                        ]:
                            api._load_data = AsyncMock(return_value=[{
                                'events': [{
                                    **EVENT, 'date_formatted': value,
                                }]
                            }])
                            assert not await service._update_month_data(
                                session, 10, 2026
                            )
                        api._places.assert_not_awaited()
                        api._make_request.assert_not_awaited()
                        sync_session.expire_all()
                        saved = sync_session.scalars(select(Show)).one()
                        assert saved.month == 10 and saved.year == 2026
                        assert saved.date == SNAPSHOT['date']
                        assert saved.seats == 7 and not saved.is_deleted
                        assert len(sync_session.scalars(
                            select(ShowSeatHistory)
                        ).all()) == 1
                    for value in [
                        '20.10.2026, 19:00',
                        '20 октября 2026, вт, 19:00',
                        '2026-10-20T19:00:00',
                    ]:
                        api._load_data = AsyncMock(return_value=[{
                            'events': [{**EVENT, 'date_formatted': value}]
                        }])
                        with patch('asyncio.sleep', new=AsyncMock()):
                            result = await api.collect_full_info()
                        assert result['e1']['date'] == value
                    assert api._make_request.await_count == 3
                finally:
                    await api.client.aclose()
                    engine.dispose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_schedule_pagination_detects_cycles_and_enforces_a_limit(
    tmp_path: Path,
) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                api = ProfticketsInfo('1')
                api.set_date(10, 2026)
                pages = [response({'response': {'items': [
                    {'events': [{**EVENT, 'id': identifier}]}
                ]}}) for identifier in ['first', 'second', 'third']]
                try:
                    with patch('asyncio.sleep', new=AsyncMock()):
                        api._make_request = AsyncMock(side_effect=[
                            pages[0], pages[0]
                        ])
                        with pytest.raises(
                            InvalidResponseFormat, match='repeats'
                        ):
                            await api._load_data()
                        assert api._make_request.await_count == 2
                        api._make_request = AsyncMock(side_effect=[
                            pages[0], pages[1], pages[0]
                        ])
                        with pytest.raises(
                            InvalidResponseFormat, match='repeats'
                        ):
                            await api._load_data()
                        assert api._make_request.await_count == 3
                        api.MAX_SCHEDULE_PAGES = 3
                        api._make_request = AsyncMock(side_effect=pages)
                        with pytest.raises(
                            InvalidResponseFormat, match='limit'
                        ):
                            await api._load_data()
                        assert api._make_request.await_count == 3
                        api._make_request = AsyncMock(side_effect=[
                            *pages[:2], response({'response': {'items': []}})
                        ])
                        assert len(await api._load_data()) == 2
                finally:
                    await api.client.aclose()
            asyncio.run(check())
        """),
        tmp_path,
    )


def test_error_alerts_disable_html_parsing(tmp_path: Path) -> None:
    run_runtime_script(
        COMMON
        + dedent("""
            async def check() -> None:
                bot = AsyncMock()
                service = ShowUpdateService(AsyncMock(), Source({}), bot)
                await service._notify_admin('Source returned <broken>')
                bot.send_message.assert_awaited_once_with(
                    settings.ADMIN_ID,
                    'Source returned <broken>',
                    parse_mode=None,
                )
            asyncio.run(check())
        """),
        tmp_path,
    )
