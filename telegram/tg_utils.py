import asyncio
import string
from datetime import datetime
from html import escape

import pytz
from aiogram.types import Message
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
        seats_text = '<code>SOLD OUT</code>'
    else:
        seats_value = (
            f'<a href="{buy_link}">{seats}</a>' if buy_link else str(seats)
        )
        seats_text = f'Билетов: {seats_value}'

    seats_diff = ''
    if (
        seats is not None
        and previous_seats is not None
        and seats != previous_seats
    ):
        diff = seats - previous_seats
        seats_diff = f' ({diff} 🔻)' if diff < 0 else f' (+{diff} 🔺)'

    return (
        f'📅<strong> {date}</strong>\n'
        f'💎 {show_name}\n'
        f'🎫 {seats_text}{seats_diff}\n'
        '------------------------\n'
    )


def split_message_by_separator(
    message: str,
    separator: str = '\n------------------------\n',
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
    chunks = split_message_by_separator(text)

    if chunks:
        await message.edit_text(chunks.pop(0), **kwargs)
        for chunk in chunks:
            await message.answer(chunk, **kwargs)
            await asyncio.sleep(1)


async def check_text(message: Message) -> str | None:
    """
    Check if message text is valid name format.

    Args:
        message: Message to check

    Returns:
        str: Cleaned text if valid, None otherwise
    """
    text = message.text
    if isinstance(text, str):
        text = text.lower().strip()
        text = text.translate(str.maketrans('', '', string.punctuation))
        if len(text.split(' ')) == 2:
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
    chunks = split_message_by_separator(
        text, separator='\n\n', max_length=settings.MAX_MSG_LEN
    )

    for i, chunk in enumerate(chunks):
        if i == 0:
            await message.answer(chunk, **kwargs)
        else:
            await message.answer(
                f'<i>Продолжение ({i + 1}/{len(chunks)}):</i>\n\n{chunk}',
                **kwargs,
            )
            await asyncio.sleep(0.5)  # Небольшая задержка между сообщениями
