from config import settings

LEXICON_COMMANDS_RU: dict = {
    '/start': f"""

<b>Привет, это FRDM!</b>

<b>VPN</b> сервис на протоколе который не умеют блокировать:
Китай, Иран и Россия.

<b>Wireguard, OpenVPN, Outline, Shadowsocks</b> уже успешно блокируются в 
России, тесты блокировок прошли в августе 2023 года.

Наш протокол, на данный момент, блокировать  <b>никто</b> не умеет.

<b>FRDM</b> настроен под <b>Россию</b> и <b>СНГ</b>. 
(кроме Туркменистана)

Оплачивая подписку, ты получаешь сразу <b>3 конфига для трёх устройств</b> и 
<b>150Гб</b> трафика для каждого конфига.

Можно установить на: 
<b>IOS/Android/MacOS/Windows/Linux</b>.

Пробный доступ даётся на <b>3 дня</b>, но лишь 1 конфиг.

Если есть вопросы:
{settings.ADMIN_USERNAME}

""",
    '/help': 'Помощь уже идёт.',

    '/throttling': 'Воу-воу! Слишком много запросов от тебя, подыши.\n\n'
                   '<b>Техника дыхания (20 секунд):</b>\n'
                   '1. Сядьте в удобное положение.\n'
                   '2. Закройте глаза и сосредоточьтесь на дыхании.\n'
                   '3. Глубоко вдохните через нос в течение 4 секунд.\n'
                   '4. Задержите дыхание на 4 секунды.\n'
                   '5. Медленно выдохните через рот в течение 4 секунд.\n'
                   '6. Подождите 4 секунды перед следующим вдохом.\n'
                   '7. Повторяйте эту последовательность в течение 20 секунд.\n'
                   '\n',
    '/throttling_call_back': 'Слишком много запросов, подыши 20 секунд!',
    '/admin_stats': 'Статус обслуживания: {maint}\n'
                    'Цена: <code>{price}</code>Р\n'
                    'В базе:\n\n'
                    'Юзеров: <code>{all_users}</code>\n'
                    'С подпиской: <code>{subs}</code>\n'
                    'Без подписки: <code>{no_subs}</code>\n'
                    'Заблокировали бота: <code>{b_block}</code>\n'
                    'Online: <code>{online_value}</code>\n'
                    'Online users: {online_users}',
    '/restart_bot': 'Перезапуск бота',
    '/maintenance_toggle': 'Обслуживание ON/OFF',
    '/get_admin_stats': 'Статистика',
    '/buy_subscription': 'Оплатить подписку',
    '/get_trial_subscription': '⏱ Пробный период на 3 дня',
    '/get_my_configs': 'Мои конфиги',


}

LEXICON_RU: dict = {
    'ERROR': f'Воу! Произошла какая-то ошибка!\nСообщи об этом'
             f': {settings.ADMIN_USERNAME}',
    'THREE_DAYS_MSG': 'Подписку можно продлить не ранее, чем за 3 дня до её '
                      'окончания😎',
    'ONE_DAY_MSG': 'Подписку можно продлить не ранее, чем за 24 часа до её '
                   'окончания😎',
    'CONFIGS_BLOCK': '<pre language="vless-config">{}</pre>\n',
    'CHEATER': 'Вот твой триальный конфиг:\n\n'
               '<span class="tg-spoiler"><i>Ублюдок, мать твою, а ну, '
               'иди сюда, говно собачье, а? Сдуру решил ко мне лезть, '
               'ты? Засранец вонючий, мать твою, а? Ну, иди сюда, попробуй '
               'меня трахнуть — я тебя сам трахну, ублюдок, онанист чёртов, '
               'будь ты проклят! Иди, идиот, трахать тебя и всю твою семью! '
               'Говно собачье, жлоб вонючий, дерьмо, сука, падла! Иди сюда, '
               'мерзавец, негодяй, гад! Иди сюда, ты, говно, жопа!</i></span>',
    'MAINTENANCE': 'Бот на техническом обслуживании.',
    'SUBSCRIBE_EXPIRATION': 'Подписка истекает уже:\n<code>{}</code>\nМожно оплачивать ❤️',
    'BOT_RESTART': 'Перезагружаемся!',
}

LEXICON_LOGS: dict = {
    'BOT_STARTED': 'Бот запущен и готов к работе. Администратор: {}',
    'ENGINE_CREATED': 'Движок базы данных успешно создан',
    'SESSION_MAKER_INITIALIZED': 'Session maker инициализирован',
    'LOG_MSG_ERROR_WHEN_START_MSG_TO_ADMIN': 'Error: {}',
    'LOG_MSG_GET_USER_VPN_UUIDS': 'Получение UUID VPN для пользователя с ID {}.',
    'LOG_MSG_CREATE_USER_VPN_UUIDS_START': 'Начало создания UUID VPN для пользователя с ID {}.',
    'LOG_MSG_CREATE_USER_VPN_UUIDS_SUCCESS': 'Успешно созданы UUID VPN для пользователя с ID {}.',
    'LOG_MSG_CREATE_USER_VPN_UUIDS_FAIL': 'Ошибка при создании UUID VPN для пользователя с ID {}: {}',
    'LOG_MSG_UPDATE_SUBSCRIPTION_STATUS': 'Обновление статуса подписки для пользователя с ID {}. Новый статус: {}.',
    'LOG_MSG_SUCCESSFUL_PAYMENT': 'Успешная оплата для пользователя с ID {}.',
    'LOG_MSG_ADMIN_COMMAND_RECEIVED': 'Получена команда админа от пользователя с ID {}.',
    'LOG_MSG_ADMIN_RESPONSE_SENT': 'Отправлен ответ админу с ID {}.',
    'LOG_MSG_USER_BLOCKED_BOT': 'Пользователь с ID {} заблокировал бота.',
    'LOG_MSG_USER_UNBLOCKED_BOT': 'Пользователь с ID {} разблокировал бота.',
    'LOG_MSG_USER_BLOCKED_BOT_UPDATED': 'Обновлен статус блокировки бота для пользователя с ID {}.',
    'LOG_MSG_USER_BOT_STATUS_UPDATE': 'User {} has been successfully {} by himself.',
    'LOG_MSG_USER_UNBLOCKED_BOT_UPDATED': 'Обновлен статус разблокировки бота для пользователя с ID {}.',
    'LOG_MSG_PURCHASE_INITIATED': 'Инициирована покупка подписки пользователем с ID {}.',
    'LOG_MSG_PRE_CHECKOUT_QUERY': 'Обработка предоплатного запроса от пользователя с ID {}.',
    'LOG_MSG_VPN_CONFIGS_SENT': 'Отправлены VPN конфигурации пользователю с ID {}.',
    'LOG_MSG_TRIAL_VPN_DETECTED': 'Обнаружена пробная VPN конфигурация для пользователя с ID {}.',
    'LOG_MSG_TRIAL_VPN_DELETED': 'Пробная VPN конфигурация удалена для пользователя с ID {}.',
    'LOG_MSG_CREATING_NEW_VPN_CONFIGS': 'Создание новых VPN конфигураций для пользователя с ID {}.',
    'LOG_MSG_VPN_CONFIGS_CREATED': 'VPN конфигурации созданы для пользователя с ID {}.',
    'LOG_MSG_EXTENDING_VPN_CONFIGS': 'Расширение существующих VPN конфигураций для пользователя с ID {}.',
    'LOG_MSG_VPN_CONFIGS_EXTENDED': 'VPN конфигурации расширены до {} для пользователя с ID {}.',
    'LOG_MSG_NO_VPN_CONFIGS': 'У пользователя с ID {} нет VPN конфигураций.',
    'LOG_MSG_SENDING_INVOICE': 'Отправка счета пользователю с ID {}.',
    'LOG_MSG_WITHIN_THREE_DAYS': 'Срок действия VPN пользователя с ID {} истекает менее чем через три дня.',
    'LOG_MSG_WITHIN_ONE_DAY': 'Срок действия VPN пользователя с ID {} истекает менее чем через 24 часа.',
    'LOG_MSG_CMD_START': 'Команда /start получена от пользователя с ID {}.',
    'LOG_MSG_CMD_HELP': 'Команда /help получена от пользователя с ID {}.',
    'LOG_MSG_CMD_TRIAL': 'Команда на получение пробного периода от пользователя с ID {}.',
    'LOG_MSG_USER_ALREADY_TRIALED': 'Пользователь с ID {} уже использовал пробный период.',
    'LOG_MSG_TRIAL_VPN_CREATING': 'Создание пробного VPN для пользователя с ID {}.',
    'LOG_MSG_TRIAL_VPN_CREATED': 'Пробный VPN создан для пользователя с ID {}.',
    'LOG_MSG_TRIAL_VPN_CONFIG_SENDING': 'Отправка конфигурации пробного VPN пользователю с ID {}.',
    'LOG_MSG_CMD_MY_CONFIG': 'Запрос на получение конфигов от пользователя с ID {}.',
    'LOG_MSG_SEND_CONFIG': 'Отправка конфигурации VPN для пользователя с ID {}, UUID {uuid}.',
    'LOG_MSG_SEND_INVOICE': 'Отправка счета пользователю с ID {}.',
    'LOG_MSG_CHECKING_ACTIVE_USERS': 'Проверка активных пользователей с VPN на подписку.',
    'LOG_MSG_VPN_EXPIRATION_NOTIFY': 'Уведомление пользователя с ID {} о скором истечении срока VPN.',
    'LOG_MSG_VPN_LOGIN': 'Вход в VPN выполнен.',
    'LOG_MSG_ADD_CONFIG': 'Добавление конфигурации VPN.',
    'LOG_MSG_GET_CONFIG': 'Получение конфигурации VPN.',
    'LOG_MSG_UPDATE_CONFIG': 'Обновление конфигурации VPN.',
    'LOG_MSG_DELETE_CLIENT': 'Удаление клиента VPN с UUID {}.',
    'LOG_MSG_RESET_CONFIG_TRAFFIC': 'Сброс трафика для VPN конфигурации с email {}.',
    'LOG_MSG_REQUEST_ERROR': 'Произошла ошибка при выполнении запроса: {}',
}