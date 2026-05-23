.PHONY: dev dev-docker restart down logs sync test test-int test-cov lint format shell venv

PY ?= mise exec -- python

venv:
	$(PY) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt

# Re-stage the custom_component into .dev/config/ so the running HA picks up
# the latest code on next restart. Called by `make dev` automatically.
sync:
	rm -rf .dev/config/custom_components/alexa_shopping_list_sync
	mkdir -p .dev/config/custom_components
	cp -R custom_components/alexa_shopping_list_sync .dev/config/custom_components/
	find .dev/config/custom_components/alexa_shopping_list_sync -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Run HA from the venv (no Docker needed). Logs stream to the foreground;
# Ctrl-C to stop. UI on http://localhost:8123 once you see "Home Assistant
# initialized in <N>s" in the log.
dev: sync
	.venv/bin/hass -c .dev/config

# Docker-based dev loop (requires Docker Desktop). Identical behavior to `dev`.
dev-docker: sync
	docker compose up -d
	docker compose logs -f homeassistant

restart:
	@echo "Stop the foreground hass with Ctrl-C and re-run \`make dev\`. Or for Docker: make sync && docker compose restart homeassistant"

down:
	docker compose down 2>/dev/null || true

logs:
	@if [ -f .dev/config/home-assistant.log ]; then tail -f .dev/config/home-assistant.log | grep -i alexa_shopping_list_sync; else docker compose logs -f homeassistant | grep -i alexa_shopping_list_sync; fi

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
