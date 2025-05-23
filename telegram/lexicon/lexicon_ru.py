from config import settings

LEXICON_MONTHS_RU: dict[str, str] = {
    'January': 'Январь',
    'February': 'Февраль',
    'March': 'Март',
    'April': 'Апрель',
    'May': 'Май',
    'June': 'Июнь',
    'July': 'Июль',
    'August': 'Август',
    'September': 'Сентябрь',
    'October': 'Октябрь',
    'November': 'Ноябрь',
    'December': 'Декабрь',
}

LEXICON_RU: dict[str, str] = {
    # Основные сообщения
    'MAIN_MENU': 'Главное меню',
    'CHOOSE_MONTH': 'Выберите месяц',
    'ERROR_MSG': 'Произошла ошибка, попробуйте ещё раз через минутку.',
    'WAIT_MSG': 'Пожалуйста, подождите, идёт сбор данных.',
    'NONE_SHOWS_THIS_MONTH': 'Спектаклей в этом месяце нет.',
    'HELP_CONTACT': f'Если нужна помощь, напиши сюда: {settings.ADMIN_USERNAME}',
    # Сообщения для работы с актёрами
    'SET_NAME': (
        'Введите: <b>Имя Фамилия</b>\n'
        'Например: <b>Олег Меньшиков</b>\n\n'
        'Без каких либо других знаков и точек, именно в таком порядке.'
    ),
    'WRONG_FIO': (
        'Некорректное имя!\n\n'
        'Введите имя и фамилию через пробел.\n'
        'Либо нажмите на /cancel, чтобы выйти.'
    ),
    'SET_NAME_SUCCESS': (
        'Отлично, теперь вы можете увидеть расписание '
        'спектаклей только с участием: <b>{}</b>'
    ),
    # Системные сообщения
    'MAINTENANCE': 'Бот на техническом обслуживании.',
    'THROTTLING': (
        'Воу-воу! Слишком много запросов от тебя, подыши.\n\n'
        '<b>Техника дыхания (20 секунд):</b>\n'
        '1. Сядьте в удобное положение.\n'
        '2. Закройте глаза и сосредоточьтесь на дыхании.\n'
        '3. Глубоко вдохните через нос в течение 4 секунд.\n'
        '4. Задержите дыхание на 4 секунды.\n'
        '5. Медленно выдохните через рот в течение 4 секунд.\n'
        '6. Подождите 4 секунды перед следующим вдохом.\n'
        '7. Повторяйте эту последовательность в течение 20 секунд.\n\n'
    ),
    'TOP_ARTISTS_REPORT': 'Топ артистов по продажам',
    'ANALYTICS_MENU_TITLE': '📊 Меню аналитики',
    'CHOOSE_REPORT_PERIOD': '📅 Выберите период для отчета:',
    'TOP_SHOWS_SALES_REPORT_TITLE': 'Топ спектаклей по продажам',
    'TOP_SHOWS_SPEED_REPORT_TITLE': 'Топ спектаклей по скорости продаж',
    'PREDICT_SELL_OUT_REPORT_TITLE': 'Прогноз sold out',
    'PREDICT_SELL_OUT_LINE': '{index}. {name} ({show_date}) — ожидаемый sold out: {date}',
    'NO_DATA_FOR_REPORT': 'Нет данных для формирования отчета за указанный период.',
    'SALES_SPEED_UNIT_PER_DAY': 'бил./день',
    'SOLD_OUT_AT_TIMESTAMP': 'Продано полностью в: ', # Used with datetime
    'ALREADY_SOLD_OUT': 'Уже распродано!',
    'BACK_TO_MAIN_MENU': '↩️ Главное меню',
    'BACK_TO_ANALYTICS_MENU': '↩️ Меню аналитики',
    # Добавляем константы для новых отчётов
    'TOP_SHOWS_RETURNS_REPORT_TITLE': 'Топ спектаклей по возвратам билетов',
    'TOP_SHOWS_RETURN_RATE_REPORT_TITLE': 'Топ спектаклей по проценту возвратов',
}

LEXICON_COMMANDS_RU: dict[str, str] = {
    '/start': 'Привет, посмотрим расписание ?'
}

LEXICON_LOGS: dict[str, str] = {
    # Системные логи
    'BOT_STARTED': 'Bot has been launched and is ready to work. Administrator: {}',
    'BOT_STOPPED': 'Bot has been stopped',
    'BOT_STOPPED_BY_USER': 'Bot was stopped by user',
    'BOT_STOPPED_BY_KEYBOARD': 'Bot was stopped by keyboard interrupt',
    'BOT_ERROR': 'An error occurred while running the bot: {}',
    'BOT_SHUTDOWN_COMPLETE': 'Bot shutdown completed successfully',
    'ENGINE_CREATED': 'The database engine was created successfully',
    'SESSION_MAKER_INITIALIZED': 'Session maker has been initialized',
    'PROFTICKET_INITIALIZED': 'Successfully initialize profticket client',
    'LOG_MSG_ERROR_WHEN_START_MSG_TO_ADMIN': 'Error: {}',
    'LOG_MSH_HELP_COMMAND': 'UserID {} using /help command.',
    # Пользовательские логи
    'USER_GOT_SHOWS': '{} (@{}) ID({}) got shows for {} month',
    'USER_ERROR': 'Error occurred for user {} (@{}) ID({}): {}',
    # Логи проверки данных
    'NO_SHOW_DATA': 'No show data found in database',
    'DATA_IS_FRESH': 'Data is fresh, no update needed',
    'DATA_NEEDS_UPDATE': 'Data needs to be updated',
    'ERROR_CHECKING_DATA': 'Error checking data freshness: {}',
    # Логи ошибок
    'ERROR_ON_STARTUP': 'Error during bot startup: {}',
    'ERROR_ON_SHUTDOWN': 'Error during bot shutdown: {}',
}

LEXICON_NATIVE_COMMANDS_RU: dict[str, str] = {
    '/start': '🔁 Перезагрузка бота',
    '/help': '🆘 Нужна помощь!',
    '/set_actor': '👤Выбрать актёра/актрису',
    '/analytics': '📊 Аналитика',
}

LEXICON_BUTTONS_RU: dict[str, str] = {
    '/set_fighter': '👤Выбрать актёра/актрису',
    '/shows_with': 'Спектакли с: ',
    # Analytics Menu Buttons
    '/analytics_menu': '📊 Аналитика',
    # Report Types
    '/report_top_shows_sales': '🏆 Топ продаж (спектакли)',
    '/report_top_shows_speed': '⚡️ Топ скорости (спектакли)',
    '/report_predict_sell_out': '⏳ Прогноз Sold Out',
    '/report_top_artists_sales': '🎭 Топ продаж (артисты)',
    # Добавляем новые кнопки для отчётов по возвратам
    '/report_top_shows_returns': '🔄 Топ по возвратам',
    '/report_top_shows_return_rate': '📉 Топ по % возвратов',
    # Period Choices (prefix with report type in handler or use FSM)
    '/period_all_time': '🕒 За всё время',
    '/period_current_month': '📅 Текущий месяц',
    # Navigation
    '/back_to_main_menu': '↩️ Главное меню',
    '/back_to_analytics_menu': '↩️ Меню аналитики',
}
