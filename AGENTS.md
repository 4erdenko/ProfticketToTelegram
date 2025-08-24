# Repository Guidelines

## Project Structure & Module Organization
- `main.py`: application entrypoint (starts Telegram bot, middlewares, update loop).
- `telegram/`: bot features
  - `handlers/`, `middlewares/`, `db/`, `lexicon/`, `utils/`.
- `services/profticket/`: Profticket API client, analytics, utilities.
- `tests/`: pytest/unittest suites; name files `test_*.py`.
- `alembic/` + `alembic.ini`: database migrations.
- Other: `config.py` (settings via `.env`), `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml` (Ruff).

## Build, Test, and Development Commands
- Create venv + install deps:
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
- Run locally: `python main.py` (requires `.env` with tokens/DB).
- Lint/format (Ruff): `ruff format . && ruff check --fix .`
- Tests: `pytest -q` (single test: `pytest tests/test_utils.py::UtilsTestCase::test_pluralize`).
- Migrations (optional): `alembic upgrade head` (new: `alembic revision -m "msg" --autogenerate`).
- Docker: `docker-compose up -d` (starts Postgres and bot image).

## Coding Style & Naming Conventions
- Python 3.11, 4‑space indent, max line length 79.
- Strings: prefer single quotes; docstrings triple double quotes.
- Imports: sorted by Ruff (isort rules). First‑party: `telegram`, `services`.
- Filenames: `snake_case.py`; tests `test_*.py`; constants in CAPS.
- Add type hints for new/edited functions.

## Testing Guidelines
- Frameworks: pytest + unittest.
- Place tests under `tests/`; name tests `test_*` and classes `Test*`.
- Keep unit tests fast and deterministic; mock network/Telegram APIs.
- Run full suite before PR: `pytest -q`.

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
