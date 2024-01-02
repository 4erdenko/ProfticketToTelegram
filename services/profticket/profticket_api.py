
import httpx
import asyncio

class ProfticketsInfo:
    BASE_URL = 'https://widget.profticket.ru/api/event/list/?company_id='
    EVENT_DATA_URL = 'https://widget.profticket.ru/widget-api/events-data/'
    CUSTOMER_BUY_URL = 'https://spa.profticket.ru/customer/'

    def __init__(self, com_id):
        if com_id is None:
            raise ValueError('Не указан ID компании')
        self.com_id = com_id
        self.month = None
        self.year = None
        self.client = httpx.AsyncClient()

    def set_date(self, month, year):
        self.month = month
        self.year = year

    def _create_url(self, page_num):
        return (
            f'{self.BASE_URL}{self.com_id}'
            f'&type=events&page={page_num}&period_id=4&hall_id=&date='
            f'{self.year}.{self.month}'
            f'&name=&language=ru-RU'
        )

    async def _load_data(self):
        page_num = 1
        items = []

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

        return items

    async def _places(self):
        places_url = f'{self.EVENT_DATA_URL}{self.com_id}/'
        response = await self.client.get(places_url)
        places_ben = response.json()
        places_events = places_ben.get('events')
        self.free_places = {
            event_id: free_places['seats']
            for event_id, free_places in places_events.items()
        }

    async def _get_buy_link(self, items):
        for get_info in items:
            for event in get_info.get('events'):
                event_id = event.get('id')
                show_id = event.get('show').get('show_id')
                buy_link = (
                    f'{self.CUSTOMER_BUY_URL}{self.com_id}/shows/{show_id}'
                    f'?eventsIds%5B%5D={event_id}&language=ru-RU'
                )
                event['buy_link'] = buy_link

    async def get_full_info(self):
        try:
            items = await self._load_data()
            await self._places()
            await self._get_buy_link(items)

            result = {}
            for get_info in items:
                for event in get_info.get('events'):
                    result[event.get('id')] = {
                        'id': event.get('id'),
                        'show_id': event.get('show').get('show_id'),
                        'theater': event.get('location_name'),
                        'scene': event.get('location_scene'),
                        'show_name': event.get('show_name'),
                        'date': event.get('date_formatted'),
                        'duration': event.get('show').get('duration'),
                        'age': event.get('show').get('age'),
                        'seats': self.free_places.get(event.get('id')),
                        'image': event.get('show').get('image_url'),
                        'annotation': event.get('annotation'),
                        'min_price': event.get('min_price'),
                        'max_price': event.get('max_price'),
                        'pushkin': event.get('pushkin_card').get('can_buy'),
                        'buy_link': event.get('buy_link'),
                    }
            return result
        except Exception as e:
            raise SystemError(f'Ошибка при получении полной информации: {e}')

    async def close(self):
        await self.client.aclose()


async def main():
    from pprint import pprint

    com_id = 30
    proftickets_info = ProfticketsInfo(com_id)

    proftickets_info.set_date('01', '2024')
    try:
        full_info = await proftickets_info.get_full_info()
        pprint(full_info)
    except Exception as e:
        print(f'Ошибка: {e}')
    finally:
        await proftickets_info.close()

if __name__ == '__main__':
    asyncio.run(main())
