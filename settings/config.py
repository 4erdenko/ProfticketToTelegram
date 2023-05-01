from datetime import datetime

import pymorphy2
import pytz


def get_current_time_and_next_month():
    """
    Get the current time in Moscow timezone and calculate the next month.

    Returns:
        tuple: A tuple containing the current Moscow time and the next month.
    """
    moscow_tz = pytz.timezone('Europe/Moscow')
    current_time = datetime.now(moscow_tz)
    next_month = current_time.month + 1 if current_time.month < 12 else 1
    return current_time, next_month


# Get the current Moscow time and calculate the next month
current_time, next_month = get_current_time_and_next_month()

# Initialize the pymorphy2 MorphAnalyzer for word declension
morph = pymorphy2.MorphAnalyzer()


def pluralize(word, count):
    """
    Function to return the correct plural form of a word
    depending on the count.

    Args:
        word (str): The word to pluralize.
        count (int): The count to determine the correct plural form.

    Returns:
        str: The pluralized word.
    """
    parsed_word = morph.parse(word)[0]
    return parsed_word.make_agree_with_number(count).word


# The company ID you want to track.
COM_ID = None

# Your Telegram bot token'
TELEGRA_BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'

# The waiting message to display while gathering information
WAIT_MSG = 'Собираю информацию, пожалуйста подождите...'

# The maximum length of a message
MAX_MSG_LEN = 4096

# A dictionary of user names and their corresponding Telegram user IDs
PERSONS = {
    'EXAMPLE_NAME': 000000000,
}

# A dictionary with keys as user IDs, and values as sets of performances.
# Performances must be specified exactly as they are
# displayed in the general list.
P_SHOWS = {
    PERSONS.get('EXAMPLE_NAME'): {
        'НАЗВАНИЕ СПЕКТАКЛЯ',
    },
}
