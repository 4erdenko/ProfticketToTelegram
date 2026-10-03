# Profticket To Telegram — theater shows and analytics bot

![Python](https://img.shields.io/badge/Python-3.14-blue)
![Aiogram](https://img.shields.io/badge/Aiogram-3.x-0aa)
![Ruff](https://img.shields.io/badge/Ruff-lint%20%26%20format-ff69b4)
![Tests](https://img.shields.io/badge/Tests-pytest-informational)
![Docker](https://img.shields.io/badge/Docker-compose-blue)
![License](https://img.shields.io/badge/License-MIT-green)

English documentation. For Russian version see README.MD.

## Table of contents

- Purpose
- Features
- Architecture
- Requirements
- Setup
- Environment variables
- Docker
- Tests and linting
- Commands and menus
- Logging
- Contributing
- Roadmap
- License & contact

## Purpose

Telegram bot that shows theater performances from Profticket and provides
lightweight sales analytics. Supports user preferences (by actor) and an admin
panel with metrics.

## Features

- Main menu: month selection, personal filter “👤 Choose actor/actress”, and
  “📊 Analytics”.
- Personal view: schedule filtered by chosen actor.
- Analytics:
  - 🏆 Top sales (shows) — gross/net;
  - ⚡️ Sales speed (shows) — current pace;
  - ⏳ Sold Out prediction — soonest sold outs;
  - 🎭 Top sales (artists);
  - 📅 Sales calendar (by date);
  - 🔄 Top returns and 📉 Top return rate.
- Long responses are split into chunks to fit Telegram limits.
- Admin panel (🛠 Admin):
  - 📈 Stats — overview/tops, including user’s current chosen actor;
  - 👥 Users — activity, roles, top by searches/throttling;
  - 🎭 Preferences — top chosen artists, user samples, users without choice;
  - 🗄 Database (shows) — shows/seat history metrics, data freshness.

Admin panel is available for `ADMIN_ID` and users with `User.admin=True`.

## Architecture

- `main.py` — startup, middlewares, background data updates.
- `telegram/` — handlers, keyboards, filters, middlewares, utilities.
- `services/profticket/` — Profticket client and analytics.
- `alembic/` — DB migrations; `alembic.ini` — Alembic config.
- `tests/` — pytest suites for analytics and utilities.

## Requirements

- Python 3.14 (managed by uv)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL 17 (the image version used by Compose)

## Setup

1) Install Python and sync the environment:
```sh
uv python install
uv sync --locked
```

The Python version is pinned in `.python-version`. Dependencies are declared in
`pyproject.toml`, with exact versions recorded in `uv.lock`. The command creates
`.venv` and includes development tools from the
`dev` group. Commands using `uv run` do not require activating the environment.

2) Copy `.env.example` to `.env` and fill values:
```sh
cp .env.example .env
```

3) Apply migrations before starting the bot:
```sh
uv run --locked alembic upgrade head
```

Migration `a137bd92c410` backfills legacy NULL deletion flags to false, adds
a non-null constraint/default and a `(show_id, timestamp, id)` history index.
Seat history is preserved. Back up a production database before upgrading;
index creation may temporarily block writes.

Past months are archived automatically and remain available in historical
reports. Observed inventory decreases and increases are aggregated in
PostgreSQL. Pace uses the last 24 hours; prediction uses seven days. For a
selected historical month, speed uses the last 24 hours of observations for
each event.

4) Run the bot:
```sh
uv run --locked main.py
```

## Environment variables

See `.env.example`. Minimal: `BOT_TOKEN`/`TEST_BOT_TOKEN`, `ADMIN_ID`, `DB_URL`,
`COM_ID`, `DEFAULT_TIMEZONE`. For Docker set `IN_DOCKER=true` so the app uses
`BOT_TOKEN` instead of `TEST_BOT_TOKEN`.

## Docker

Quick start:
```sh
docker compose up -d --wait profticket_postgres
docker compose run --rm --no-deps profticket_bot_service alembic upgrade head
docker compose up -d profticket_bot_service
```
Starts Postgres, applies the schema and starts the bot image. Provide env vars.

To verify a local image build:
```sh
docker build -t profticket_to_tg:local .
```

The image uses Python 3.14 and dependencies from `uv.lock` without the `dev`
group. Compose starts the published image; building locally does not replace
that image automatically.

## Tests and linting

```sh
uv run --locked pytest -q
uv run --locked ruff format --check .
uv run --locked ruff check .
```

Tests are fast and deterministic; network calls are stubbed/mocked.

To format code and apply automatic lint fixes:
```sh
uv run --locked ruff format .
uv run --locked ruff check --fix .
```

## Commands and menus

- Native menu is configured in `telegram/keyboards/native_menu.py`: `/start`,
  `/help`, `/set_actor`, `/analytics`, `/subscriptions`.
- Button texts: `telegram/lexicon/lexicon_ru.py`.

## Subscriptions and trends

In a private chat, open **🔔 Подписки** or `/subscriptions`. Search for a show
or artist by part of its name, choose a result and a delivery interval:
30 minutes, 1 hour, 6 hours, 12 hours, daily or weekly. A show subscription
covers its upcoming performances, including new dates. An artist subscription
covers shows whose published cast includes that artist; alternate performers
in the published cast do not confirm their participation on a particular date.

Subscription cards provide frequency changes, pause, resume and deletion.
Only changes trigger a notification. Creation and resumption establish a
baseline from the current state. Delivery frequency is independent of source
polling, which uses `UPDATE_INTERVAL`. Settings and baselines persist in the
database. Large digests provide an “Остальные изменения →” button. Saved pages
preserve every change at delivery time and remain available only to the
recipient, including after restarts and subsequent notifications.
Apply migrations through `d734c2a8f190` before starting the updated bot:
`uv run --locked alembic upgrade head`.

**📈 Тенденции** shows available inventory, observed decreases and increases
over 24 hours, pace and a comparison with the preceding day. Inventory
snapshots do not expose orders: decreases can include quota removal, while
increases can include additional inventory. These are not confirmed sales
or refunds.

The conditional depletion forecast requires at least a day of fresh history,
checks gaps, quota jumps and pace stability, and stops at the performance date
or a 14-day horizon. It uses changes over actual elapsed time instead of
quadratic extrapolation. The range describes pace scenarios, not a probability
or statistical confidence interval. Reports explain unavailable forecasts.

## Logging

Configured in `telegram/utils/startup.py` (`setup_logging`), printed to stdout
via `coloredlogs` at INFO level.

## Contributing

Before submitting a PR:

- `uv run --locked ruff format --check .`
- `uv run --locked ruff check .`
- `uv run --locked pytest -q`
- Update `pyproject.toml` and `uv.lock` together when changing dependencies.
- Follow Conventional Commits (e.g., `feat(telegram): ...`).
- Never commit secrets; use `.env`.

## Roadmap

- Pagination in admin and analytics reports.
- CSV export for preferences/tops.
- User lookup (id/username) with quick card.
- Role/ban management from admin menu.

## License & contact

License — MIT (see `LICENSE`). For support, check `ADMIN_USERNAME` in `.env`.


## Ermolova / Mosbilet source

For a persistent direct Russian egress without an SSH tunnel, use the separate
HTTPS proxy in `deploy/mosbilet-proxy` and `docker-compose.mosbilet.yml` on the
bot host. `MOSBILET_PROXY_CA_FILE` trusts the proxy certificate only; destination
TLS verification still uses the default trust store. See the deployment guide
in `deploy/mosbilet-proxy/README.md` for credentials, IP ACLs and certificate renewal.

The default `SCHEDULE_SOURCE=ermolova` reads the official theatre schedule and
cast, then obtains `available_tickets` from Mosbilet. Set
`SCHEDULE_SOURCE=profticket` to explicitly select the legacy provider.

Configure `MOSBILET_PROXY_URL` in `.env` if Mosbilet requires Russian egress.
HTTP CONNECT and SOCKS5 proxies are supported. For a local SSH tunnel:

```sh
ssh -N -D 127.0.0.1:18080 -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 ru-server
```

Use `MOSBILET_PROXY_URL=socks5h://127.0.0.1:18080` while that tunnel is running.
For Docker, use an endpoint reachable from inside the container; its loopback
is not the host loopback. Keep proxy credentials out of Git. Only Mosbilet
requests use this proxy; TLS verification remains enabled.

Unknown inventory is displayed as a link to the theatre and is never saved as
zero seat history. Months remain visible before sales open. Failed or unverified
empty refreshes preserve the previous monthly snapshot and alert once after
three failures for that month, resetting after a successful refresh.

New performances use `ermolova:` IDs and negative website show IDs, separate from
legacy Profticket history. Switching sources uses existing fields. New sales analytics
need new observations; missing historical observations cannot be reconstructed.
Published casts can include alternate performers rather than a date-specific cast.
