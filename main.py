# import logging
# import sys
#
# from aiogram import executor
# from aiogram.utils.exceptions import NetworkError, TelegramAPIError
#
# from telegram.bot import dp
#
# if __name__ == '__main__':
#     # Set up logging with a basic configuration
#     logging.basicConfig(
#         level=logging.INFO,
#         datefmt='%Y-%m-%d %H:%M:%S',
#         format='%(asctime)s [%(levelname)s]: %(message)s',
#         handlers=[
#             logging.StreamHandler(stream=sys.stdout),
#         ],
#     )
#
#     # Try to start the bot's polling process
#     try:
#         executor.start_polling(dp, skip_updates=True)
#     except NetworkError as e:
#         # Log network error
#         logging.error(f"Ошибка сети: {e}")
#     except TelegramAPIError as e:
#         # Log Telegram API error
#         logging.error(f"Ошибка Telegram API: {e}")
#         if 'Bad Gateway' in str(e):
#             logging.error('Ошибка Bad Gateway')
import asyncio
import logging
import sys

import coloredlogs
from aiogram import Bot, Dispatcher
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


from config import settings
from telegram.handlers import user_handlers
from telegram.lexicon.lexicon_ru import LEXICON_LOGS
from telegram.middlewares.db import DbSessionMiddleware
from telegram.middlewares.logging_to_db import UserLoggingMiddleware
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

    engine = create_async_engine(url=settings.DB_URL, echo=True)
    logger.info(LEXICON_LOGS['ENGINE_CREATED'])

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    logger.info(LEXICON_LOGS['SESSION_MAKER_INITIALIZED'])

    bot = Bot(token=settings.TEST_BOT_TOKEN, parse_mode='HTML')
    dp = Dispatcher(maintenance_mode=settings.MAINTENANCE)



    dp.include_router(user_handlers.user_router)


    dp.update.outer_middleware(DbSessionMiddleware(session_pool=sessionmaker))
    dp.update.outer_middleware(ThrottlingMiddleware())
    dp.update.middleware(UserLoggingMiddleware())


    logger.info(LEXICON_LOGS['BOT_STARTED'].format(settings.ADMIN_ID))
    await bot.delete_webhook(drop_pending_updates=True)
    dp.startup.register(on_startup)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
