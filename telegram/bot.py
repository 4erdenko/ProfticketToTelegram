import asyncio
import logging as logger
import parser.web_parser as pt

import aiogram
from aiogram import types
from aiogram.dispatcher.filters import Text

from settings.config import (P_SHOWS, TELEGRA_BOT_TOKEN, WAIT_MSG,
                             get_next_month)
from telegram.keyboard import (keyboard, keyboard_private,
                               keyboard_private_months)

bot = aiogram.Bot(token=TELEGRA_BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = aiogram.Dispatcher(bot)


@dp.message_handler(commands=['start'])
async def process_start_command(message: aiogram.types.Message):
    """
    Handles the /start command.

    Returns:
        Sends the user to choose_person to check their status.
    """
    await choose_person(message)
    logger.info(
        f'({message.from_user.full_name}) '
        f'(@{message.from_user.username}) '
        f'ID({message.from_user.id}) started bot'
    )


async def choose_person(message: aiogram.types.Message):
    """
    Determines if the user is in the P_SHOWS list and provides
    a personalized or regular keyboard accordingly.

    Returns:
        None: Sends a message with either a personalized or regular keyboard.
    """
    if message.from_user.id in P_SHOWS:
        await message.answer(
            f'О, да это же {message.from_user.full_name}!',
            reply_markup=keyboard_private,
        )
    else:
        await message.answer(
            f'Привет {message.from_user.first_name}\\.\n' f'Глянем Афишу?\n',
            reply_markup=keyboard,
            parse_mode='MarkdownV2',
        )


async def choose_personal_shows(message: aiogram.types.Message, month=None):
    """
    Sends a message with a personalized selection of
    performances for the specified month.

    Returns:
        str: Sends a message with the personalized performance selection.
    """
    if message.from_user.id in P_SHOWS:
        return pt.get_special_info(
            month=month, telegram_id=message.from_user.id
        )


@dp.message_handler(Text(equals=['Этот месяц']))
async def this_month_command(message: aiogram.types.Message):
    """
    Handles the 'Этот месяц' command.

    Returns:
        Sends a message with this month's performance data.
    """
    try:
        msg = await message.answer(WAIT_MSG)
        await bot.send_chat_action(
            message.chat.id,
            'typing',
        )
        await send_chunks_edit(message.chat.id, msg, pt.get_special_info())

        logger.info(
            f'{message.from_user.full_name} '
            f'(@{message.from_user.username}) '
            f'ID({message.from_user.id}) got shows for this month'
        )
    except Exception as e:
        await message.answer(
            'Произошла ошибка, попробуйте ещё раз через минутку.'
        )
        logger.error(e)


@dp.message_handler(Text(equals=['Следующий месяц']))
async def next_month_command(message: aiogram.types.Message):
    """
    Handles the 'Следующий месяц' command.

    Returns:
        Sends a message with performance data for the next month.
    """
    next_month = get_next_month()
    try:
        msg = await message.answer(WAIT_MSG)
        await bot.send_chat_action(
            message.chat.id,
            'typing',
        )
        await send_chunks_edit(
            message.chat.id, msg, pt.get_special_info(month=next_month)
        )

        logger.info(
            f'{message.from_user.full_name} '
            f'(@{message.from_user.username}) '
            f'ID({message.from_user.id}) got shows for '
            f'0{next_month} month'
        )
    except Exception as e:
        await message.answer(
            'Произошла ошибка, попробуйте ещё раз через минутку.'
        )
        logger.error(e)


@dp.message_handler(Text(equals=['Мои спектакли']))
async def my_shows_command(message: aiogram.types.Message):
    """
    Handles the 'Мои спектакли' command.

    Returns:
        Creates buttons to select the month.
    """
    await message.answer(
        'Выберите месяц', reply_markup=keyboard_private_months
    )


@dp.message_handler(Text(equals=['Этот']))
async def this_month_private_command(message: aiogram.types.Message):
    """
    Handles the 'Этот' command in the personal section.

    Returns:
        Sends a message with personal data about this month's performances.
    """
    try:
        msg = await message.answer(WAIT_MSG)
        await bot.send_chat_action(
            message.chat.id,
            'typing',
        )
        await msg.edit_text(await choose_personal_shows(message))
        logger.info(
            f'{message.from_user.full_name} '
            f'(@{message.from_user.username}) '
            f'ID({message.from_user.id}) got personal info for this month'
        )
    except Exception as e:
        await message.answer(
            'Произошла ошибка, попробуйте ещё раз через минутку.'
        )
        logger.error(e)


@dp.message_handler(Text(equals=['Следующий']))
async def next_month_private_command(message: aiogram.types.Message):
    """
    Handles the 'Следующий' command in the personal section.

    Returns:
        Sends a message with personal data about performances
        for the next month.
    """
    next_month = get_next_month()
    try:
        msg = await message.answer(WAIT_MSG)
        await bot.send_chat_action(
            message.chat.id,
            'typing',
        )
        await msg.edit_text(
            await choose_personal_shows(message, month=next_month)
        )
        logger.info(
            f'{message.from_user.full_name} '
            f'(@{message.from_user.username}) '
            f'ID({message.from_user.id}) got personal info for '
            f'0{next_month} month'
        )
    except Exception as e:
        await message.answer(
            'Произошла ошибка, попробуйте ещё раз через минутку.'
        )
        logger.error(e)


@dp.message_handler(Text(equals=['↩️']))
async def back_command(message: aiogram.types.Message):
    """
    Handles the '↩️' command.

    Returns:
        Returns the user to the main menu.
    """
    await message.delete()
    await message.answer('Главное меню', reply_markup=keyboard_private)


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
    chunks = pt.split_message_by_separator(text)

    if chunks:
        await message.edit_text(chunks.pop(0), **kwargs)
        for chunk in chunks:
            await message.answer(chunk, **kwargs)
            await asyncio.sleep(1)
