# PetPop PoC. PETPOP_MODE=mock is the default everywhere (BRIEF Section 13).
SHELL := /bin/bash
export PETPOP_MODE ?= mock
export PETPOP_MOCK_SPEED ?= 0.1
PY ?= .venv/bin/python
KIOSK := apps/kiosk
export PYTHONPATH := $(CURDIR):$(CURDIR)/mock-server

.PHONY: help setup dev mock api worker kiosk test test-py test-web openapi client proxies fixtures tiles \
        regress up down models gate-0 gate-1 gate-2 gate-3 gate-4 gate-5 gate-6 clean

help:
	@grep -E '^[a-z0-9-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

setup: ## create .venv, install Python and kiosk dependencies
	uv venv .venv --python 3.12 -q || python3 -m venv .venv
	uv pip install --python $(PY) -q -e '.[dev]' || $(PY) -m pip install -e '.[dev]'
	cd $(KIOSK) && npm install --no-audit --no-fund

dev: ## API + worker + SPA (no Docker): http://127.0.0.1:5173
	scripts/dev.sh

mock: ## standalone mock server on :8000 (frozen contract)
	$(PY) -m mock_server --port 8000

api: ## backend API only on :8000
	$(PY) -m backend.api

worker: ## worker only
	$(PY) -m backend.worker

kiosk: ## SPA dev server on :5173 (proxies /api to :8000); VITE_MOCK=1 for no backend at all
	cd $(KIOSK) && npm run dev

test: test-py test-web ## all fast tests

test-py:
	PETPOP_MOCK_SPEED=0 $(PY) -m pytest

test-web:
	cd $(KIOSK) && npx vitest run && npx tsc -b --noEmit

openapi: ## regenerate data/schema/openapi.json and the TypeScript client
	$(PY) scripts/export_openapi.py
	cd $(KIOSK) && npm run -s gen:client

client:
	cd $(KIOSK) && npm run -s gen:client

proxies: ## rebuild the proxy base meshes (bpy)
	$(PY) scripts/make_proxy_base.py
	$(PY) scripts/check_base_mesh.py

fixtures: ## rebuild the fixture pack from the mock-mode pipeline
	$(PY) scripts/make_fixtures.py

tiles: ## re-render pattern and marking tiles from the base mesh
	$(PY) scripts/make_tiles.py

regress: ## run the 30-pet regression set and write tests/regression/metrics.md
	$(PY) scripts/regress.py

up: ## GPU host: full Docker Compose stack
	docker compose -f infra/docker-compose.yml --env-file .env up -d --build

down:
	docker compose -f infra/docker-compose.yml --env-file .env down

models: ## GPU host: download pinned weights and verify SHA256
	$(PY) scripts/models.py --dest $${PETPOP_MODELS:-/srv/models}

gate-0 gate-1 gate-2 gate-3 gate-4 gate-5 gate-6: ## run acceptance gate N
	scripts/gates/$@

clean:
	rm -rf var $(KIOSK)/dist $(KIOSK)/storybook-static $(KIOSK)/test-results
