import asyncio
import calendar
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.ermolova import (
    ErmolovaInfo,
    SourceError,
    parse_details,
    parse_inventory,
    parse_schedule,
)
from services.profticket.analytics import parse_show_date as analytics_date
from telegram.lexicon.lexicon_ru import (
    LEXICON_MONTHS_RU,
    PERFORMANCE_FALLBACKS,
)
from telegram.tg_utils import get_result_message, parse_show_date


def schedule_html(link: str = '#mosbilet123', day: int = 13) -> str:
    month = LEXICON_MONTHS_RU[calendar.month_name[9]]
    return f"""
        <span class="head h1">{month} 2026</span>
        <div class="perform erm-bold">
            <div class="perform-date">
                <span>{day} Sunday</span><span>19:00</span>
                <span style="display:none">16:00</span><span>Main</span>
            </div>
            <div class="perform-name">
                <a href="/afisha/view/230/">A &amp; B</a>
            </div>
            <a href="/afisha/view/230/{link}">Buy</a>
            <span style="display:none">0 SOLD OUT</span>
        </div>
    """


def test_schedule_identity_survives_sales_opening() -> None:
    before = parse_schedule(schedule_html(link=''), 9, 2026)[0]
    after = parse_schedule(schedule_html(), 9, 2026)[0]
    assert before['id'] == after['id']
    assert before['seats'] is None
    assert after['seats'] is None
    assert after['performance_id'] == '123'
    assert after['show_id'] == -230
    assert after['date'] == '13.09.2026, 19:00'
    assert after['show_name'] == 'A & B'
    assert before['buy_link'] == 'https://www.ermolova.ru/afisha/view/230/'


@pytest.mark.parametrize(
    'source',
    [
        '<html>Access denied</html>',
        schedule_html().replace('2026', '2025'),
        schedule_html().replace('19:00', 'not-a-time'),
        schedule_html().replace('class="perform-name"', 'class="changed"'),
        schedule_html().replace('#mosbilet123', '#mosbiletx'),
        schedule_html() + schedule_html(),
    ],
)
def test_invalid_schedule_is_not_partial_success(source: str) -> None:
    with pytest.raises(SourceError):
        parse_schedule(source, 9, 2026)


def test_wrong_month_and_empty_page_are_rejected() -> None:
    with pytest.raises(SourceError):
        parse_schedule(schedule_html(), 10, 2026)
    with pytest.raises(SourceError):
        parse_schedule(schedule_html().split('<div')[0], 9, 2026)


def test_cast_does_not_include_navigation_or_creators() -> None:
    details = parse_details("""
        <h1 class="head">Show</h1>
        <a href="/persones/troupe/view/1/">Navigation</a>
        <div class="creators-block-actors">
            <a href="/persones/troupe/view/2/">First Actor</a>
            <a href="/persones/troupe/view/2/">First Actor</a>
            <a href="/persones/invited/view/3/">Second Actor</a>
        </div>
    """)
    assert details['actors'] == ['First Actor', 'Second Actor']


@pytest.mark.parametrize('count', [None, -1, True, '78', 1.5])
def test_invalid_inventory_is_not_zero(count: object) -> None:
    with pytest.raises(SourceError):
        parse_inventory({'available_tickets': count})


def test_inventory_uses_available_total_not_schema_count() -> None:
    assert (
        parse_inventory(
            {
                'available_tickets': 0,
                'schema': {'sectors': [{'places': [{'status': 'free'}]}]},
            }
        )['seats']
        == 0
    )
    assert parse_inventory({'available_tickets': 78})['seats'] == 78


def test_date_readers_support_both_sources() -> None:
    expected = datetime(2026, 9, 13, 19)
    assert parse_show_date('13.09.2026, 19:00') == expected
    assert analytics_date('13.09.2026, 19:00') == expected


@pytest.mark.parametrize('date_str', [None, '', 'invalid date'])
def test_date_readers_preserve_invalid_date_fallbacks(
    date_str: str | None,
) -> None:
    assert parse_show_date(date_str) == datetime.min
    assert analytics_date(date_str) is None


def test_unknown_inventory_renders_link_without_false_soldout() -> None:
    message = get_result_message(None, 50, 'A & B', '<date>', 'https://e.test')
    assert 'SOLD OUT' not in message
    assert 'None' not in message
    assert 'A &amp; B' in message and '&lt;date&gt;' in message
    assert '<a href="https://e.test">' in message
    assert '🔻' not in message
    assert 'Билетов пока нет' in get_result_message(
        0, None, 'A', 'd', 'https://e.test'
    )


@pytest.mark.parametrize('missing', [None, ''])
@pytest.mark.parametrize('seats', [None, 0, 5])
def test_message_handles_missing_fields(
    missing: str | None,
    seats: int | None,
) -> None:
    message = get_result_message(seats, None, missing, missing, missing)
    assert PERFORMANCE_FALLBACKS['name'] in message
    assert PERFORMANCE_FALLBACKS['date'] in message
    assert '<a ' not in message
    assert 'None' not in message
    if seats is None:
        assert PERFORMANCE_FALLBACKS['inventory'] in message
        assert 'SOLD OUT' not in message
    elif seats == 0:
        assert 'Билетов пока нет' in message
    else:
        assert str(seats) in message


@pytest.mark.parametrize('field', ['show_name', 'date', 'buy_link'])
def test_message_handles_each_nullable_field(field: str) -> None:
    values = {
        'show_name': 'A & B',
        'date': '<date>',
        'buy_link': 'https://e.test',
    }
    values[field] = None
    message = get_result_message(5, 7, **values)
    assert 'None' not in message
    if field == 'buy_link':
        assert '<a ' not in message
    else:
        assert '<a href="https://e.test">Купить</a>' in message
    assert '(на 2 меньше)' in message


@pytest.mark.parametrize(
    'url', ['', 'http://proxy:3128', 'socks5://proxy:1080']
)
def test_proxy_ca_requires_https(url: str) -> None:
    with pytest.raises(ValueError, match='HTTPS proxy'):
        ErmolovaInfo(url, proxy_ca_file='missing.crt')


def test_proxy_ca_missing_file_fails_closed() -> None:
    with pytest.raises(FileNotFoundError):
        ErmolovaInfo('https://proxy:3129', proxy_ca_file='missing.crt')


def test_complete_collection_and_failed_inventory() -> None:
    async def check() -> None:
        source = ErmolovaInfo()
        source.client = AsyncMock()
        source.inventory_client = AsyncMock()
        try:
            source.set_date(9, 2026)

            async def request(client: object, url: str) -> SimpleNamespace:
                if '/index/' in url:
                    return SimpleNamespace(
                        content=schedule_html().encode('cp1251')
                    )
                if '/schema' in url:
                    return SimpleNamespace(
                        json=lambda: {'available_tickets': 78}
                    )
                return SimpleNamespace(content=b'<h1 class="head">Show</h1>')

            source._get = request
            result = await source.collect_full_info()
            assert len(result) == 1
            assert next(iter(result.values()))['seats'] == 78

            async def failed_inventory(
                client: object, url: str
            ) -> SimpleNamespace:
                if '/schema' in url:
                    raise SourceError('Unavailable')
                return await request(client, url)

            source._get = failed_inventory
            with pytest.raises(SourceError):
                await source.collect_full_info()
        finally:
            await source.aclose()

    asyncio.run(check())
