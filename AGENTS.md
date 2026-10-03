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

## Autonomous Review and Fix Loop
- The user has authorized the complete review and fix loop for this project. A normal request to review uncommitted changes starts the loop, as does an implementation or fix request; do not stop at findings and wait for another "fix" message. Stay read-only only when the user explicitly asks for review without fixes.
- Inspect the combined staged, unstaged and untracked changes against HEAD, including affected callers and integrations. Preserve unrelated user changes and stay within the authorized task.
- Delegate independent, read-only reviews of separate affected areas when useful. After fixing a finding, have another agent review the fix and its affected behavior.
- Accept findings only when code tracing or a focused reproduction establishes a concrete bug and impact. Record each finding and its resolution in the task; do not turn style preferences, speculation or unrelated existing defects into more work.
- Fix confirmed findings without waiting for another "fix" message. Add a meaningful regression test when warranted, then run the affected checks with `uv run --locked`. Run Ruff, formatting checks and the full test suite before completion; use PyCharm diagnostics when available.
- Review the resulting changes again. Repeat fixes, relevant checks and independent review until no confirmed findings remain and all required checks pass. Reuse passed checks and unchanged-area reviews; repeat or broaden them only after changes, failures or a specific unresolved doubt.
- If progress stalls, investigate the cause or change the approach. Ask only for missing information or approval that is actually required, stating the concrete blocker; an arbitrary number of rounds is not a success condition.
- This loop does not authorize Git staging, commits, pushes, deployment, Kubernetes changes or Telegram actions. Follow their separate approval rules and never expand the task to clear unrelated problems.
- Report the closed findings, completed checks and any unverified limits concisely. A clean review means no confirmed bugs were found in the inspected scope, not a guarantee that the project has no bugs.

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
