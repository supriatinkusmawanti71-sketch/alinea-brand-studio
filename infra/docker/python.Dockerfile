FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /workspace

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY apps ./apps
COPY backend ./backend
COPY contracts ./contracts
COPY alembic.ini ./alembic.ini
COPY infra/migrations ./infra/migrations

RUN useradd --create-home --uid 10001 app
USER app

CMD ["uv", "run", "uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
