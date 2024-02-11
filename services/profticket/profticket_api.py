import asyncio
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


class ProfticketsInfo:
    BASE_URL = 'https://widget.profticket.ru/api/event/list/?company_id='
    EVENT_DATA_URL = 'https://widget.profticket.ru/widget-api/events-data/'
    CUSTOMER_BUY_URL = 'https://spa.profticket.ru/customer/'
    SHOW_URL = 'https://widget.profticket.ru/api/event/show/'

    def __init__(self, com_id):
        if com_id is None:
            raise ValueError('Не указан ID компании')
        self.com_id = com_id
        self.month = None
        self.year = None
        self.client = httpx.AsyncClient()
        logger.info(f'Initializing with com_id: {com_id}')

    def set_date(self, month, year):
        self.month = month
        self.year = year
        logger.info(f'Setting date: {self.month}/{self.year}')

    def _create_url(self, page_num):
        logger.info(f'Creating url:{page_num} for com_id: {self.com_id}')
        return (
            f'{self.BASE_URL}{self.com_id}'
            f'&type=events&page={page_num}&period_id=4&hall_id=&date='
            f'{self.year}.{self.month}'
            f'&name=&language=ru-RU'
        )

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(3))
    async def _load_data(self):
        page_num = 1
        items = []
        logger.info(f'Loading data for page: {page_num}')
        while True:
            url = self._create_url(page_num)
            response = await self.client.get(url)
            response_json = response.json()
            if 'response' not in response_json:
                raise ValueError('Проблемы с получением данных с сервера')

            new_items = response_json.get('response').get('items')
            if not new_items:
                break

            items.extend(new_items)
            page_num += 1
            logger.info(f'Len items for page {page_num}: {len(new_items)}')
        return items

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(3))
    async def _places(self):
        places_url = f'{self.EVENT_DATA_URL}{self.com_id}/'
        response = await self.client.get(places_url)
        places_ben = response.json()
        places_events = places_ben.get('events')
        self.free_places = {
            event_id: free_places['seats']
            for event_id, free_places in places_events.items()
        }
        logger.info('Get free places')

    async def _get_event_buy_link(self, event):
        event_id = event.get('id')
        show_id = event.get('show').get('show_id')
        buy_link = (
            f'{self.CUSTOMER_BUY_URL}{self.com_id}/shows/{show_id}'
            f'?eventsIds%5B%5D={event_id}&language=ru-RU'
        )
        event['buy_link'] = buy_link

    async def _get_buy_link(self, items):
        tasks = [
            self._get_event_buy_link(event)
            for get_info in items
            for event in get_info.get('events')
        ]
        await asyncio.gather(*tasks)
        logger.info('Get len buy links')

    @retry(stop=stop_after_attempt(10), wait=wait_fixed(3))
    async def _get_event_actors(self, event):
        show_id = event.get('show').get('show_id')
        actors_url = (
            f'{self.SHOW_URL}?company_id'
            f'={self.com_id}&show_id={show_id}'
        )
        response = await self.client.get(actors_url)
        actors_data = response.json()
        actors_list = (
            actors_data.get('response')
            .get('show_detail', '')
            .get('actors', '')
        )
        event['actors'] = actors_list if actors_list else ['']

    async def _get_show_actors(self, items):
        tasks = [
            self._get_event_actors(event)
            for get_info in items
            for event in get_info.get('events')
        ]
        await asyncio.gather(*tasks)
        logger.info('Get show actors')

    async def collect_full_info(self):
        try:
            items = await self._load_data()
            tasks_result = await asyncio.gather(
                self._places(),
                self._get_buy_link(items),
                self._get_show_actors(items),
                return_exceptions=True
            )

            for task_result in tasks_result:
                if isinstance(task_result, Exception):
                    logger.error(f'Ошибка в задаче: {task_result}',
                                 exc_info=True)

            result = {}
            for get_info in items:
                for event in get_info.get('events', []):
                    event_id = event.get('id')
                    if not event_id:
                        continue
                    result[event_id] = {
                        'id': event_id,
                        'show_id': event.get('show', {}).get('show_id'),
                        'theater': event.get('location_name'),
                        'scene': event.get('location_scene'),
                        'show_name': event.get('show_name'),
                        'date': event.get('date_formatted'),
                        'duration': event.get('show', {}).get('duration'),
                        'age': event.get('show', {}).get('age'),
                        'seats': self.free_places.get(event_id),
                        'image': event.get('show', {}).get('image_url'),
                        'annotation': event.get('annotation'),
                        'min_price': event.get('min_price'),
                        'max_price': event.get('max_price'),
                        'pushkin': event.get('pushkin_card', {}).get(
                            'can_buy'),
                        'buy_link': event.get('buy_link'),
                        'actors': event.get('actors', ''),
                    }
            logger.info(f'Finished parsing get {len(result)} data')
            return result
        except Exception as e:
            logger.error(
                f'Неожиданная ошибка при получении полной информации: {e}',
                exc_info=True)
            raise SystemError(
                f'Ошибка при получении полной информации: {e}') from e
