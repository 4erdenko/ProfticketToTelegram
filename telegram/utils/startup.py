import asyncio
import contextlib
import logging
import sys

import coloredlogs
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from telegram.handlers import (
    admin_handlers,
    analytics_handlers,
    maintenance_handler,
    personal_handlers,
    throttling_handler,
    user_handlers,
)
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
    dp.include_router(admin_handlers.admin_router)
    return dp


async def on_startup(bot: Bot, admin_id: int) -> None:
    """
    Performs bot startup actions.

    Args:
        bot: Bot instance
        admin_id: Admin user ID for notifications
    """
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await set_native_menu(bot)
    except Exception as e:
        logger.warning('Unable to configure the bot menu: %s', e)
    try:
        await bot.send_message(
            admin_id, LEXICON_LOGS['BOT_STARTED'].format(admin_id)
        )
    except Exception as e:
        logger.error(LEXICON_LOGS['ERROR_ON_STARTUP'].format(str(e)))
    logger.info(LEXICON_LOGS['BOT_STARTED'].format(admin_id))


async def on_shutdown(
    bot: Bot, admin_id: int, update_task: asyncio.Task | None = None
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
    except Exception as e:
        logger.error(LEXICON_LOGS['ERROR_ON_SHUTDOWN'].format(str(e)))
    finally:
        try:
            if update_task is not None:
                if not update_task.done():
                    update_task.cancel()
                try:
                    with contextlib.suppress(asyncio.CancelledError):
                        await update_task
                except Exception as e:
                    logger.error('Background update task failed: %s', e)
        finally:
            await bot.session.close()
            logger.info(LEXICON_LOGS['BOT_SHUTDOWN_COMPLETE'])


def get_token() -> str:
    """
    Returns the appropriate bot token based on environment.

    Returns:
        str: Bot token
    """
    return (
        settings.BOT_TOKEN
        if str(settings.IN_DOCKER).strip().lower()
        in {'1', 'true', 'yes', 'on'}
        else settings.TEST_BOT_TOKEN
    )
