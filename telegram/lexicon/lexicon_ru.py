from config import settings

LEXICON_RU: dict = {
    'WAIT_MSG': 'Пожалуйста, подождите, идёт сбор данных.',
    'NONE_SHOWS_THIS_MONTH': 'Спектаклей в этом месяце нет.',
    'THROTTLING': 'Воу-воу! Слишком много запросов от тебя, подыши.\n\n'
                '<b>Техника дыхания (20 секунд):</b>\n'
                '1. Сядьте в удобное положение.\n'
                '2. Закройте глаза и сосредоточьтесь на дыхании.\n'
                '3. Глубоко вдохните через нос в течение 4 секунд.\n'
                '4. Задержите дыхание на 4 секунды.\n'
                '5. Медленно выдохните через рот в течение 4 секунд.\n'
                '6. Подождите 4 секунды перед следующим вдохом.\n'
                '7. Повторяйте эту последовательность в течение 20 секунд.\n'
                '\n',
    'MAINTENANCE': 'Бот на техническом обслуживании.',
    'HELP_CONTACT': f'Если нужна помощь, напиши сюда: '
                    f'{settings.ADMIN_USERNAME}'

}

LEXICON_COMMANDS_RU: dict = {
    '/start': 'Привет, посмотрим расписание ?'
}

LEXICON_LOGS: dict = {
    'BOT_STARTED': 'Bot has been launched and is ready to work. Administrator: {}',
    'ENGINE_CREATED': 'The database engine was created successfully',
    'SESSION_MAKER_INITIALIZED': 'Session maker has been initialized',
    'PROFTICKET_INITIALIZED': 'Successfully initialize profticket client',
    'LOG_MSG_ERROR_WHEN_START_MSG_TO_ADMIN': 'Error: {}',
    'LOG_MSH_HELP_COMMAND': 'UserID {} using /help command.',
}

LEXICON_NATIVE_COMMANDS_RU: dict[str, str] = {
    '/start': '🔁 Перезагрузка бота',
    '/help': '🆘 Нужна помощь!'
}
