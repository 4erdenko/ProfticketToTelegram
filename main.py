import asyncio
import logging
import os
import sys

import coloredlogs
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import settings
from services.profticket.profticket_api import ProfticketsInfo
from services.profticket.profticket_snapshoter import ShowUpdateService
from telegram.handlers import (maintenance_handler, personal_handlers,
                               throttling_handler, user_handlers)
from telegram.keyboards.native_menu import set_native_menu
from telegram.lexicon.lexicon_ru import LEXICON_LOGS
from telegram.middlewares.banhammer import BanMiddleware
from telegram.middlewares.db import DbSessionMiddleware
from telegram.middlewares.logging_to_db import UserLoggingMiddleware
from telegram.middlewares.profticket import ProfticketSessionMiddleware
from telegram.middlewares.throttling import ThrottlingMiddleware


async def on_startup(bot: Bot):
    try:
        await bot.send_message(
            settings.ADMIN_ID,
            LEXICON_LOGS['BOT_STARTED'].format(settings.ADMIN_ID),
        )
    except Exception as e:
        logging.exception(
            LEXICON_LOGS['LOG_MSG_ERROR_WHEN_START_MSG_TO_ADMIN'].format(e)
        )


def get_env():
    load_dotenv()
    return os.getenv('IN_DOCKER', 'true')


def get_token():
    if get_env() != 'true':
        return settings.TEST_BOT_TOKEN
    else:
        return settings.BOT_TOKEN


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        stream=sys.stdout,
    )
    coloredlogs.install(
        level='INFO',
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        isatty=True,
        stream=sys.stdout,
    )
    logger = logging.getLogger(__name__)

    engine = create_async_engine(url=settings.DB_URL, echo=False)
    logger.info(LEXICON_LOGS['ENGINE_CREATED'])

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    logger.info(LEXICON_LOGS['SESSION_MAKER_INITIALIZED'])

    bot = Bot(token=get_token(), parse_mode='HTML')
    dp = Dispatcher(maintenance_mode=settings.MAINTENANCE)

    profticket = ProfticketsInfo(settings.COM_ID)
    logger.info(LEXICON_LOGS['PROFTICKET_INITIALIZED'])

    dp.include_router(maintenance_handler.maintenance_router)
    dp.include_router(throttling_handler.throttling_router)
    dp.include_router(user_handlers.user_router)
    dp.include_router(personal_handlers.personal_user_router)

    dp.update.outer_middleware(DbSessionMiddleware(session_pool=sessionmaker))
    dp.update.outer_middleware(ThrottlingMiddleware())
    dp.update.outer_middleware(BanMiddleware())
    dp.update.middleware(UserLoggingMiddleware())
    dp.update.middleware(ProfticketSessionMiddleware(profticket))

    show_update_service = ShowUpdateService(sessionmaker, profticket, bot)
    asyncio.create_task(show_update_service.update_loop())

    logger.info(LEXICON_LOGS['BOT_STARTED'].format(settings.ADMIN_ID))
    await bot.delete_webhook(drop_pending_updates=True)
    dp.startup.register(on_startup)
    await set_native_menu(bot)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
