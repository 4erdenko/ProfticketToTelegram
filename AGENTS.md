# Repository Guidelines

## Project Structure & Module Organization
- `main.py`: application entrypoint (starts Telegram bot, middlewares, update loop).
- `telegram/`: bot features
  - `handlers/`, `middlewares/`, `db/`, `lexicon/`, `utils/`.
- `services/profticket/`: Profticket API client, analytics, utilities.
- `tests/`: pytest/unittest suites; name files `test_*.py`.
- `alembic/` + `alembic.ini`: database migrations.
- Other: `config.py` (settings via `.env`), `pyproject.toml` + `uv.lock` (dependencies and Ruff), `Dockerfile`, `docker-compose.yml`.

## Build, Test, and Development Commands
- Create venv + install deps: `uv sync --locked`.
- Run locally: `uv run --locked main.py` (requires `.env` with tokens/DB).
- Lint/format (Ruff): `uv run --locked ruff format . && uv run --locked ruff check --fix .`.
- Tests: `uv run --locked pytest -q` (single test: `uv run --locked pytest tests/test_utils.py::UtilsTestCase::test_pluralize`).
- Migrations before startup: `uv run --locked alembic upgrade head` (new: `uv run --locked alembic revision -m "msg" --autogenerate`).
- Docker: start Postgres with `docker compose up -d --wait profticket_postgres`, run migrations with `docker compose run --rm --no-deps profticket_bot_service alembic upgrade head`, then start `profticket_bot_service`.

## Coding Style & Naming Conventions
- Python 3.14, 4‑space indent, max line length 79.
- Strings: prefer single quotes; docstrings triple double quotes.
- Imports: sorted by Ruff (isort rules). First‑party: `telegram`, `services`.
- Filenames: `snake_case.py`; tests `test_*.py`; constants in CAPS.
- Add type hints for new/edited functions.

## Testing Guidelines
- Frameworks: pytest + unittest.
- Place tests under `tests/`; name tests `test_*` and classes `Test*`.
- Keep unit tests fast and deterministic; mock network/Telegram APIs.
- Run full suite before PR: `uv run --locked pytest -q`.

## Commit & Pull Request Guidelines
- Use Conventional Commits for clarity, mirroring history (e.g., `feat(telegram): add throttling`, `fix(analytics): handle empty data`).
- PRs must include: clear summary, rationale, test coverage for changes, screenshots/log snippets when UX/text output changes, and migration notes if DB schema changes.
- Keep diffs focused; update `README.MD`/docs when behavior or config changes.

## Communication & Language
- Communicate in the language of the request (issues, PRs, reviews, and user‑facing messages). Example: report in Russian → reply in Russian; in English → reply in English.
- Keep responses concise and professional; include concrete commands/paths where helpful.

## Security & Configuration Tips
- Never commit secrets. Configure via `.env` (see `config.py`): `BOT_TOKEN`, `ADMIN_ID`, `DB_URL`, `COM_ID`, `IN_DOCKER`, etc.
- Avoid real network calls in tests; use stubs/mocks.
