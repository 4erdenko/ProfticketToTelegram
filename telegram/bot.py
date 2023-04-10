import logging as logger

import aiogram
from aiogram import types
from aiogram.dispatcher.filters import Text

import parser.web_parser as pt
from settings.config import (
    TELEGRA_BOT_TOKEN,
    P_SHOWS,
    next_month,
    WAIT_MSG,
)
from telegram.keyboard import (
    keyboard,
    keyboard_private,
    keyboard_private_months,
)

bot = aiogram.Bot(token=TELEGRA_BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = aiogram.Dispatcher(bot)


@dp.message_handler(commands=['start'])
async def process_start_command(message: aiogram.types.Message):
    """
    Реакция на команду /start

    Returns: отправляет пользователя на проверку в choose_person

    """
    await choose_person(message)
    logger.info(
        f'({message.from_user.full_name}) '
        f'(@{message.from_user.username}) '
        f'ID({message.from_user.id}) started bot'
    )


async def choose_person(message: aiogram.types.Message):
    """
    Returns: Если пользователь в списке P_SHOWS, то даёт ему клавиатуру с
    персональными данными, иначе - обычную клавиатуру.

    """
    if message.from_user.id in P_SHOWS:
        await message.answer(
            f'О, да это же {message.from_user.full_name}!',
            reply_markup=keyboard_private,
        )
    else:
        await message.answer(
            f'Привет {message.from_user.first_name}\.\n' f'Глянем Афишу?\n',
            reply_markup=keyboard,
            parse_mode='MarkdownV2',
        )


async def choose_personal_shows(message: aiogram.types.Message, month=None):
    """
    Returns: Отправка сообщения с персональной выборкой спектаклей.
    """
    if message.from_user.id in P_SHOWS:
        return pt.get_special_info(
            month=month, telegram_id=message.from_user.id
        )


@dp.message_handler(Text(equals=['Этот месяц']))
async def this_month_command(message: aiogram.types.Message):
    """
    Реакция на команду "Этот месяц"

    Returns: Отправка сообщения с данными о спектаклях на этот месяц.

    """
    try:
        msg = await message.answer(WAIT_MSG)
        await bot.send_chat_action(
            message.chat.id,
            'typing',
        )
        await msg.edit_text(pt.get_special_info())
        logger.info(
            f'{message.from_user.full_name} '
            f'(@{message.from_user.username}) '
            f'ID({message.from_user.id}) got shows for this month'
        )
    except Exception as e:
        await message.answer(
            f'Произошла ошибка, попробуйте ещё раз через ' f'минутку.'
        )
        logger.error(e)


@dp.message_handler(Text(equals=['Следующий месяц']))
async def next_month_command(message: aiogram.types.Message):
    """
    Реакция на команду "Следующий месяц"

    Returns: Отправка сообщения с данными о спектаклях на следующий месяц.

    """
    try:
        msg = await message.answer(WAIT_MSG)
        await bot.send_chat_action(
            message.chat.id,
            'typing',
        )
        await msg.edit_text(pt.get_special_info(month=next_month))
        logger.info(
            f'{message.from_user.full_name} '
            f'(@{message.from_user.username}) '
            f'ID({message.from_user.id}) got shows for '
            f'0{next_month} month'
        )
    except Exception as e:
        await message.answer(
            f'Произошла ошибка, попробуйте ещё раз через ' f'минутку.'
        )
        logger.error(e)


@dp.message_handler(Text(equals=['Мои спектакли']))
async def my_shows_command(message: aiogram.types.Message):
    """
    Реакция на команду "Мои спектакли"

    Returns: Создаёт кнопки для выбора месяца.

    """
    await message.answer(
        'Выберите месяц', reply_markup=keyboard_private_months
    )


@dp.message_handler(Text(equals=['Этот']))
async def this_month_private_command(message: aiogram.types.Message):
    """
    Реакция на команду "Этот" в персональном разделе

    Returns: Отправка сообщения с персональными данными о спектаклях на этот
        месяц.

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
            f'Произошла ошибка, попробуйте ещё раз через ' f'минутку.'
        )
        logger.error(e)


@dp.message_handler(Text(equals=['Следующий']))
async def next_month_private_command(message: aiogram.types.Message):
    """
    Реакция на команду "Следующий" в персональном разделе

    Returns: Отправка сообщения с персональными данными о спектаклях на
        следующий месяц.

    """
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
            f'Произошла ошибка, попробуйте ещё раз через ' f'минутку.'
        )
        logger.error(e)


@dp.message_handler(Text(equals=['↩️']))
async def back_command(message: aiogram.types.Message):
    """
    Реакция на команду "↩️"

    Returns: Возвращает пользователя в главное меню.

    """
    await message.delete()
    await message.answer('Главное меню', reply_markup=keyboard_private)
