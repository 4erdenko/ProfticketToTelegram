import asyncio
import logging
import os
import signal
import sys
from typing import Optional

import coloredlogs
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from config import settings
from telegram.handlers import (maintenance_handler, personal_handlers,
                               throttling_handler, user_handlers,
                               analytics_handlers)
from telegram.keyboards.native_menu import set_native_menu
from telegram.lexicon.lexicon_ru import LEXICON_LOGS

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configures logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    coloredlogs.install(
        level='INFO',
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        isatty=True,
        stream=sys.stdout,
    )


def handle_signals() -> None:
    """Sets up signal handlers for graceful shutdown."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda signum, frame: None)


async def setup_dispatcher() -> Dispatcher:
    """
    Configures and returns the dispatcher with all routers.

    Returns:
        Dispatcher: Configured dispatcher instance
    """
    dp = Dispatcher(
        storage=MemoryStorage(), maintenance_mode=settings.MAINTENANCE
    )
    dp.include_router(maintenance_handler.maintenance_router)
    dp.include_router(throttling_handler.throttling_router)
    dp.include_router(user_handlers.user_router)
    dp.include_router(personal_handlers.personal_user_router)
    dp.include_router(analytics_handlers.analytics_router)
    return dp


async def on_startup(bot: Bot, admin_id: int) -> None:
    """
    Performs bot startup actions.

    Args:
        bot: Bot instance
        admin_id: Admin user ID for notifications
    """
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await set_native_menu(bot)
        await bot.send_message(
            admin_id, LEXICON_LOGS['BOT_STARTED'].format(admin_id)
        )
        logger.info(LEXICON_LOGS['BOT_STARTED'].format(admin_id))
    except Exception as e:
        logger.error(LEXICON_LOGS['ERROR_ON_STARTUP'].format(str(e)))
        raise


async def on_shutdown(
    bot: Bot, admin_id: int, update_task: Optional[asyncio.Task] = None
) -> None:
    """
    Performs bot shutdown actions.

    Args:
        bot: Bot instance
        admin_id: Admin user ID for notifications
        update_task: Optional background task to cancel
    """
    try:
        await bot.send_message(admin_id, LEXICON_LOGS['BOT_STOPPED'])
        if update_task and not update_task.done():
            update_task.cancel()
            try:
                await update_task
            except asyncio.CancelledError:
                pass
        await bot.session.close()
        logger.info(LEXICON_LOGS['BOT_SHUTDOWN_COMPLETE'])
    except Exception as e:
        logger.error(LEXICON_LOGS['ERROR_ON_SHUTDOWN'].format(str(e)))


def get_token() -> str:
    """
    Returns the appropriate bot token based on environment.

    Returns:
        str: Bot token
    """
    load_dotenv()
    return (
        settings.TEST_BOT_TOKEN
        if os.getenv('IN_DOCKER') != 'true'
        else settings.BOT_TOKEN
    )
