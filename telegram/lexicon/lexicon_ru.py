from config import settings

INVENTORY_UNKNOWN = 'Билеты на сайте'
PERFORMANCE_FALLBACKS = {
    'name': 'Название не указано',
    'date': 'Дата уточняется',
    'inventory': 'Количество билетов неизвестно',
}

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
    'CHOOSE_MONTH': 'На какой месяц показать спектакли?',
    'ERROR_MSG': 'Произошла ошибка, попробуйте ещё раз через минутку.',
    'WAIT_MSG': 'Собираю данные, это займёт немного времени…',
    'NONE_SHOWS_THIS_MONTH': 'Спектаклей в этом месяце нет.',
    'HELP_CONTACT': f'Если нужна помощь, напиши сюда: {settings.ADMIN_USERNAME}',
    # Сообщения для работы с актёрами
    'SET_NAME': ('Как зовут актёра?\nНапример: <b>Олег Меньшиков</b>'),
    'WRONG_FIO': (
        'Напишите имя и фамилию через пробел.\n'
        'Например: <b>Олег Меньшиков</b>\n'
        'Отмена: /cancel'
    ),
    'SET_NAME_SUCCESS': (
        '🎭 Выбрали: <b>{}</b>\n'
        'Теперь можно посмотреть спектакли с этим актёром.'
    ),
    # Системные сообщения
    'MAINTENANCE': 'Бот на техническом обслуживании.',
    'THROTTLING': (
        f'Слишком много нажатий. Подождите {settings.TTL_IN_SEC} секунд.'
    ),
    'TOP_ARTISTS_REPORT': '🎭 Билеты на спектакли с актёрами',
    'ANALYTICS_MENU_TITLE': '📊 Билеты на сайте\nЧто хотите узнать?',
    'CHOOSE_REPORT_PERIOD': '📅 За какой период показать данные?',
    'TOP_SHOWS_SALES_REPORT_TITLE': '🎟 Где билетов стало меньше',
    'TOP_SHOWS_SALES_FORMAT_EXPLANATION': (
        'Считаем все уменьшения. Итог учитывает добавленные билеты.'
    ),
    'TOP_SHOWS_SPEED_REPORT_TITLE': '⚡️ Как быстро уходят билеты',
    'TRENDS_REPORT_TITLE': '📈 Что с билетами',
    'TOP_SHOWS_SPEED_FORMAT_EXPLANATION': (
        'Среднее за последние сутки наблюдений.'
    ),
    'PREDICT_SELL_OUT_REPORT_TITLE': '⏳ Когда могут закончиться билеты',
    'PREDICT_SELL_OUT_LINE': (
        '{index}. <b>{name}</b>\n'
        '📅 {show_date}\n'
        'Могут закончиться примерно <b>{date}</b>, если будут уходить так же.'
    ),
    'NO_DATA_FOR_REPORT': 'Пока нет данных за этот период',
    'NO_RELIABLE_FORECAST': (
        'Пока нельзя надёжно сказать, когда закончатся билеты.\n'
        'Посмотрите «📈 Что с билетами»: там есть остаток и изменения.'
    ),
    'SALES_SPEED_UNIT_PER_DAY': 'билетов в день',
    'SOLD_OUT_AT_TIMESTAMP': 'Билетов на сайте нет с ',
    'ALREADY_SOLD_OUT': 'Сейчас билетов на сайте нет.',
    'BACK_TO_MAIN_MENU': '↩️ Главное меню',
    'BACK_TO_ANALYTICS_MENU': '↩️ Меню аналитики',
    # Добавляем константы для новых отчётов
    'TOP_SHOWS_RETURNS_REPORT_TITLE': '🎟 Где билетов стало больше',
    'TOP_SHOWS_RETURN_RATE_REPORT_TITLE': '🔄 Сколько билетов добавляется',
    'TOP_SHOWS_SALES_LINE': (
        '{index}. <b>{name}</b>\n'
        'Все уменьшения: <b>{gross}</b>.\n'
        'Итого: {net_change}.{tracking}'
    ),
    'TOP_ARTISTS_SALES_LINE': (
        '{index}. <b>{name}</b>\nБилетов стало меньше на <b>{sold}</b>.'
    ),
    'TOP_SHOWS_SPEED_LINE': (
        '{index}. <b>{name}</b>{status}\nВ среднем за день: <b>{speed}</b>.'
    ),
    # Mark archived performances in the pace report.
    'SHOW_STATUS_PAST': ' (архив)',
    'SHOW_STATUS_CURRENT': '',
    'TOP_SHOWS_RETURNS_LINE': (
        '{index}. <b>{name}</b>\nБилетов добавилось: <b>{returns}</b>.'
    ),
    'TOP_SHOWS_RETURN_RATE_LINE': (
        '{index}. <b>{name}</b>\n'
        'На каждые 100 исчезнувших билетов добавилось <b>{percent}</b>.'
    ),
    'TRACKING_SINCE': '\nСчитаем с {date}.',
    'CALENDAR_PACE_REPORT_TITLE': '📅 Билеты по датам спектаклей',
    'CALENDAR_PACE_FORMAT_EXPLANATION': (
        'Изменения билетов на сайте для каждой даты спектакля.'
    ),
    'CALENDAR_PACE_DATE_LINE': (
        '<b>{date}</b>\n'
        '{shows}\n'
        'Меньше на <b>{gross}</b>, больше на <b>{refunds}</b>.\n'
        'Итого: {net_change}.'
    ),
    'CALENDAR_PACE_SUMMARY': (
        '📊 <b>Всего за период</b>\n'
        'Меньше на <b>{total_gross}</b>, больше на <b>{total_refunds}</b>.\n'
        'Итого: {net_change}.\n'
        'В среднем на дату спектакля: на <b>{avg_gross}</b> меньше.'
    ),
    # Админ-меню
    'ADMIN_MENU_TITLE': '🛠 Админ-меню',
    'ADMIN_STATS_TITLE': 'Админ-статистика',
    'ADMIN_USERS_TITLE': '👥 Пользователи — обзор',
    'ADMIN_PREFS_TITLE': '🎭 Предпочтения пользователей',
    'ADMIN_DB_TITLE': '🗄 Сводка по базе',
    'NO_PREFS': 'Нет данных о предпочтениях пользователей.',
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
    '/subscriptions': '🔔 Подписки на спектакли и артистов',
}

LEXICON_BUTTONS_RU: dict[str, str] = {
    '/subscriptions': '🔔 Подписки',
    '/set_fighter': '👤Выбрать актёра/актрису',
    '/shows_with': 'Спектакли с: ',
    # Analytics Menu Buttons
    '/analytics_menu': '📊 Аналитика',
    # Report Types
    '/report_top_shows_sales': '🏆 Билетов стало меньше',
    '/report_top_shows_speed': '⚡️ Как быстро уходят билеты',
    '/report_trends': '📈 Что с билетами',
    '/report_predict_sell_out': '⏳ Прогноз билетов',
    '/report_top_artists_sales': '🎭 По актёрам',
    '/report_calendar_pace': '📅 По датам',
    # Добавляем новые кнопки для отчётов по возвратам
    '/report_top_shows_returns': '🔄 Билетов стало больше',
    '/report_top_shows_return_rate': '📉 Сравнить изменения',
    # Period Choices (prefix with report type in handler or use FSM)
    '/period_all_time': '🕒 За всё время',
    '/period_current_month': '📅 Текущий месяц',
    # Navigation
    '/back_to_main_menu': '↩️ Главное меню',
    '/back_to_analytics_menu': '↩️ Меню аналитики',
    # Admin
    '/admin_menu': '🛠 Админка',
    '/admin_stats': '📈 Статистика',
    '/admin_users': '👥 Пользователи',
    '/admin_prefs': '🎭 Предпочтения',
    '/admin_db': '🗄 База (шоу)',
}

LEGACY_ANALYTICS_BUTTONS = {
    '🏆 Уменьшение билетов': '/report_top_shows_sales',
    '⚡️ Темп изменения': '/report_top_shows_speed',
    '📈 Тенденции': '/report_trends',
    '🎭 Динамика по артистам': '/report_top_artists_sales',
    '📅 Динамика по датам': '/report_calendar_pace',
    '🔄 Пополнение квоты': '/report_top_shows_returns',
    '📉 Пополнение / уменьшение': '/report_top_shows_return_rate',
    '🏆 Топ продаж (спектакли)': '/report_top_shows_sales',
    '⚡️ Топ скорости (спектакли)': '/report_top_shows_speed',
    '⏳ Прогноз Sold Out': '/report_predict_sell_out',
    '🎭 Топ продаж (артисты)': '/report_top_artists_sales',
    '📅 Календарь продаж': '/report_calendar_pace',
    '🔄 Топ по возвратам': '/report_top_shows_returns',
    '📉 Топ по % возвратов': '/report_top_shows_return_rate',
}
