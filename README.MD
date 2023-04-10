# Ticket Sale Service Parser

This Telegram bot is designed to collect and provide information about theater performances. The bot has different
functionalities depending on whether the user is registered (has a record in the `P_SHOWS` dictionary) or not.

## Main Functionality

### For unregistered users:

1. `/start` - command that greets the user and offers to view the event schedule.
2. `Этот месяц` - displays a list of performances for the current month.
3. `Следующий месяц` - displays a list of performances for the next month.

### For registered users:

1. `/start` - command that greets the user and opens the personal menu.
2. `Этот месяц` - displays a list of performances for the current month.
3. `Следующий месяц` - displays a list of performances for the next month.
4. `Мои спектакли` - opens a menu to choose a month and displays personalized information about the performances for the
   selected month.
5. `↩️` - returns the user to the main menu.

## Installation and Configuration

1. Install the necessary dependencies from the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

2. Replace `YOUR_TOKEN` in the `config.py` file with your Telegram bot token.

3. Fill in the `COM_ID`, `PERSONS`, and `P_SHOWS` variables in the `config.py` file with the relevant data about the
   company, users, and performances.
   Additionally, in the json_library folder, there is a ready-to-use script for parsing all the organizations connected
   to the ticket service. When running the `profticket_place_parser.py` script, it will create a `profticket.json` file
   in the json_library folder with theater data. Choose the required ID and specify it in `COM_ID`.

4. Run the bot by executing the following command:

```bash
python main.py
```

Now your Telegram bot is ready for use.

## Logging

The bot uses Python's built-in logging module to log important events and errors. The logging configuration is set up in the `main.py` file. By default, the log messages will be printed to the standard output (console) with a logging level of `INFO`.

To adjust the logging level or add other logging handlers, you can modify the `logging.basicConfig()` call in `main.py`. For example, you can add a file handler to store log messages in a file:

```python
import logging
import sys

from aiogram import executor
from aiogram.utils.exceptions import TelegramAPIError, NetworkError

from telegram.bot import dp

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S',
        format='%(asctime)s [%(levelname)s]: %(message)s',
        handlers=[
            logging.StreamHandler(stream=sys.stdout),
            logging.FileHandler(filename="logfile.log", mode="a"),  # Add this line
        ],
    )
    try:
        executor.start_polling(dp, skip_updates=True)
    except NetworkError as e:
        logging.error(f"Network Error: {e}")
    except TelegramAPIError as e:
        logging.error(f"Telegram API Error: {e}")
        if 'Bad Gateway' in str(e):
            logging.error('Bad Gateway Error')
```

This will create a file named `logfile.log` in the same directory as your `main.py` file, and it will append log messages to the file. You can customize the filename