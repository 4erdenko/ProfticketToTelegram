import asyncio
import string
from datetime import datetime

import pytz
from aiogram.types import Message
from dateutil.relativedelta import relativedelta

from config import settings


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


def get_result_message(seats, previous_seats, show_name, date, buy_link):
    """
    Function to create a message with information about a performance.

    Args:
        seats (int): Number of available seats.
        previous_seats (int): Number of seats from previous update
        show_name (str): Name of the performance.
        date (str): Date of the performance.
        buy_link (str): Ticket purchase link.

    """
    if seats == 0:
        seats_text = '<code>SOLD OUT</code>'
    else:
        seats_text = f'Билетов: <a href="{buy_link}">{seats}</a>'

    # Добавляем информацию об изменении количества билетов
    seats_diff = ''
    if previous_seats is not None and seats != previous_seats:
        diff = seats - previous_seats
        if diff < 0:
            seats_diff = f' ({diff} 🔻)'
        else:
            seats_diff = f' (+{diff} 🔺)'

    return (
        f'📅<strong> {date}</strong>\n'
        f'💎 {show_name}\n'
        f'🎫 {seats_text}{seats_diff}\n'
        '------------------------\n'
    )


def split_message_by_separator(
        message,
        separator='\n------------------------\n',
        max_length=settings.MAX_MSG_LEN,
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


async def send_chunks_edit(chat_id, message, text, **kwargs):
    """
    Sends a message in chunks. The first chunk is sent using msg.edit_text,
    and the subsequent chunks are sent using message.answer.

    Args:
        chat_id (int): The ID of the chat where the message will be sent.
        message (aiogram.types.Message): The message object.
        text (str): The message text to be sent.
        **kwargs: Additional arguments to pass to the message
            sending functions.

    Returns:
        None
    """
    chunks = split_message_by_separator(text)

    if chunks:
        await message.edit_text(chunks.pop(0), **kwargs)
        for chunk in chunks:
            await message.answer(chunk, **kwargs)
            await asyncio.sleep(1)


async def check_text(message: Message):
    text = message.text
    if isinstance(text, str):
        text = text.lower().strip()
        text = text.translate(str.maketrans('', '', string.punctuation))
        if len(text.split(' ')) == 2:
            return text
    return None
