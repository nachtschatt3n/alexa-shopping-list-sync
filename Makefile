.PHONY: dev restart down logs test test-int test-cov lint format shell venv

PY ?= mise exec -- python

venv:
	$(PY) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

dev:
	docker compose up -d
	docker compose logs -f homeassistant

restart:
	docker compose restart homeassistant

down:
	docker compose down

logs:
	docker compose logs -f homeassistant | grep -i alexa_shopping_list_sync

test:
	.venv/bin/pytest -q -m "not integration"

test-int:
	@if [ ! -f .env ]; then echo "ERROR: copy .env.example to .env and fill in ALEXA_EMAIL/ALEXA_PASSWORD"; exit 1; fi
	@set -a && . ./.env && set +a && .venv/bin/pytest -q -m integration

test-cov:
	.venv/bin/pytest --cov --cov-report=term-missing -m "not integration"

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

format:
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

shell:
	docker compose exec homeassistant bash
