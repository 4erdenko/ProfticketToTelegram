import httpx

from settings.config import (COM_ID, MAX_MSG_LEN, P_SHOWS, get_current_month,
                             get_current_year, pluralize)

result_dict = {}


class ProfticketsInfo:
    """
    Class for information about events from spa.profticket.ru
    """

    def __init__(self, com_id=None, page_num=None, month=None, year=None):
        if month is None:
            month = get_current_month()
        if year is None:
            year = get_current_year()
        if page_num is None:
            page_num = 1
        if com_id is None:
            raise ValueError('Не указан ID компании')
        self.com_id = com_id
        self.page_num = page_num
        self.month = month
        self.year = year
        self.event_id = ''
        self.show_id = ''
        self.main_url = (
            f'https://widget.profticket.ru/api/event/list'
            f'/?company_id={com_id}&type=events&page='
            f'{page_num}&period_id=4&hall_id=&date={year}.{month}'
            f'&name=&language=ru-RU'
        )
        self.page = httpx.get(self.main_url)
        self.main_json = self.page.json()
        if 'response' not in self.main_json:
            raise ValueError('Проблемы с получением словаря с сервера!')
        self.page_count = self.main_json.get('response').get('page_count')
        self.items = self.main_json.get('response').get('items')
        if self.page_count > 1:
            for page_num in range(2, self.page_count + 1):
                self.main_url = (
                    f'https://widget.profticket.ru/api/event/list'
                    f'/?company_id={com_id}&type=events'
                    f'&page={page_num}&period_id=4&hall_id='
                    f'&date={year}.{month}'
                    f'&name=&language=ru-RU'
                )
                self.page = httpx.get(self.main_url)
                self.main_json = self.page.json()
                self.items += self.main_json.get('response').get('items')

    def _places(self):
        """
        Retrieves a dictionary with the number of available
        seats for each event.

        Returns:
            dict: A dictionary containing event IDs as keys and the number
            of available seats as values.
        """
        self.places_url = (
            f'https://widget.profticket.ru/widget-api/'
            f'events-data/{self.com_id}/'
        )
        self.places_page = httpx.get(self.places_url)
        self.places_ben = self.places_page.json()
        self.places_events = self.places_ben.get('events')
        self.free_places = {}
        self.event_ids = {}
        for event_id, free_places in self.places_events.items():
            seats = free_places['seats']
            self.free_places[event_id] = seats
            self.event_ids[event_id] = event_id

    def _get_buy_link(self):
        """
        Generates a ticket purchase link for each event.

        Returns:
            None: The method modifies the 'buy_link' attribute for each event
            in the 'items' attribute of the object.
        """
        for get_info in self.items:
            for event in get_info.get('events'):
                self.event_id = event.get('id')
                self.show_id = event.get('show').get('show_id')
                self.buy_link = (
                    f'https://spa.profticket.ru/customer/'
                    f'{self.com_id}/shows/'
                    f'{self.show_id}?eventsIds%5B%5D='
                    f'{self.event_id}&language=ru-RU'
                )
                event['buy_link'] = self.buy_link

    def get_full_info(self):
        """
        Retrieves a complete dictionary with performance information.

        Returns:
            dict: A dictionary containing all performance details
            such as event ID, theater, scene, show name, date, duration,
            age restriction, available seats, image URL, annotation,
            price range, Pushkin card availability, and buying link.

        Raises:
            ValueError: If there is a problem obtaining the dictionary
            with available seats.
        """
        try:
            self._places()
        except Exception as e:
            raise ValueError(f'Проблемы с получением словаря с местами {e}')
        result = {}
        self._get_buy_link()
        for get_info in self.items:
            for event in get_info.get('events'):
                my_dict = {
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

                result[event.get('id')] = my_dict
        return result


def get_special_info(month=None, telegram_id=None):
    """
    Function to get all or personal performances in a specified month.

    Args:
        month (int, optional): Specifies an integer between 1 and 12.
            If not specified, the default is the current month.
        telegram_id (int, optional): If specified, a list of performances
            that are assigned to the user in config.py will be returned.

    Returns:
        str: A list of performances for the specified month.
    """
    p = ProfticketsInfo(month=month, com_id=COM_ID)
    result = p.get_full_info()
    if not result:
        return 'Спектаклей в этом месяце нет.'
    msg = ''
    total = ''
    show_count = 0
    for item in result:
        date = result[item]['date']
        show_name = result[item]['show_name'].strip()
        seats = int(result[item]['seats'])
        if telegram_id is None:
            show_count += 1
            msg += get_result_message(seats, show_name, date)
            total = f'Всего {show_count} {pluralize("спектакль", show_count)}🌚'
        else:
            if show_name in P_SHOWS.get(telegram_id):
                show_count += 1
                msg += get_result_message(seats, show_name, date)
                total = (
                    f'Всего {show_count} {pluralize("спектакль", show_count)}🌚'
                )
            elif msg == '':
                total = 'Нет спектаклей в этом месяце.'

    return f'{msg}{total}'


def get_result_message(seats, show_name, date):
    """
    Function to create a message with information about a performance.

    Args:
        seats (int): Number of available seats.
        show_name (str): Name of the performance.
        date (str): Date of the performance.

    """
    if seats == 0:
        seats_text = '<code>SOLD OUT</code>'
    else:
        seats_text = f'Билетов: <code>{seats}</code>'

    return (
        f'📅<strong> {date}</strong>\n'
        f'💎 {show_name}\n'
        f'🎫 {seats_text}\n'
        '------------------------\n'
    )


def split_message_by_separator(
    message, separator='\n------------------------\n', max_length=MAX_MSG_LEN
):
    """

    Splits a message into chunks based on the provided separator.
    Ensures that each chunk is within the maximum length.

    Args:
        message (str):The message to split.
        separator (str, optional):The separator to split the message.
        max_length (int, optional):The maximum length of each chunk.
            Default is 4096.

    Returns:
        list: A list of message chunks.
    """
    chunks = []
    current_chunk = ''

    for block in message.split(separator):
        if len(current_chunk) + len(block) + len(separator) > max_length:
            chunks.append(current_chunk.rstrip())
            current_chunk = ''

        current_chunk += block + separator

    if current_chunk:
        chunks.append(current_chunk.rstrip())

    return chunks
