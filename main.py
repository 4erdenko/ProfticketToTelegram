import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from config import settings
from services.ermolova import ErmolovaInfo
from services.profticket.profticket_api import ProfticketsInfo
from services.profticket.profticket_snapshoter import ShowUpdateService
from telegram.db.user_operations import setup_database
from telegram.lexicon.lexicon_ru import LEXICON_LOGS
from telegram.middlewares.banhammer import BanMiddleware
from telegram.middlewares.db import DbSessionMiddleware
from telegram.middlewares.logging_to_db import UserLoggingMiddleware
from telegram.middlewares.profticket import ProfticketSessionMiddleware
from telegram.middlewares.throttling import ThrottlingMiddleware
from telegram.utils.startup import (
    get_token,
    on_shutdown,
    on_startup,
    setup_dispatcher,
    setup_logging,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    """Main application entry point."""
    setup_logging()

    bot = Bot(
        token=get_token(), default=DefaultBotProperties(parse_mode='HTML')
    )
    dp = await setup_dispatcher()

    session_pool, context_data = await setup_database()

    profticket = (
        ErmolovaInfo(
            settings.MOSBILET_PROXY_URL,
            proxy_ca_file=settings.MOSBILET_PROXY_CA_FILE,
        )
        if settings.SCHEDULE_SOURCE == 'ermolova'
        else ProfticketsInfo(settings.COM_ID)
    )
    logger.info(LEXICON_LOGS['PROFTICKET_INITIALIZED'])

    dp.update.middleware(DbSessionMiddleware(session_pool=session_pool))
    dp.update.middleware(UserLoggingMiddleware())
    dp.update.middleware(BanMiddleware())
    dp.update.middleware(ThrottlingMiddleware())
    dp.update.middleware(ProfticketSessionMiddleware(profticket))

    show_update_service = ShowUpdateService(
        session_pool,
        profticket,
        bot,
    )

    update_task = None
    try:
        update_task = asyncio.create_task(show_update_service.update_loop())
        await on_startup(bot, settings.ADMIN_ID)
        await dp.start_polling(bot)
    except KeyboardInterrupt, SystemExit:
        logger.info(LEXICON_LOGS['BOT_STOPPED_BY_USER'])
    except Exception as e:
        logger.exception(LEXICON_LOGS['BOT_ERROR'].format(str(e)))
        raise
    finally:
        try:
            await on_shutdown(bot, settings.ADMIN_ID, update_task)
        finally:
            try:
                if isinstance(profticket, ErmolovaInfo):
                    await profticket.aclose()
                else:
                    await profticket.client.aclose()
            finally:
                await context_data['engine'].dispose()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info(LEXICON_LOGS['BOT_STOPPED_BY_KEYBOARD'])
    except Exception as e:
        logger.exception(LEXICON_LOGS['BOT_ERROR'].format(str(e)))
