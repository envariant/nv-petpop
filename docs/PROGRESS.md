# PetPop PoC progress (S0 to S2)

Ordered checklist of every S0, S1 and S2 deliverable in BRIEF.md Sections 12 and 13.
Tick an item only when `make test` and that milestone's gate pass. S3 and later are listed at the end
for reference only and are never started in a cloud session.

## S0 / M0: contract and mock server (`make gate-0`)

- [x] Repo scaffold: monorepo layout from Section 12, Makefile, pyproject, `.env.example`, `.gitignore`, LICENSES.md
- [x] `data/schema/petspec.schema.json`: closed enumerations for every PetSpec field (Section 3)
- [x] `data/schema/vocab.json`: every enumeration value has a prompt phrase and a morph mapping; schema test enforces it
- [x] `data/schema/manifest.schema.json`: per-job manifest (files, stage, timings, seeds, workflow versions, fidelity)
- [x] `data/breeds/dog.json` (~60) and `data/breeds/cat.json` (~25) presets with `prompt_hint`, validated against the schema
- [x] Shared contract models + rule-based Stage A parser over `vocab.json` (merge order preset, taps, patch)
- [x] Proxy base meshes: `scripts/make_proxy_base.py` (bpy, primitives, QuadriFlow, Smart UV, vertex groups, 14 landmarks, shape keys) and `scripts/check_base_mesh.py` (pulled forward from S2: the fixtures and the live preview need them)
- [x] Fixture pack: 10 PetSpecs with mock outputs under `fixtures/pets/`, manifests valid against the schema
- [x] `mock-server/`: standalone FastAPI, no DB/queue/Blender; breeds over real presets, `/spec/parse` with the rule parser, scripted jobs (`mock-server/scripts/*.json`: normal, slow-queue, failed-stage, fallback-figurine)
- [x] `data/schema/openapi.json` committed from the mock server; drift test
- [x] TypeScript client generated from the OpenAPI (`apps/kiosk/src/api/`)
- [x] MSW handlers (`VITE_MOCK=1`) with a timer-driven fake job, covering every OpenAPI path
- [x] Contract test: every endpoint and every mock script validated against openapi.json, manifests against manifest.schema.json
- [x] `scripts/gates/gate-0` passes; gates 3 to 5 print `SKIPPED (needs GPU)`; PR for M0

## S1 / M1: front end in full (`make gate-1`)

- [x] Kiosk shell: Vite + React 18 + TS + Tailwind + Framer Motion + Zustand, 1080x1920 portrait, scaled to the viewport, single origin
- [x] Screen 1 Attract loop (turntable of six figurines, "Tap to make yours", captions)
- [x] Screen 2 Species (two tiles, accent colour per species)
- [x] Screen 3 Breed (searchable grid, on-screen keyboard, "Mixed / not sure", preset pre-fill)
- [x] Screen 4 Build (all Section 4 selectors as swatches, tiles and chips; live 3D preview with morph targets and procedural material, labelled "preview")
- [x] Screen 5 Brief (on-screen keyboard, example chips, `/spec/parse`, highlights changed selectors, "for flavour only" fallback)
- [x] Screen 6 Name and generate (name, summary card, Generate, three-run session cap)
- [x] Screen 7 Generating (WebSocket progress, real intermediate previews, queue position, failure and fallback states)
- [x] Screen 8 Result (turntable, pinch zoom, textured/clay toggle, Tweak keeps the seed, QR, Send to print with ticket)
- [x] Phone result page `/r/:token`
- [x] Kiosk behaviour: 90 s idle then 15 s "Still there?" then wipe; "Back in a moment" offline overlay with auto-retry; hidden five-tap staff panel
- [x] Pattern and marking tiles pre-rendered from the base mesh by a build script
- [x] Storybook: a story for every screen, three visual directions as themes
- [x] Playwright: a test for every screen plus the full walkthrough (gate-1)
- [x] `scripts/gates/gate-1` passes; PR for M1 (the 5-person touch review on the kiosk screen is Nishant's step)

## S2 / M2: real backend, parametric path (`make gate-2`)

- [x] `backend/api`: FastAPI, SQLite via SQLAlchemy (tables from Section 9), every route in openapi.json, signed URLs, SPA served from one origin, Prometheus `/metrics`
- [x] Queue and events: local cross-process queue and event bus for `make dev`; Redis + arq implementation for `make up`
- [x] `ArtefactStore`: local folder `var/artefacts/` and MinIO/S3 implementation
- [x] `backend/worker`: StageRunner, `stage_a.py` to `stage_f.py` taking `(job_id, spec, manifest)`, resumable, per-stage timeouts, one retry, progress events
- [x] Adapters with `PETPOP_MODE` switch: mock LLM (rule parser), `MockImageBackend`, `MockShapeBackend`; real Ollama and ComfyUI clients behind the same interfaces
- [x] `backend/prompts`: Jinja templates and `compiler.py` (Section 7), vocabulary only, no raw user text
- [x] `pipelines/blender/render_control.py`: depth and silhouette renders from five cameras
- [x] `pipelines/blender/wrap.py`: morph, ICP align, landmark pull, shrinkwrap, corrective smooth, eye inserts, accessories, validation and fallback
- [x] `pipelines/blender/bake.py`: albedo in the fixed UV layout, per-region colour correction, seam padding
- [x] `pipelines/blender/export_print.py`: base disc, mandrel socket from `config/mandrel.json`, voxel remesh, decimate, min-wall check, 3MF + STL
- [x] `pipelines/blender/paint_check.py`: free-space distance along normals, `paint_mask.png`
- [x] Preview export: Draco GLB, `turntable.mp4`, `manifest.json`
- [x] Accessory library `assets/accessories/` generated by script
- [x] Fallbacks and fault injection (`PETPOP_FAIL_STAGE`), IoU confidence check
- [x] Fulfil (print bundle to the fulfilment folder, ticket), QR result page, staff panel endpoints with token
- [x] Real backend passes the identical contract test the mock server passes; fixture pack regenerated from the real pipeline
- [x] Regression set `tests/regression/pets.json` (30 pets) and `make regress` metrics table
- [x] `infra/`: docker-compose.yml, Dockerfiles, `.env.example`; `pipelines/comfy/` manifests (`models.yaml`, `requirements.txt`)
- [x] `scripts/gates/gate-2` passes; PR for M2
- [x] `docs/HANDOFF.md`: what the GPU host needs for S3
- [x] Extra: LoRA training-set script and Kohya config (`assets/lora/`), per-adapter override `PETPOP_ADAPTERS` for the S3 bring-up

## M2.5: host-agnostic GenAI (branch `poc`)

- [x] Profile layer: `config/genai/{mock,mac-m4pro,nvidia-24gb}.yaml` + schema; `GENAI_PROFILE` selects; endpoints, model ids, quality, residency, timeouts and expected timings out of code; worker names no model or host (test)
- [x] Manifest 1.1 records the profile, adapters and model ids with pins; gates 3 to 6 print `SKIPPED (needs a GenAI host)` on mock
- [x] `mac-m4pro`: ComfyUI MPS (SDXL fp16, depth ControlNet, IP-Adapter Plus), Hunyuan3D-2.1 via the MPS fork on a shape server (octree 256 / 30 steps, later 192), Ollama 7B, one resident model, 8-12 min expected (later 12-16), latency waived
- [x] `TEXTURE_BACKEND=projection` (Blender) default on every profile; `hy_paint` optional and NVIDIA-only
- [x] `nvidia-24gb`: Hunyuan3D-2mv 384 / 50, fp8 allowed, `hy_paint` optional, 4-minute target enforced
- [x] Six ComfyUI workflows authored in API format by script, model names bound from the profile, `meta.validated: false`
- [x] `mac/`: setup script, launchd units for the three services, `tunnel.sh` (token proxy + Cloudflare), runbook, `make -C mac models` writing SHA256 pins
- [x] `make up` smoke-tested here on the mock profile without GPU services: Compose, Postgres, Redis/arq, MinIO (`scripts/smoke_stack.sh`); fixes: arq enqueue from the event loop, MinIO image, compose healthchecks
- [x] Full pipeline on `mac-m4pro` and `nvidia-24gb` against a fake GenAI host (real adapters and workflows)
- [x] `docs/HANDOFF.md` for the Mac host; `CLAUDE.md` and BRIEF Section 13 updated; PR opened

### M2.5 follow-up: deterministic Mac setup

- [x] Tools pinned with hashes (`mac/tools.lock`: uv, Ollama, Caddy, cloudflared, CPython 3.11.17); no Homebrew
- [x] Python packages hash-locked for macOS arm64, wheels only, reproducible (`mac/locks/*.txt` from `mac/lock.sh`); `uv pip sync --require-hashes`
- [x] Tencent's Hunyuan3D-2.1 code pinned to a commit; the fork's `install.sh` (HEAD clone, unpinned packages) no longer run
- [x] Weight pins committed from Hugging Face metadata (`scripts/models.py --pin --from-hub`, `models.lock.json`); `make -C mac models` fetches and checks every file
- [x] Ollama model pinned by manifest digest and checked after the pull
- [x] Shape server fixed to load like the fork (import paths, `backend` + `compat_patches` before torch, local weights only, offline); stub test
- [x] `mac-m4pro` octree 192 and expected timings from the fork's M4 Pro benchmark (12-16 min per pet)

## Later stages (not started in the cloud)

- S3 GenAI host bring-up on the Mac (gates 3 to 5 with `GENAI_PROFILE=mac-m4pro`), later the NVIDIA box; S4 real assets; S5 kiosk hardening (gate 6)
