import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any

import httpx
from fake_useragent import UserAgent
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from telegram.tg_utils import parse_show_date

logger = logging.getLogger(__name__)


class ProfticketAPIError(Exception):
    """
    Custom exception class for handling errors related to the Profticket API.

    This exception is raised whenever there is an issue with accessing or
    retrieving data from the Profticket API. It provides a means to catch and
    handle errors specific to the API, allowing for more granular error
    management and debugging.

    :ivar message: The error message associated with the exception.
    :type message: str
    :ivar status_code: The HTTP status code returned by the API when
    the error occurred.
    :type status_code: int
    """

    pass


class RateLimitError(ProfticketAPIError):
    """
    Exception raised for hitting the API rate limit.

    This exception is raised when the API rate limit is exceeded, indicating
    that too many requests have been made in a given time period.

    :ivar retry_after: Indicates how many seconds to wait before making a new
                       request.
    :type retry_after: int
    """

    def __init__(self, message: str, retry_after: float = 5.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EmptyResponseError(ProfticketAPIError):
    """
    Raised when the API response is empty.

    This exception is used to indicate that a request to the Profticket API
    was successful (i.e., no HTTP errors), but the response body was empty,
    which should not normally occur.
    """

    pass


class InvalidResponseFormat(ProfticketAPIError):
    """
    Exception raised for errors in the response format from the Profticket API.

    This exception is used to indicate issues with the format of the response
    returned by the Profticket API, which may not conform to the expected
    structure. This can help in debugging and handling errors related to
    response parsing or handling.
    """

    pass


class ConnectionTimeoutError(ProfticketAPIError):
    """
    Custom error class for handling connection timeouts.

    This error is raised when a connection attempt to the Profticket API
    exceeds the allowed time limit, indicating a timeout.

    :ivar message: Detailed error message describing the timeout.
    :type message: str
    :ivar retry_attempts: Number of retry attempts made before failing.
    :type retry_attempts: int
    """

    pass


def _retry_delay(retry_state: Any) -> float:
    error = retry_state.outcome.exception()
    if isinstance(error, RateLimitError):
        return error.retry_after
    return wait_exponential(multiplier=1, min=4, max=10)(retry_state)


def _retry_after(value: str | None) -> float:
    if value:
        try:
            delay = float(value)
            if not isfinite(delay):
                return 5.0
            return max(0.0, delay)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(
                    0.0,
                    (retry_at - datetime.now(UTC)).total_seconds(),
                )
            except TypeError, ValueError, OverflowError:
                pass
    return 5.0


class UserAgentProvider:
    """
    Provides random user-agent strings.

    This class is used to generate random user-agent strings for applications
    which need to simulate different clients.

    :ivar ua: Instance of UserAgent used to generate random user-agent strings.
    :type ua: UserAgent
    """

    def __init__(self):
        self.ua = UserAgent()

    def get_random_user_agent(self) -> str:
        return self.ua.random


class ProfticketsInfo:
    """
    ProfticketsInfo class handles interactions with the Profticket API.

    This class provides methods for fetching event data, managing cache,
    and handling requests with retry logic. It allows setting a target
    date for fetching events and retrieving information about free places
    for events.

    :ivar com_id: The company ID for fetching event data.
    :type com_id: str
    :ivar month: The target month for fetching event data.
    :type month: Optional[int]
    :ivar year: The target year for fetching event data.
    :type year: Optional[int]
    :ivar user_agent_provider: Provides random user agents for requests.
    :type user_agent_provider: UserAgentProvider
    :ivar client: The HTTP client for making asynchronous requests.
    :type client: httpx.AsyncClient
    :ivar _request_semaphore: Semaphore to limit concurrent requests.
    :type _request_semaphore: asyncio.Semaphore
    :ivar _show_cache: Cache storing information about shows.
    :type _show_cache: Dict[str, Dict[str, Any]]
    :ivar free_places: Dictionary mapping event IDs to the number of
    free places.
    :type free_places: Dict[str, int]
    """

    BASE_URL = 'https://widget.profticket.ru/api/event/list/?company_id='
    EVENT_DATA_URL = 'https://widget.profticket.ru/widget-api/events-data/'
    CUSTOMER_BUY_URL = 'https://spa.profticket.ru/customer/'
    SHOW_URL = 'https://widget.profticket.ru/api/event/show/'
    MAX_SCHEDULE_PAGES = 100

    PROXY_URL = settings.PROXY_URL

    def __init__(
        self, com_id: str, timeout: float = 30.0, concurrent_requests: int = 3
    ) -> None:
        """
        Initializes the instance with company ID, timeout,
        and concurrent requests.

        :param com_id: The company ID. It should be a non-empty string.
        :type com_id: str
        :param timeout: The timeout value for HTTP requests in seconds.
        Default is 30.0.
        :type timeout: float, optional
        :param concurrent_requests: The number of concurrent requests allowed.
        Default is 3.
        :type concurrent_requests: int, optional

        :raises ValueError: If `com_id` is not provided.
        """
        if not com_id:
            raise ValueError('Company ID is required')

        self.com_id = com_id
        self.month: int | None = None
        self.year: int | None = None

        self.user_agent_provider = UserAgentProvider()

        self.client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_keepalive_connections=5, max_connections=10
            ),
            headers={
                'Accept': 'application/json',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Connection': 'keep-alive',
            },
            verify=True,
        )
        self._request_semaphore = asyncio.Semaphore(concurrent_requests)
        self._show_cache: dict[str, dict[str, Any]] = {}
        self.free_places: dict[str, int | None] = {}

    def set_date(self, month: int, year: int) -> None:
        """
        Set the target date for an event.

        This function sets the specific month and year for an internal event
        or target.
        It updates the respective attributes of the instance and logs
        the new date.

        :param month: The month of the target date.
        :type month: int
        :param year: The year of the target date.
        :type year: int
        :return: None
        """
        datetime(year, month, 1)
        self.month = month
        self.year = year
        logger.info(f'Set target date to: {month}/{year}')

    def _create_url(self, page_num: int) -> str:
        """
        Generates a URL for retrieving event data for a specific page number,
        month,
        and year. Ensures that both month and year are set; otherwise, raises a
        ValueError.

        :param page_num: The page number for paginated event data.
        :type page_num: int
        :return: A formatted URL string.
        :rtype: str
        :raises ValueError: If month or year is not set.
        """
        if not all([self.month, self.year]):
            raise ValueError(
                'Month and year must be set before making requests'
            )

        url = (
            f'{self.BASE_URL}{self.com_id}'
            f'&type=events&page={page_num}&period_id=4&hall_id=&date='
            f'{self.year}.{self.month}'
            f'&name=&language=ru-RU'
        )
        logger.debug(f'Created URL for page {page_num}: {url}')
        return url

    def _get_headers(self) -> dict[str, str]:
        """
        Generate HTTP headers for a request with dynamic User-Agent,
        and static Accept,
        Accept-Language, and Connection headers.

        This method calls the `get_random_user_agent`
        from `user_agent_provider` to
        dynamically obtain a User-Agent string.
        The headers returned are suitable for making
        HTTP requests that require these specific headers to be set.

        :return: A dictionary containing HTTP headers for a request.
        :rtype: Dict[str, str]
        """
        headers = {
            'User-Agent': self.user_agent_provider.get_random_user_agent(),
            'Accept': 'application/json',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
        }
        return headers

    @retry(
        retry=retry_if_exception_type(
            (
                httpx.HTTPStatusError,
                httpx.ProxyError,
                ConnectionTimeoutError,
                RateLimitError,
            )
        ),
        stop=stop_after_attempt(settings.STOP_AFTER_ATTEMPT),
        wait=_retry_delay,
        reraise=True,
    )
    async def _make_request(self, url: str) -> httpx.Response:
        """
        Makes an asynchronous HTTP GET request to the specified URL, handling
        rate limits and specific exceptions.

        Retries are handled for HTTP status errors and Proxy errors through
        decorators. If a rate limit is hit, it waits for the specified time
        before retrying. Logs and raises errors for timeout, proxy, and other
        HTTP status errors accordingly.

        :param url: The URL to make the request to.
        :type url: str
        :return: The HTTP response object.
        :rtype: httpx.Response
        :raises RateLimitError: If the rate limit is exceeded.
        :raises ConnectionTimeoutError: If there is a connection timeout.
        :raises httpx.ProxyError: If there is a proxy error.
        :raises httpx.HTTPStatusError: If there is a general HTTP status error.
        :raises ProfticketAPIError: For any other raised exceptions
        during the request.
        """
        async with self._request_semaphore:
            try:
                headers = self._get_headers()
                response = await self.client.get(url, headers=headers)

                if response.status_code == 429:
                    retry_after = _retry_after(
                        response.headers.get('Retry-After')
                    )
                    logger.warning(f'Rate limit hit, waiting {retry_after}s')
                    raise RateLimitError('Rate limit exceeded', retry_after)

                response.raise_for_status()
                return response

            except httpx.TimeoutException as e:
                logger.error(f'Timeout error: {str(e)}')
                raise ConnectionTimeoutError(
                    f'Connection timeout: {str(e)}'
                ) from e

            except httpx.ProxyError as e:
                logger.error(f'Proxy error: {str(e)}')
                raise

            except httpx.HTTPStatusError as e:
                logger.error(
                    f'HTTP error: {e.response.status_code} - {e.response.text}'
                )
                raise

            except RateLimitError:
                raise

            except Exception as e:
                logger.error(f'Request error: {str(e)}')
                raise ProfticketAPIError(f'Request error: {str(e)}') from e

    async def _load_data(self) -> list[dict]:
        """Return a complete monthly schedule or reject the whole refresh."""
        items = []
        seen_pages = set()
        for page_num in range(1, self.MAX_SCHEDULE_PAGES + 1):
            response = await self._make_request(self._create_url(page_num))
            data = response.json()
            payload = data.get('response') if isinstance(data, dict) else None
            new_items = (
                payload.get('items') if isinstance(payload, dict) else None
            )
            if not isinstance(new_items, list) or any(
                not isinstance(item, dict) for item in new_items
            ):
                raise InvalidResponseFormat(
                    f'Invalid response format on page {page_num}'
                )
            if not new_items:
                return items
            fingerprint = hashlib.sha256(
                json.dumps(new_items, sort_keys=True).encode()
            ).digest()
            if fingerprint in seen_pages:
                raise InvalidResponseFormat('Schedule pagination repeats')
            seen_pages.add(fingerprint)
            items.extend(new_items)
            logger.info(
                f'Loaded {len(new_items)} items from page {page_num}. '
                f'Total: {len(items)}'
            )
            await asyncio.sleep(0.5)
        raise InvalidResponseFormat('Schedule pagination limit exceeded')

    def clear_cache(self) -> None:
        """
        Clear the cache containing shows.

        This method clears the internal cache that stores show-related
        information and logs the size of the cache before clearing.

        :return: None
        """
        cache_size = len(self._show_cache)
        self._show_cache.clear()
        logger.info(f'Cleared cache containing {cache_size} shows')

    async def _places(self) -> None:
        """
        Fetches the number of free places for events asynchronously.

        This method constructs a URL using the class's `EVENT_DATA_URL` and
        `com_id` attributes, then makes an asynchronous request to that URL
        to retrieve event data. The response is parsed to extract the number
        of free seats for each event, and this information is saved in the
        `free_places` attribute. If an error occurs during this process,
        an error is logged, the `free_places` attribute is reset to an
        empty dictionary, and a `ProfticketAPIError` is raised.

        :raises ProfticketAPIError: If there is an error while trying to
                                     load places data.
        :rtype: None
        """
        places_url = f'{self.EVENT_DATA_URL}{self.com_id}/'
        try:
            response = await self._make_request(places_url)
            places_ben = response.json()
            places_events = (
                places_ben.get('events')
                if isinstance(places_ben, dict)
                else None
            )
            if not isinstance(places_events, dict):
                raise InvalidResponseFormat('Missing inventory events')
            free_places = {}
            for event_id, inventory in places_events.items():
                if not isinstance(inventory, dict):
                    raise InvalidResponseFormat('Invalid inventory event')
                seats = inventory.get('seats')
                if seats is not None and (type(seats) is not int or seats < 0):
                    raise InvalidResponseFormat('Invalid inventory count')
                free_places[str(event_id)] = seats
            self.free_places = free_places
            logger.info(
                f'Loaded free places info for {len(self.free_places)} events'
            )
        except Exception as e:
            logger.error(f'Error loading places: {str(e)}')
            self.free_places = {}
            raise ProfticketAPIError(f'Failed to load places: {str(e)}') from e

    def _generate_buy_link(self, event_id: str, show_id: str) -> str:
        """
        Generate a URL link for purchasing tickets for a specific
        event and show.

        This method combines the customer buy URL with the provided
        company ID, show ID,
        event ID, and language details to create a unique ticket purchase link.

        :param event_id: The unique identifier for the event.
        :type event_id: str
        :param show_id: The unique identifier for the show.
        :type show_id: str
        :return: A string containing the generated URL for buying tickets.
        :rtype: str
        """
        return (
            f'{self.CUSTOMER_BUY_URL}{self.com_id}/shows/{show_id}'
            f'?eventsIds%5B%5D={event_id}&language=ru-RU'
        )

    async def _get_show_details(self, show_id: str) -> dict[str, Any]:
        """Cache verified details only for the current refresh."""
        if show_id in self._show_cache:
            return self._show_cache[show_id]
        url = f'{self.SHOW_URL}?company_id={self.com_id}&show_id={show_id}'
        response = await self._make_request(url)
        data = response.json()
        payload = data.get('response') if isinstance(data, dict) else None
        show_detail = (
            payload.get('show_detail') if isinstance(payload, dict) else None
        )
        if not isinstance(show_detail, dict) or not show_detail:
            raise InvalidResponseFormat(f'Missing show details: {show_id}')
        actors = show_detail.get('actors')
        if actors is None:
            actors = []
        if not isinstance(actors, list) or any(
            not isinstance(actor, str) for actor in actors
        ):
            raise InvalidResponseFormat(f'Invalid show actors: {show_id}')
        self._show_cache[show_id] = {
            'actors': actors,
            'details': show_detail,
        }
        return self._show_cache[show_id]

    async def collect_full_info(self) -> dict[str, Any]:
        """
        Collects detailed information about events and shows.

        This method performs the following steps:
        1. Load basic data.
        2. Collect unique show IDs.
        3. Load information about places.
        4. Process show details in batches.
        5. Compile the final result with relevant event details.

        :raises ProfticketAPIError: if any exception occurs during the process.
        :return: A dictionary with event details keyed by event ID.
        :rtype: Dict[str, Any]
        """
        try:
            if self.month is None or self.year is None:
                raise ValueError('Set month and year before collection')
            self.clear_cache()
            items = await self._load_data()
            if not items:
                logger.warning('No items found')
                return {}

            events = []
            event_ids = set()
            for item in items:
                item_events = item.get('events')
                if not isinstance(item_events, list):
                    raise InvalidResponseFormat('Missing schedule events')
                for event in item_events:
                    show = (
                        event.get('show') if isinstance(event, dict) else None
                    )
                    if not isinstance(show, dict):
                        raise InvalidResponseFormat('Missing event show')
                    event_id = event.get('id')
                    show_id = show.get('show_id')
                    if (
                        type(event_id) not in (str, int)
                        or not str(event_id).strip()
                        or not event_id
                        or type(show_id) not in (str, int)
                    ):
                        raise InvalidResponseFormat('Missing event identity')
                    try:
                        if int(show_id) <= 0:
                            raise ValueError('Invalid show ID')
                    except ValueError as exc:
                        raise InvalidResponseFormat(
                            'Invalid event show ID'
                        ) from exc
                    event_id, show_id = str(event_id), str(show_id)
                    if event_id in event_ids:
                        raise InvalidResponseFormat('Duplicate event identity')
                    if any(
                        not isinstance(event.get(field), str)
                        or not event[field].strip()
                        for field in ('show_name', 'date_formatted')
                    ):
                        raise InvalidResponseFormat('Missing event title/date')
                    try:
                        event_date = datetime.fromisoformat(
                            event['date_formatted']
                        )
                    except ValueError:
                        event_date = parse_show_date(event['date_formatted'])
                    if event_date == datetime.min or (
                        event_date.year,
                        event_date.month,
                    ) != (self.year, self.month):
                        raise InvalidResponseFormat(
                            'Event date does not match the requested month'
                        )
                    pushkin = event.get('pushkin_card') or {}
                    if not isinstance(pushkin, dict):
                        raise InvalidResponseFormat('Invalid Pushkin card')
                    event_ids.add(event_id)
                    events.append((event, show, event_id, show_id, pushkin))

            unique_shows = sorted({row[3] for row in events})
            logger.info(f'Found {len(unique_shows)} unique shows to process')

            await self._places()

            batch_size = 5
            for i in range(0, len(unique_shows), batch_size):
                batch = await asyncio.gather(
                    *(
                        self._get_show_details(show_id)
                        for show_id in unique_shows[i : i + batch_size]
                    ),
                    return_exceptions=True,
                )
                for outcome in batch:
                    if isinstance(outcome, BaseException):
                        raise outcome
                await asyncio.sleep(0.5)

            result = {}
            for event, show, event_id, show_id, pushkin in events:
                result[event_id] = {
                    'id': event_id,
                    'show_id': show_id,
                    'theater': event.get('location_name'),
                    'scene': event.get('location_scene'),
                    'show_name': event['show_name'],
                    'date': event['date_formatted'],
                    'duration': show.get('duration'),
                    'age': show.get('age'),
                    'seats': self.free_places.get(event_id),
                    'image': show.get('image_url'),
                    'annotation': event.get('annotation'),
                    'min_price': event.get('min_price'),
                    'max_price': event.get('max_price'),
                    'pushkin': pushkin.get('can_buy', False),
                    'buy_link': self._generate_buy_link(event_id, show_id),
                    'actors': self._show_cache[show_id]['actors'],
                }

            logger.info(f'Successfully processed {len(result)} events')
            return result

        except Exception as e:
            logger.error(f'Error collecting information: {str(e)}')
            raise ProfticketAPIError(
                f'Failed to collect information: {str(e)}'
            ) from e


if __name__ == '__main__':
    pass
