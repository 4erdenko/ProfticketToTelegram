FROM python:3.14.8-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache

# Non-root user for security
RUN useradd -u 10001 -m app
COPY --chown=app:app . .
USER app

CMD ["python","main.py"]
