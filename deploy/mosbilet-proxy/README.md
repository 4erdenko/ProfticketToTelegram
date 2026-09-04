# Прямой российский прокси для «Мосбилета»

Этот Compose запускается на российском сервере `185.11.246.62`, отдельно
от бота. Squid выходит в интернет напрямую. Существующий VLESS/SOCKS
на `127.0.0.1:1080` не используется и не изменяется. SSH нужен только
для администрирования, а не для передачи запросов бота.

Маршрут: бот на `188.245.236.164` → HTTPS-прокси на
`185.11.246.62:3129` → `tickets.mos.ru:443`.

Squid разрешает только CONNECT к этому домену и порту, только с IP бота,
после проверки пароля. TLS защищает соединение с прокси, включая пароль.
Сертификат самого «Мосбилета» проверяется отдельно стандартным хранилищем
доверия HTTPX; TLS interception/SSL bump не используется.

## Подготовка российского сервера

Команды ниже выполняются из каталога репозитория на российском сервере.
Нужны Docker Compose, OpenSSL и `htpasswd` (пакет `apache2-utils`).
Секреты создаются один раз и не перегенерируются при обычном обновлении.

```sh
install -d -m 700 .my_local_dev/mosbilet-proxy
PROXY_SECRETS_DIR="$(pwd)/.my_local_dev/mosbilet-proxy"
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
  -subj '/CN=mosbilet-proxy' \
  -addext 'subjectAltName=IP:185.11.246.62' \
  -keyout "$PROXY_SECRETS_DIR/proxy.key" \
  -out "$PROXY_SECRETS_DIR/proxy.crt"
htpasswd -cB "$PROXY_SECRETS_DIR/passwords" mosbilet
printf '%s\n' '188.245.236.164/32' > "$PROXY_SECRETS_DIR/allowed-clients"
chown -R 13:13 "$PROXY_SECRETS_DIR"
chmod 500 "$PROXY_SECRETS_DIR"
chmod 400 "$PROXY_SECRETS_DIR/"*
export MOSBILET_PROXY_BIND_IP=185.11.246.62
export MOSBILET_PROXY_SECRETS_DIR="$PROXY_SECRETS_DIR"
docker compose -f deploy/mosbilet-proxy/compose.yml build
docker compose -f deploy/mosbilet-proxy/compose.yml run --rm mosbilet-proxy squid -k parse
docker compose -f deploy/mosbilet-proxy/compose.yml up -d
```

UID 13 — пользователь `proxy` в образе Debian. Каталог должен быть доступен
для чтения этому UID. Не добавляйте ключ, пароль или `.env` в Git.
Дополнительно ограничьте входящий TCP 3129 IP-адресом бота в сетевом firewall;
при Docker published ports правила должны учитывать цепочку DOCKER-USER.
Срок сертификата — год: до истечения замените сертификат и обновите его
копию на сервере бота, затем пересоздайте оба контейнера.

## Подключение бота

Передайте **только публичный** `proxy.crt` по доверенному SSH-соединению на
сервер бота в `/opt/profticket_bot/.my_local_dev/mosbilet-proxy/proxy.crt`.
Обеспечьте чтение сертификата UID 10001 контейнера бота. Приватный ключ
остаётся на российском сервере. Добавьте в `.env` сервера бота:

```dotenv
MOSBILET_PROXY_URL=https://mosbilet:URL_ENCODED_PASSWORD@185.11.246.62:3129
MOSBILET_PROXY_CA_HOST_FILE=/opt/profticket_bot/.my_local_dev/mosbilet-proxy/proxy.crt
```

Пароль в URL должен быть percent-encoded. Override собирает образ бота
из текущего checkout и не использует старый опубликованный образ,
не поддерживающий `MOSBILET_PROXY_CA_FILE`. Сначала проверьте конфигурацию, затем применяйте
оба Compose-файла при запуске и последующих обновлениях:

```sh
docker compose -f docker-compose.yml -f docker-compose.mosbilet.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.mosbilet.yml up -d --build --no-deps profticket_bot_service
```

Override принудительно выбирает источник `ermolova`, монтирует сертификат
только для чтения и передаёт настройки прокси. Пустой URL или отсутствующий
файл сертификата приводят к ошибке запуска, а не к незаметному прямому выходу.
Обычный Compose без override сохраняет прежнюю возможность прямого доступа.

## Проверка после установки

Из нового контейнера бота выполните запрос без загрузки расписания в БД:

```sh
docker exec -i profticket_telegram_bot python - <<'PY'
import asyncio
from config import settings
from services.ermolova import ErmolovaInfo, INVENTORY_URL, parse_inventory

async def check():
    source = ErmolovaInfo(
        settings.MOSBILET_PROXY_URL,
        proxy_ca_file=settings.MOSBILET_PROXY_CA_FILE,
    )
    try:
        response = await source._get(
            source.inventory_client,
            INVENTORY_URL + '53398302/schema?theatrical=true',
        )
        print(parse_inventory(response.json()))
    finally:
        await source.aclose()

asyncio.run(check())
PY
```

ID в примере относится к событию сентября 2026; после его удаления замените
его актуальным ID из афиши. Проверьте также отказ без пароля, с неверным
паролем, с другого IP и при CONNECT к другому домену/порту. После успешного
запроса проверьте штатное обновление трёх месяцев по логам и данным БД.
Наличие файлов этой конфигурации в ветке само по себе не разворачивает прокси.
