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