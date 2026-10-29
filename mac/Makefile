# Mac GenAI host (profile mac-m4pro). Run from the repo root: make -C mac <target>
SHELL := /bin/bash
REPO := $(abspath ..)
PETPOP_GENAI ?= $(HOME)/petpop-genai
PETPOP_MODELS ?= $(HOME)/petpop-models
TOOLS_PY := $(PETPOP_GENAI)/venvs/tools/bin/python
export GENAI_PROFILE := mac-m4pro

.PHONY: setup lock models verify start stop restart status logs tunnel check

setup:   ## install the pinned tools, Python, venvs and code; load the launchd units
	$(REPO)/mac/setup.sh

lock:    ## regenerate mac/locks/*.txt (needs uv; also runs in the cloud VM); commit the result
	PATH="$(PETPOP_GENAI)/bin:$$PATH" $(REPO)/mac/lock.sh

models:  ## fetch the mac-m4pro weights; every file must match pipelines/comfy/models.lock.json
	cd $(REPO) && $(TOOLS_PY) scripts/models.py --fetch --dest $(PETPOP_MODELS) --profile mac-m4pro

verify:  ## re-hash the downloaded weights against the committed pins
	cd $(REPO) && $(TOOLS_PY) scripts/models.py --verify --dest $(PETPOP_MODELS) --profile mac-m4pro

start:
	for u in comfyui shape ollama; do launchctl kickstart -k gui/$$(id -u)/com.petpop.$$u; done

stop:
	for u in comfyui shape ollama; do launchctl kill TERM gui/$$(id -u)/com.petpop.$$u || true; done

restart: start

status:
	@for u in comfyui shape ollama; do launchctl print gui/$$(id -u)/com.petpop.$$u 2>/dev/null | grep -E "^\s*(state|pid) =" | tr -s ' ' | sed "s/^/$$u: /"; done

logs:
	tail -n 40 -f $(PETPOP_GENAI)/logs/*.log

check:   ## probe the three services locally (no tunnel)
	cd $(REPO) && COMFY_URL=http://127.0.0.1:8188 SHAPE_URL=http://127.0.0.1:8190 OLLAMA_URL=http://127.0.0.1:11434 \
		$(TOOLS_PY) scripts/genai_check.py

tunnel:  ## authenticating proxy + Cloudflare tunnel; prints the URLs for the cloud environment
	$(REPO)/mac/tunnel.sh
