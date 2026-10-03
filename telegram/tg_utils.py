import asyncio
import string
import unicodedata
from datetime import datetime
from html import escape
from html.parser import HTMLParser

import pytz
from aiogram.types import LinkPreviewOptions, Message
from dateutil.relativedelta import relativedelta

from config import settings
from telegram.lexicon.lexicon_ru import (
    INVENTORY_UNKNOWN,
    LEXICON_MONTHS_RU,
    PERFORMANCE_FALLBACKS,
)

MONTHS_GENITIVE_RU = {
    'января': 1,
    'февраля': 2,
    'марта': 3,
    'апреля': 4,
    'мая': 5,
    'июня': 6,
    'июля': 7,
    'августа': 8,
    'сентября': 9,
    'октября': 10,
    'ноября': 11,
    'декабря': 12,
}


def get_current_month_year():
    """
    Get the current time in Moscow timezone.

    Returns:
        tuple: A tuple containing the current month and year.
    """
    moscow_tz = pytz.timezone('Europe/Moscow')
    current_time = datetime.now(moscow_tz)
    return current_time.month, current_time.year


def get_next_month_year():
    """
    Get the next month and year based on the current time in Moscow timezone.

    Returns:
        tuple: A tuple containing the next month and year.
    """
    moscow_tz = pytz.timezone('Europe/Moscow')
    next_time = datetime.now(moscow_tz) + relativedelta(months=+1)
    return next_time.month, next_time.year


def get_three_months():
    """
    Get information about current month and two
    following months in Moscow timezone.

    Returns:
        tuple: A tuple containing three tuples,
        each with (month_number, month_name).
    """
    moscow_tz = pytz.timezone('Europe/Moscow')
    current_time = datetime.now(moscow_tz)

    months = []
    for i in range(3):
        month_date = current_time + relativedelta(months=i)
        month_number = month_date.month
        month_name = month_date.strftime('%B')  # Full month name in English
        month_name_ru = LEXICON_MONTHS_RU[month_name]
        months.append((month_number, month_name_ru, month_date.year))

    return tuple(months)


def parse_show_date(date_str: str | None) -> datetime:
    """Parse a Russian formatted show date."""
    if date_str is None:
        return datetime.min
    try:
        return datetime.strptime(date_str, '%d.%m.%Y, %H:%M')
    except ValueError:
        pass
    try:
        date_part, _, time_part = date_str.partition(',')
        day_str, month_ru, year_str = date_part.strip().split()
        hour_min = time_part.rsplit(',', 1)[-1].strip()
        month = MONTHS_GENITIVE_RU.get(month_ru.lower())
        if not month:
            raise ValueError('Unknown month name')
        fmt = '%d.%m.%Y %H:%M'
        return datetime.strptime(
            f'{day_str}.{month}.{year_str} {hour_min}',
            fmt,
        )
    except Exception:
        return datetime.min


def get_result_message(
    seats: int | None,
    previous_seats: int | None,
    show_name: str | None,
    date: str | None,
    buy_link: str | None,
) -> str:
    """
    Function to create a message with information about a performance.

    Args:
        seats (int): Number of available seats.
        previous_seats (int): Number of seats from previous update
        show_name (str): Name of the performance.
        date (str): Date of the performance.
        buy_link (str): Ticket purchase link.

    """
    buy_link = escape((buy_link or '').strip(), quote=True)
    show_name = escape(show_name or PERFORMANCE_FALLBACKS['name'])
    date = escape(date or PERFORMANCE_FALLBACKS['date'])
    if seats is None:
        seats_text = (
            f'<a href="{buy_link}">{INVENTORY_UNKNOWN}</a>'
            if buy_link
            else PERFORMANCE_FALLBACKS['inventory']
        )
    elif seats == 0:
        seats_text = 'Билетов пока нет'
    else:
        seats_text = f'Билетов: <b>{seats}</b>'

    seats_diff = ''
    if (
        seats is not None
        and previous_seats is not None
        and seats != previous_seats
    ):
        diff = seats - previous_seats
        direction = 'меньше' if diff < 0 else 'больше'
        seats_diff = f' (на {abs(diff)} {direction})'

    tickets = f'🎟 {seats_text}{seats_diff}'
    if seats is not None and seats > 0 and buy_link:
        tickets += f' · <a href="{buy_link}">Купить</a>'

    return f'🎭 <b>{show_name}</b>\n📅 {date}\n{tickets}\n\n'


def _text_length(text: str) -> int:
    """Count Telegram text offsets in UTF-16 code units."""
    return len(text.encode('utf-16-le')) // 2


class _HTMLMessageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, str]] = []
        self.runs: list[tuple[str, tuple[tuple[str, str], ...]]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.tags.append((tag, self.get_starttag_text()))

    def handle_endtag(self, tag: str) -> None:
        if not self.tags or self.tags[-1][0] != tag:
            raise ValueError('Unbalanced HTML message')
        self.tags.pop()

    def handle_data(self, data: str) -> None:
        self.runs.append((data, tuple(self.tags)))

    def render(self, start: int, end: int) -> str:
        parts: list[str] = []
        active: tuple[tuple[str, str], ...] = ()
        offset = 0
        for data, tags in self.runs:
            run_end = offset + len(data)
            if run_end > start and offset < end:
                common = 0
                for current, previous in zip(tags, active, strict=False):
                    if current != previous:
                        break
                    common += 1
                parts.extend(
                    f'</{tag}>' for tag, _ in reversed(active[common:])
                )
                parts.extend(markup for _, markup in tags[common:])
                parts.append(
                    escape(
                        data[max(0, start - offset) : end - offset],
                        quote=False,
                    )
                )
                active = tags
            offset = run_end
            if offset >= end:
                break
        parts.extend(f'</{tag}>' for tag, _ in reversed(active))
        return ''.join(parts).rstrip()


def split_message_by_separator(
    message: str,
    separator: str = '\n\n',
    max_length: int = settings.MAX_MSG_LEN,
) -> list[str]:
    """
    Splits a message into chunks based on the provided separator.
    Ensures that each chunk is within the maximum length.

    Args:
        message: The message to split
        separator: The separator to split the message
        max_length: The maximum length of each chunk

    Returns:
        list: A list of message chunks
    """
    if max_length < 2:
        raise ValueError('Message limit must fit a Unicode character')
    if not message.strip():
        return []
    parser = _HTMLMessageParser()
    parser.feed(message)
    parser.close()
    parser.runs.append((separator, ()))
    text = ''.join(data for data, _ in parser.runs)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start
        length = 0
        while end < len(text):
            size = 2 if ord(text[end]) > 0xFFFF else 1
            if length + size > max_length:
                break
            length += size
            end += 1
        if end < len(text) and separator:
            boundary = text.rfind(separator, start, end)
            if boundary >= start:
                end = boundary + len(separator)
        if text[start:end].strip():
            chunks.append(parser.render(start, end))
        start = end
    return chunks


async def send_chunks_edit(
    chat_id: int, message: Message, text: str, **kwargs
) -> None:
    """
    Sends a message in chunks. The first chunk is sent using msg.edit_text,
    and the subsequent chunks are sent using message.answer.

    Args:
        chat_id: The ID of the chat where the message will be sent
        message: The message object
        text: The message text to be sent
        **kwargs: Additional arguments to pass to the message sending functions
    """
    kwargs.setdefault(
        'link_preview_options', LinkPreviewOptions(is_disabled=True)
    )
    chunks = split_message_by_separator(text)

    if chunks:
        await message.edit_text(chunks.pop(0), **kwargs)
        for chunk in chunks:
            await message.answer(chunk, **kwargs)
            await asyncio.sleep(1)


def normalize_actor_name(name: str) -> str:
    """Use the same Unicode and whitespace normalization for both casts."""
    punctuation = string.punctuation.replace('-', '').replace("'", '')
    text = unicodedata.normalize('NFKC', name).casefold()
    text = text.translate(str.maketrans('‐‑‒–—’', "-----'"))
    text = text.translate(str.maketrans('', '', punctuation))
    return ' '.join(text.split())


async def check_text(message: Message) -> str | None:
    """
    Check if message text is valid name format.

    Args:
        message: Message to check

    Returns:
        str: Cleaned text if valid, None otherwise
    """
    if isinstance(message.text, str) and not any(
        char in message.text for char in '<>&'
    ):
        text = normalize_actor_name(message.text)
        words = text.split()
        if len(words) == 2 and all(
            word[0].isalpha()
            and word[-1].isalpha()
            and all(char.isalpha() or char in "-'" for char in word)
            for word in words
        ):
            return text
    return None


async def send_chunks_answer(message: Message, text: str, **kwargs) -> None:
    """
    Sends a message in chunks using message.answer for all parts.

    Args:
        message: The message object
        text: The message text to be sent
        **kwargs: Additional arguments to pass to message.answer
    """
    kwargs.setdefault(
        'link_preview_options', LinkPreviewOptions(is_disabled=True)
    )
    chunks = split_message_by_separator(
        text, separator='\n\n', max_length=settings.MAX_MSG_LEN
    )
    while len(chunks) > 1:
        count = len(chunks)
        prefix_length = _text_length(f'Продолжение ({count}/{count}):\n\n')
        shorter_chunks = split_message_by_separator(
            text,
            separator='\n\n',
            max_length=settings.MAX_MSG_LEN - prefix_length,
        )
        chunks = shorter_chunks
        if len(chunks) == count:
            break

    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.answer(chunk, **kwargs)
        else:
            await message.answer(
                f'<i>Продолжение ({i + 1}/{len(chunks)}):</i>\n\n{chunk}',
                **kwargs,
            )
            await asyncio.sleep(0.5)  # Небольшая задержка между сообщениями
