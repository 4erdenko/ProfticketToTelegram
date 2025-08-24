# Profticket To Telegram — theater shows and analytics bot

![Python](https://img.shields.io/badge/Python-3.11-blue)
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

- Python 3.11
- PostgreSQL 14+

## Setup

1) Create venv and install deps:
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2) Copy `.env.example` to `.env` and fill values:
```
cp .env.example .env
```

3) (Optional) Apply migrations:
```
alembic upgrade head
```

4) Run the bot:
```
python main.py
```

## Environment variables

See `.env.example`. Minimal: `BOT_TOKEN`/`TEST_BOT_TOKEN`, `ADMIN_ID`, `DB_URL`,
`COM_ID`, `DEFAULT_TIMEZONE`. For Docker set `IN_DOCKER=true` so the app uses
`BOT_TOKEN` instead of `TEST_BOT_TOKEN`.

## Docker

Quick start:
```
docker-compose up -d
```
Starts Postgres and the bot image. Ensure env vars are provided.

## Tests and linting

```
pytest -q
ruff format . && ruff check --fix .
```

Tests are fast and deterministic; network calls are stubbed/mocked.

## Commands and menus

- Native menu is configured in `telegram/keyboards/native_menu.py`: `/start`,
  `/help`, `/set_actor`, `/analytics`.
- Button texts: `telegram/lexicon/lexicon_ru.py`.

## Logging

Configured in `telegram/utils/startup.py` (`setup_logging`), printed to stdout
via `coloredlogs` at INFO level.

## Contributing

Before submitting a PR:
- `ruff format . && ruff check --fix .`
- `pytest -q`
- Follow Conventional Commits (e.g., `feat(telegram): ...`).
- Never commit secrets; use `.env`.

## Roadmap

- Pagination in admin and analytics reports.
- CSV export for preferences/tops.
- User lookup (id/username) with quick card.
- Role/ban management from admin menu.

## License & contact

License — MIT (see `LICENSE`). For support, check `ADMIN_USERNAME` in `.env`.
