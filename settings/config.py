from datetime import datetime

import pymorphy2
import pytz

# Московское время для
# предотвращения ошибок с датой при размещении на сервере с другой тайм-зоной.
moscow_tz = pytz.timezone('Europe/Moscow')

current_time = datetime.now(moscow_tz)
next_month = current_time.month + 1
# Автоматическое склонение слова в зависимости от числа.
morph = pymorphy2.MorphAnalyzer()


def pluralize(word, count):
    parsed_word = morph.parse(word)[0]
    return parsed_word.make_agree_with_number(count).word


COM_ID = None  # ID компании, которую вы хотите отслеживать.
TELEGRA_BOT_TOKEN = 'YOUR_TOKEN'

WAIT_MSG = 'Собираю информацию, пожалуйста подождите...'
PERSONS = {
    'EXAMPLE_NAME': 000000000,
}
# Словарь с ключами - id пользователей, значениями - множествами спектаклей.
# Спектакли должны быть указаны в точности так, как они выдаются в общем
# списке.
P_SHOWS = {
    PERSONS.get('EXAMPLE'): {
        'НАЗВАНИЕ СПЕКТАКЛЯ',
    },
}
