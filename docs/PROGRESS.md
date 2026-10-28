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

- [ ] Kiosk shell: Vite + React 18 + TS + Tailwind + Framer Motion + Zustand, 1080x1920 portrait, scaled to the viewport, single origin
- [ ] Screen 1 Attract loop (turntable of six figurines, "Tap to make yours", captions)
- [ ] Screen 2 Species (two tiles, accent colour per species)
- [ ] Screen 3 Breed (searchable grid, on-screen keyboard, "Mixed / not sure", preset pre-fill)
- [ ] Screen 4 Build (all Section 4 selectors as swatches, tiles and chips; live 3D preview with morph targets and procedural material, labelled "preview")
- [ ] Screen 5 Brief (on-screen keyboard, example chips, `/spec/parse`, highlights changed selectors, "for flavour only" fallback)
- [ ] Screen 6 Name and generate (name, summary card, Generate, three-run session cap)
- [ ] Screen 7 Generating (WebSocket progress, real intermediate previews, queue position, failure and fallback states)
- [ ] Screen 8 Result (turntable, pinch zoom, textured/clay toggle, Tweak keeps the seed, QR, Send to print with ticket)
- [ ] Phone result page `/r/:token`
- [ ] Kiosk behaviour: 90 s idle then 15 s "Still there?" then wipe; "Back in a moment" offline overlay with auto-retry; hidden five-tap staff panel
- [ ] Pattern and marking tiles pre-rendered from the base mesh by a build script
- [ ] Storybook: a story for every screen, three visual directions as themes
- [ ] Playwright: a test for every screen plus the full walkthrough (gate-1)
- [ ] `scripts/gates/gate-1` passes; PR for M1

## S2 / M2: real backend, parametric path (`make gate-2`)

- [ ] `backend/api`: FastAPI, SQLite via SQLAlchemy (tables from Section 9), every route in openapi.json, signed URLs, SPA served from one origin, Prometheus `/metrics`
- [ ] Queue and events: local cross-process queue and event bus for `make dev`; Redis + arq implementation for `make up`
- [ ] `ArtefactStore`: local folder `var/artefacts/` and MinIO/S3 implementation
- [ ] `backend/worker`: StageRunner, `stage_a.py` to `stage_f.py` taking `(job_id, spec, manifest)`, resumable, per-stage timeouts, one retry, progress events
- [ ] Adapters with `PETPOP_MODE` switch: mock LLM (rule parser), `MockImageBackend`, `MockShapeBackend`; real Ollama and ComfyUI clients behind the same interfaces
- [ ] `backend/prompts`: Jinja templates and `compiler.py` (Section 7), vocabulary only, no raw user text
- [ ] `pipelines/blender/render_control.py`: depth and silhouette renders from five cameras
- [ ] `pipelines/blender/wrap.py`: morph, ICP align, landmark pull, shrinkwrap, corrective smooth, eye inserts, accessories, validation and fallback
- [ ] `pipelines/blender/bake.py`: albedo in the fixed UV layout, per-region colour correction, seam padding
- [ ] `pipelines/blender/export_print.py`: base disc, mandrel socket from `config/mandrel.json`, voxel remesh, decimate, min-wall check, 3MF + STL
- [ ] `pipelines/blender/paint_check.py`: free-space distance along normals, `paint_mask.png`
- [ ] Preview export: Draco GLB, `turntable.mp4`, `manifest.json`
- [ ] Accessory library `assets/accessories/` generated by script
- [ ] Fallbacks and fault injection (`PETPOP_FAIL_STAGE`), IoU confidence check
- [ ] Fulfil (print bundle to the fulfilment folder, ticket), QR result page, staff panel endpoints with token
- [ ] Real backend passes the identical contract test the mock server passes; fixture pack regenerated from the real pipeline
- [ ] Regression set `tests/regression/pets.json` (30 pets) and `make regress` metrics table
- [ ] `infra/`: docker-compose.yml, Dockerfiles, `.env.example`; `pipelines/comfy/` manifests (`models.yaml`, `requirements.txt`)
- [ ] `scripts/gates/gate-2` passes; PR for M2
- [ ] `docs/HANDOFF.md`: what the GPU host needs for S3

## Later stages (not started in the cloud)

- S3 GPU host bring-up (gates 3 to 5), S4 real assets, S5 kiosk hardening (gate 6)
