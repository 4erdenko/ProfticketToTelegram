from aiogram import F, Router
from aiogram.filters import MagicData
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from telegram.keyboards.main_keyboard import main_keyboard
from telegram.lexicon.lexicon_ru import LEXICON_RU

maintenance_router = Router()
maintenance_router.message.filter(MagicData(F.maintenance_mode.is_(True)))
maintenance_router.callback_query.filter(
    MagicData(F.maintenance_mode.is_(True))
)


@maintenance_router.message()
async def any_message(message: Message, session: AsyncSession):
    """
    This method sends a maintenance message to the user.

    :param message: The message object received from the user.
    :type message: :class:`telegram.Message`
    :param session: The async session object used for database operations.
    :type session: :class:`sqlalchemy.ext.asyncio.AsyncSession`
    :return: None
    """
    await message.answer(
        LEXICON_RU['MAINTENANCE'],
        reply_markup=await main_keyboard(message, session),
    )
