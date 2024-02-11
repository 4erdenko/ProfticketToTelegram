import logging

from aiogram import Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent

from telegram.lexicon.lexicon_ru import LEXICON_RU
from telegram.middlewares.throttling import ThrottledError

throttling_router = Router(name=__name__)
logger = logging.getLogger(__name__)


@throttling_router.errors(ExceptionTypeFilter(ThrottledError))
async def error_throttled(event: ErrorEvent) -> None:
    """

    :param event: The ErrorEvent object containing information about the error.
    :return: None

    """
    update = event.update

    if update.message:
        await update.message.answer(text=LEXICON_RU['THROTTLING'])
