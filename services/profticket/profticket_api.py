import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from fake_useragent import UserAgent
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from config import settings

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

    pass


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

    PROXY_URL = settings.PROXY_URL

    def __init__(
        self, com_id: str, timeout: float = 30.0, concurrent_requests: int = 3
    ):
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
        self.month: Optional[int] = None
        self.year: Optional[int] = None

        proxies = {'http://': self.PROXY_URL, 'https://': self.PROXY_URL}

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
            # proxies=proxies,
            verify=False,
        )
        self._request_semaphore = asyncio.Semaphore(concurrent_requests)
        self._show_cache: Dict[str, Dict[str, Any]] = {}
        self.free_places: Dict[str, int] = {}

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

    def _get_headers(self) -> Dict[str, str]:
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
            (httpx.HTTPStatusError, httpx.ProxyError)
        ),
        stop=stop_after_attempt(settings.STOP_AFTER_ATTEMPT),
        wait=wait_exponential(multiplier=1, min=4, max=10),
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
                    retry_after = int(response.headers.get('Retry-After', 5))
                    logger.warning(f'Rate limit hit, waiting {retry_after}s')
                    await asyncio.sleep(retry_after)
                    raise RateLimitError('Rate limit exceeded')

                response.raise_for_status()
                return response

            except httpx.TimeoutException as e:
                logger.error(f'Timeout error: {str(e)}')
                raise ConnectionTimeoutError(f'Connection timeout: {str(e)}')

            except httpx.ProxyError as e:
                logger.error(f'Proxy error: {str(e)}')
                raise

            except httpx.HTTPStatusError as e:
                logger.error(
                    f'HTTP error: {e.response.status_code} - {e.response.text}'
                )
                raise

            except Exception as e:
                logger.error(f'Request error: {str(e)}')
                raise ProfticketAPIError(f'Request error: {str(e)}')

    async def _load_data(self) -> List[dict]:
        """
        Loads data asynchronously from a paginated API endpoint.

        This method iterates through paginated responses from an API,
        makes requests,
        handles errors, and collects items into a list until no more
        items are available
        or a maximum number of consecutive errors is reached. Upon encountering
        errors, it logs them and decides whether to continue or stop
        based on the
        number of consecutive errors and the availability of partial data.

        :return: List of dictionaries containing the loaded items.
        :rtype: List[dict]
        :raises InvalidResponseFormat: If the API response format is invalid.
        :raises ProfticketAPIError: If an API error occurs and no partial
        data is available.
        """
        items = []
        page_num = 1
        consecutive_errors = 0
        max_consecutive_errors = 3
        stop_reason = None

        while True:
            try:
                url = self._create_url(page_num)
                response = await self._make_request(url)
                response_json = response.json()

                if 'response' not in response_json:
                    stop_reason = 'Invalid response format'
                    raise InvalidResponseFormat(
                        f'Invalid response format on page {page_num}'
                    )

                new_items = response_json['response'].get('items', [])
                if not new_items:
                    stop_reason = 'No more items'
                    logger.info('No more items to load')
                    break

                items.extend(new_items)
                logger.info(
                    f'Loaded {len(new_items)} items from page {page_num}. '
                    f'Total: {len(items)}'
                )
                page_num += 1
                consecutive_errors = 0
                await asyncio.sleep(0.5)

            except ProfticketAPIError as e:
                consecutive_errors += 1
                stop_reason = f'API Error: {str(e)}'
                logger.error(f'Error loading page {page_num}: {str(e)}')

                if consecutive_errors >= max_consecutive_errors:
                    logger.warning(
                        f'Stopping after {consecutive_errors} '
                        f'consecutive errors'
                    )
                    break

                if items:
                    logger.info(
                        f'Returning partial data: {len(items)} items. '
                        f'Reason: {stop_reason}'
                    )
                    return items
                raise

            except Exception as e:
                stop_reason = f'Unexpected error: {str(e)}'
                logger.error(f'Unexpected error on page {page_num}: {str(e)}')
                if items:
                    logger.info(
                        f'Returning partial data: {len(items)} items. '
                        f'Reason: {stop_reason}'
                    )
                    return items
                raise ProfticketAPIError(f'Failed to load data: {str(e)}')

        logger.info(
            f'Completed loading {len(items)} items. Stop reason: {stop_reason}'
        )
        return items

    def clear_cache(self):
        """
        Clear the cache containing shows.

        This method clears the internal cache that stores show-related
        information and logs the size of the cache before clearing.

        :return: None
        """
        cache_size = len(self._show_cache)
        self._show_cache.clear()
        logger.info(f'Cleared cache containing {cache_size} shows')

    async def _places(self):
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
            logger.error(f'Error loading places: {str(e)}')
            self.free_places = {}
            raise ProfticketAPIError(f'Failed to load places: {str(e)}')

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

    async def _get_show_details(self, show_id: str) -> Dict[str, Any]:
        """
        Fetches and returns the detailed information of a show, optionally
        using cached data.

        This asynchronous method attempts to fetch show details from a remote
        service. If there is a cache hit, it returns the cached data to
        save a network call. If the data is fetched successfully,
        it updates the cache
        with the new data.

        :param show_id: The unique identifier of the show to retrieve
        details for.
        :type show_id: str
        :return: A dictionary containing the show details and list of actors.
        :rtype: Dict[str, Any]
        """
        if show_id in self._show_cache:
            logger.debug(f'Using cached data for show_id: {show_id}')
            return self._show_cache[show_id]

        url = f'{self.SHOW_URL}?company_id={self.com_id}&show_id={show_id}'
        try:
            response = await self._make_request(url)
            data = response.json()
            show_detail = data.get('response', {}).get('show_detail', {})

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
            logger.error(
                f'Error fetching show details for {show_id}: {str(e)}'
            )
            return {'actors': [''], 'details': {}}

    async def collect_full_info(self) -> Dict[str, Any]:
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
            items = await self._load_data()
            if not items:
                logger.warning('No items found')
                return {}

            unique_shows = {
                event.get('show', {}).get('show_id')
                for item in items
                for event in item.get('events', [])
            }
            unique_shows.discard(None)
            logger.info(f'Found {len(unique_shows)} unique shows to process')

            await self._places()

            show_tasks = [
                self._get_show_details(show_id) for show_id in unique_shows
            ]
            logger.info(f'Processing {len(show_tasks)} shows')

            batch_size = 5
            for i in range(0, len(show_tasks), batch_size):
                batch = show_tasks[i : i + batch_size]
                if batch:
                    await asyncio.gather(*batch)
                    await asyncio.sleep(0.5)

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
                            f'Error processing event {event_id}: {str(e)}'
                        )
                        continue

            logger.info(f'Successfully processed {len(result)} events')
            return result

        except Exception as e:
            logger.error(f'Error collecting information: {str(e)}')
            raise ProfticketAPIError(
                f'Failed to collect information: {str(e)}'
            )


if __name__ == '__main__':
    pass
