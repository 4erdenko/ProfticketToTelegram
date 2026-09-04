"""Ermolova schedule and Mosbilet inventory, without database side effects."""

import asyncio
import calendar
import hashlib
import re
import ssl
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from telegram.lexicon.lexicon_ru import LEXICON_MONTHS_RU

BASE_URL = 'https://www.ermolova.ru'
INVENTORY_URL = 'https://tickets.mos.ru/api/widget/v2/performance/'


class SourceError(ValueError):
    """A source response cannot safely replace a saved monthly snapshot."""


def parse_schedule(source: str, month: int, year: int) -> list[dict]:
    soup = BeautifulSoup(source, 'html.parser')
    heading = soup.select_one('span.head.h1')
    expected = f'{LEXICON_MONTHS_RU[calendar.month_name[month]]} {year}'
    if not heading or heading.get_text(' ', strip=True) != expected:
        raise SourceError('Schedule month does not match the request')
    blocks = soup.select('div.perform.erm-bold')
    if not blocks:
        raise SourceError('Empty schedule requires manual verification')
    events = {}
    for block in blocks:
        title = block.select_one('.perform-name a[href]')
        dates = block.select_one('.perform-date')
        if not title or not dates:
            raise SourceError('Missing performance title or date')
        match = re.fullmatch(r'/afisha/view/(\d+)/', title['href'])
        spans = dates.find_all('span', recursive=False)
        if not match or len(spans) != 4:
            raise SourceError('Unexpected performance layout')
        website_id = int(match[1])
        try:
            day = int(spans[0].get_text(strip=True).split()[0])
            time = spans[1].get_text(strip=True)
            date = datetime.strptime(
                f'{year}-{month}-{day} {time}', '%Y-%m-%d %H:%M'
            )
        except ValueError as exc:
            raise SourceError('Invalid performance date') from exc
        scene = spans[3].get_text(' ', strip=True)
        scene_key = hashlib.sha256(scene.encode()).hexdigest()[:12]
        event_id = f'ermolova:{website_id}:{date.isoformat()}:{scene_key}'
        buy = block.select_one('a[href*="#mosbilet"]')
        external = block.select_one('a.crave-button[href]')
        performance_id = None
        if buy:
            performance = re.fullmatch(
                rf'/afisha/view/{website_id}/#mosbilet(\d+)', buy['href']
            )
            if not performance:
                raise SourceError('Invalid Mosbilet performance link')
            performance_id = performance[1]
        link = buy or external or title
        buy_link = urljoin(BASE_URL, link['href'])
        if not buy_link.startswith('https://'):
            raise SourceError('Unexpected ticket link scheme')
        name = title.get_text(' ', strip=True)
        if not name or not scene or event_id in events:
            raise SourceError('Missing or duplicate performance identity')
        events[event_id] = {
            'id': event_id,
            'show_id': -website_id,
            'website_id': website_id,
            'performance_id': performance_id,
            'theater': 'Ermolova',
            'scene': scene,
            'show_name': name,
            'date': date.strftime('%d.%m.%Y, %H:%M'),
            'buy_link': buy_link,
            'seats': None,
            'min_price': None,
            'max_price': None,
            'duration': None,
            'age': None,
            'pushkin': bool(block.select_one('img[src*="pushkin"]')),
        }
    return list(events.values())


def parse_details(source: str) -> dict[str, Any]:
    soup = BeautifulSoup(source, 'html.parser')
    if not soup.select_one('h1.head'):
        raise SourceError('Missing show details')
    actors = dict.fromkeys(
        node.get_text(' ', strip=True)
        for node in soup.select('.creators-block-actors a[href*="/persones/"]')
        if node.get_text(strip=True)
    )
    image = soup.select_one('meta[property="og:image"]')
    description = soup.select_one('meta[name="description"]')
    return {
        'actors': list(actors),
        'image': urljoin(BASE_URL, image.get('content', ''))
        if image
        else None,
        'annotation': description.get('content') if description else None,
    }


def parse_inventory(data: Any) -> dict[str, int | None]:
    if not isinstance(data, dict):
        raise SourceError('Invalid inventory response')
    seats = data.get('available_tickets')
    if type(seats) is not int or seats < 0:
        raise SourceError('Missing or invalid available ticket count')
    # The schema's free-place count differs from the API's available total.
    prices = [
        category['adult_price']
        for category in data.get('categories', [])
        if isinstance(category, dict)
        and type(category.get('adult_price')) in (int, float)
        and category['adult_price'] >= 0
    ]
    return {
        'seats': seats,
        'min_price': int(min(prices)) if prices else None,
        'max_price': int(max(prices)) if prices else None,
    }


class ErmolovaInfo:
    def __init__(
        self,
        proxy_url: str = '',
        timeout: float = 20.0,
        *,
        proxy_ca_file: str = '',
    ) -> None:
        proxy = proxy_url or None
        if proxy_ca_file:
            if not proxy_url.startswith('https://'):
                raise ValueError('Proxy CA requires an HTTPS proxy URL')
            proxy_context = ssl.create_default_context(cafile=proxy_ca_file)
            proxy = httpx.Proxy(proxy_url, ssl_context=proxy_context)
        self.month: int | None = None
        self.year: int | None = None
        self.client = httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, trust_env=False
        )
        self.inventory_client = httpx.AsyncClient(
            proxy=proxy, timeout=timeout, trust_env=False
        )
        self._semaphore = asyncio.Semaphore(3)

    def set_date(self, month: int, year: int) -> None:
        datetime(year, month, 1)
        self.month, self.year = month, year

    async def aclose(self) -> None:
        await self.client.aclose()
        await self.inventory_client.aclose()

    async def _get(
        self, client: httpx.AsyncClient, url: str
    ) -> httpx.Response:
        async with self._semaphore:
            for attempt in range(3):
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    if attempt == 2:
                        raise SourceError(
                            f'Source request failed: {type(exc).__name__}'
                        ) from None
                    await asyncio.sleep(attempt + 1)
        raise SourceError('Source request failed')

    async def collect_full_info(self) -> dict[str, dict]:
        month, year = self.month, self.year
        if month is None or year is None:
            raise ValueError('Set month and year before loading the schedule')
        response = await self._get(
            self.client, f'{BASE_URL}/afisha/index/any/{month}-{year}/'
        )
        events = parse_schedule(response.content.decode('cp1251'), month, year)
        details = {}

        async def load_details(website_id: int) -> None:
            page = await self._get(
                self.client, f'{BASE_URL}/afisha/view/{website_id}/'
            )
            details[website_id] = parse_details(page.content.decode('cp1251'))

        async def load_inventory(event: dict) -> None:
            if event['performance_id']:
                inventory = await self._get(
                    self.inventory_client,
                    f'{INVENTORY_URL}{event["performance_id"]}/schema'
                    '?theatrical=true',
                )
                event.update(parse_inventory(inventory.json()))

        # Finish failed batches before starting another month.
        results = await asyncio.gather(
            *(load_details(i) for i in {e['website_id'] for e in events}),
            *(load_inventory(event) for event in events),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        for event in events:
            event.update(details[event['website_id']])
        return {event['id']: event for event in events}
