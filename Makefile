# PetPop PoC. GENAI_PROFILE=mock is the default everywhere (config/genai/<profile>.yaml; BRIEF Section 13).
SHELL := /bin/bash
export GENAI_PROFILE ?= mock
export PETPOP_MOCK_SPEED ?= 0.1
PY ?= .venv/bin/python
KIOSK := apps/kiosk
export PYTHONPATH := $(CURDIR):$(CURDIR)/mock-server

.PHONY: help setup dev mock api worker kiosk test test-py test-web openapi client proxies fixtures tiles \
        regress up down smoke-stack workflows models gate-0 gate-1 gate-2 gate-3 gate-4 gate-5 gate-6 clean

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

workflows: ## regenerate the six ComfyUI workflow JSONs (node ids are generated, never hand-edited)
	$(PY) scripts/make_comfy_workflows.py

tiles: ## re-render pattern and marking tiles from the base mesh
	$(PY) scripts/make_tiles.py

regress: ## run the 30-pet regression set and write tests/regression/metrics.md
	$(PY) scripts/regress.py

COMPOSE_FILES := -f infra/docker-compose.yml $(if $(filter nvidia-24gb,$(GENAI_PROFILE)),-f infra/docker-compose.nvidia.yml)
ENV_FILE ?= .env
COMPOSE := PETPOP_ENV_FILE=../$(ENV_FILE) docker compose $(COMPOSE_FILES) --env-file $(ENV_FILE)

up: ## Docker Compose stack for GENAI_PROFILE (api, worker/arq, postgres, redis, minio [+ comfyui, ollama on nvidia])
	$(COMPOSE) up -d --build --wait

down:
	$(COMPOSE) down

smoke-stack: ## build and run the stack here on the mock profile, push one job through it, tear it down
	scripts/smoke_stack.sh

models: ## NVIDIA host: verify pinned weights (the Mac uses make -C mac models)
	$(PY) scripts/models.py --verify --dest $${PETPOP_MODELS:-/srv/models} --profile $(GENAI_PROFILE)

gate-0 gate-1 gate-2 gate-3 gate-4 gate-5 gate-6: ## run acceptance gate N
	scripts/gates/$@

clean:
	rm -rf var $(KIOSK)/dist $(KIOSK)/storybook-static $(KIOSK)/test-results
