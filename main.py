import logging
import sys

from aiogram import executor
from aiogram.utils.exceptions import TelegramAPIError, NetworkError

from telegram.bot import dp

if __name__ == '__main__':
    # Set up logging with a basic configuration
    logging.basicConfig(
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S',
        format='%(asctime)s [%(levelname)s]: %(message)s',
        handlers=[
            logging.StreamHandler(stream=sys.stdout),
        ],
    )

    # Try to start the bot's polling process
    try:
        executor.start_polling(dp, skip_updates=True)
    except NetworkError as e:
        # Log network error
        logging.error(f"Ошибка сети: {e}")
    except TelegramAPIError as e:
        # Log Telegram API error
        logging.error(f"Ошибка Telegram API: {e}")
        if 'Bad Gateway' in str(e):
            logging.error('Ошибка Bad Gateway')
