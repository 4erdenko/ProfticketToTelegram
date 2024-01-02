import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.keyboards.main_keyboard import main_keyboard

user_router = Router(name=__name__)
logger = logging.getLogger(__name__)


@user_router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    await message.answer(
        'Hi!', reply_markup=await main_keyboard(message, session)
    )



@user_router.message(F.text == 'Этот месяц')
async def this_month_command(message: Message):
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
#
#
# @user_router.message(F.text == 'Следующий месяц')
# async def next_month_command(message: Message):
#     """
#     Handles the 'Следующий месяц' command.
#
#     Returns:
#         Sends a message with performance data for the next month.
#     """
#     next_month = get_next_month()
#     try:
#         msg = await message.answer(WAIT_MSG)
#         await bot.send_chat_action(
#             message.chat.id,
#             'typing',
#         )
#         await send_chunks_edit(
#             message.chat.id, msg, pt.get_special_info(month=next_month)
#         )
#
#         logger.info(
#             f'{message.from_user.full_name} '
#             f'(@{message.from_user.username}) '
#             f'ID({message.from_user.id}) got shows for '
#             f'0{next_month} month'
#         )
#     except Exception as e:
#         await message.answer(
#             'Произошла ошибка, попробуйте ещё раз через минутку.'
#         )
#         logger.error(e)
#
