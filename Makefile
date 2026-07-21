.PHONY: bootstrap dev down restart logs ps test lint build check clean

bootstrap:
	cp .env.example .env 2>/dev/null || true
	npm install
	uv sync

dev:
	docker compose up --build

down:
	docker compose down --remove-orphans

restart:
	docker compose down --remove-orphans
	docker compose up --build

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

test:
	uv run pytest
	npm run test:web

lint:
	uv run ruff check .
	uv run ruff format --check .
	npm run lint:web
	npm run typecheck:web

build:
	npm run build:web

check: lint test build

clean:
	docker compose down --volumes --remove-orphans
	rm -rf .venv node_modules apps/web/.next
