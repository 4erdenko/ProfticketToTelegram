import asyncio
import logging

import httpx
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from config import settings

logger = logging.getLogger(__name__)


class ProfticketsInfo:
    """Class for interacting with Profticket API"""

    BASE_URL = 'https://widget.profticket.ru/api/event/list/?company_id='
    EVENT_DATA_URL = 'https://widget.profticket.ru/widget-api/events-data/'
    CUSTOMER_BUY_URL = 'https://spa.profticket.ru/customer/'
    SHOW_URL = 'https://widget.profticket.ru/api/event/show/'

    def __init__(self, com_id):
        """
        Initialize API client with company ID

        Args:
            com_id: Company identifier for API access
        """
        if com_id is None:
            raise ValueError('Company ID is required')
        self.com_id = com_id
        self.month = None
        self.year = None
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(
                max_keepalive_connections=5, max_connections=10
            ),
        )
        self._request_semaphore = asyncio.Semaphore(5)
        self._show_cache = {}
        self.free_places = {}
        logger.info(f'Initialized API client with company_id: {com_id}')

    def set_date(self, month, year):
        """Set target date for data retrieval"""
        self.month = month
        self.year = year
        logger.info(f'Set target date to: {month}/{year}')

    def _create_url(self, page_num):
        """Create URL for fetching event list"""
        url = (
            f'{self.BASE_URL}{self.com_id}'
            f'&type=events&page={page_num}&period_id=4&hall_id=&date='
            f'{self.year}.{self.month}'
            f'&name=&language=ru-RU'
        )
        logger.info(f'Created URL for page {page_num}: {url}')
        return url

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        stop=stop_after_attempt(settings.STOP_AFTER_ATTEMPT),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def _make_request(self, url):
        """Make HTTP request with retry logic and rate limiting"""
        async with self._request_semaphore:
            try:
                response = await self.client.get(url)

                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 5))
                    logger.warning(f'Rate limit hit, waiting {retry_after}s')
                    await asyncio.sleep(retry_after)
                    raise httpx.HTTPStatusError(
                        'Rate limit exceeded', response=response
                    )

                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                logger.error(f'HTTP error: {e}', exc_info=True)
                raise
            except Exception as e:
                logger.error(f'Request error: {e}', exc_info=True)
                raise

    async def _load_data(self):
        """Load paginated event data"""
        page_num = 1
        items = []
        logger.info('Starting data load from page 1')

        while True:
            url = self._create_url(page_num)
            try:
                response = await self._make_request(url)
                response_json = response.json()

                if 'response' not in response_json:
                    raise ValueError('Invalid server response')

                new_items = response_json.get('response').get('items')
                if not new_items:
                    break

                items.extend(new_items)
                logger.info(
                    f'Loaded {len(new_items)} items from page {page_num}'
                )
                page_num += 1
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f'Error loading page {page_num}: {e}')
                raise

        logger.info(f'Completed loading {len(items)} total items')
        return items

    async def _places(self):
        """Fetch available places information"""
        places_url = f'{self.EVENT_DATA_URL}{self.com_id}/'
        try:
            response = await self._make_request(places_url)
            places_ben = response.json()
            places_events = places_ben.get('events', {})
            self.free_places = {
                event_id: free_places.get('seats', 0)
                for event_id, free_places in places_events.items()
                if isinstance(free_places, dict)
            }
            logger.info(
                f'Loaded free places info for {len(self.free_places)} events'
            )
        except Exception as e:
            logger.error(f'Error loading places: {e}', exc_info=True)
            self.free_places = {}

    def _generate_buy_link(self, event_id, show_id):
        """Generate buy link without making requests"""
        return (
            f'{self.CUSTOMER_BUY_URL}{self.com_id}/shows/{show_id}'
            f'?eventsIds%5B%5D={event_id}&language=ru-RU'
        )

    async def _get_show_details(self, show_id):
        """Get and cache complete show details including actors"""
        if show_id in self._show_cache:
            logger.debug(f'Using cached data for show_id: {show_id}')
            return self._show_cache[show_id]

        url = f'{self.SHOW_URL}?company_id={self.com_id}&show_id={show_id}'
        try:
            response = await self._make_request(url)
            data = response.json()
            show_detail = data.get('response', {}).get('show_detail', {})

            # Ensure actors is always a list
            actors = show_detail.get('actors')
            if not isinstance(actors, list):
                actors = ['']

            self._show_cache[show_id] = {
                'actors': actors,
                'details': show_detail,
            }
            logger.debug(f'Cached show details for show_id: {show_id}')
            return self._show_cache[show_id]
        except Exception as e:
            logger.error(f'Error fetching show details for {show_id}: {e}')
            # Return default structure with empty list for actors
            return {'actors': [''], 'details': {}}

    def clear_cache(self):
        """Clear the show data cache"""
        cache_size = len(self._show_cache)
        self._show_cache.clear()
        logger.info(f'Cleared cache containing {cache_size} shows')

    async def collect_full_info(self):
        """Collect all information about events with optimized request flow"""
        try:
            # 1. Load basic data
            items = await self._load_data()
            if not items:
                logger.warning('No items found')
                return {}

            # 2. Pre-collect all unique show IDs
            unique_shows = {
                event.get('show', {}).get('show_id')
                for item in items
                for event in item.get('events', [])
            }
            logger.info(f'Found {len(unique_shows)} unique shows to process')

            # 3. Load places info (single request)
            await self._places()

            # 4. Process show details in batches
            show_tasks = []
            uncached_shows = [
                show_id
                for show_id in unique_shows
                if show_id not in self._show_cache
            ]
            logger.info(
                f'Processing {len(uncached_shows)} uncached shows '
                f'out of {len(unique_shows)} total'
            )

            for show_id in uncached_shows:
                show_tasks.append(self._get_show_details(show_id))

            # Process in batches of 5
            for i in range(0, len(show_tasks), 5):
                batch = show_tasks[i: i + 5]
                if batch:
                    await asyncio.gather(*batch)
                    await asyncio.sleep(0.5)

            # 5. Build final result using cached data
            result = {}
            for item in items:
                for event in item.get('events', []):
                    event_id = event.get('id')
                    show_id = event.get('show', {}).get('show_id')

                    if not all([event_id, show_id]):
                        continue

                    try:
                        show_data = self._show_cache.get(show_id, {})
                        result[event_id] = {
                            'id': event_id,
                            'show_id': show_id,
                            'theater': event.get('location_name'),
                            'scene': event.get('location_scene'),
                            'show_name': event.get('show_name'),
                            'date': event.get('date_formatted'),
                            'duration': event.get('show', {}).get('duration'),
                            'age': event.get('show', {}).get('age'),
                            'seats': self.free_places.get(event_id, 0) or 0,
                            'image': event.get('show', {}).get('image_url'),
                            'annotation': event.get('annotation'),
                            'min_price': event.get('min_price', 0),
                            'max_price': event.get('max_price', 0),
                            'pushkin': event.get('pushkin_card', {}).get(
                                'can_buy', False
                            ),
                            'buy_link': self._generate_buy_link(
                                event_id, show_id
                            ),
                            'actors': show_data.get('actors', ['']),
                        }
                    except Exception as e:
                        logger.error(
                            f'Error processing event {event_id}: {e}',
                            exc_info=True,
                        )
                        continue

            logger.info(f'Successfully processed {len(result)} events')
            return result

        except Exception as e:
            logger.error(f'Error collecting information: {e}', exc_info=True)
            raise SystemError(f'Failed to collect information: {e}') from e


if __name__ == '__main__':
    pass
