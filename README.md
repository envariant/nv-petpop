# PetPop

Touch-first kiosk that turns a description of a dog or cat into a chibi vinyl-collectible-style figurine:
a textured GLB preview, a watertight print mesh and a fixed-layout UV atlas for the inkjet painter. Two apps on
one core (BRIEF Section 17): **PetPop Kiosk** for customers (library mode: assemble, customise, order) and
**PetPop Studio** for staff (generate, curate, publish). The kiosk never depends on the GenAI host.
The spec is [docs/BRIEF.md](docs/BRIEF.md). The GenAI stages run on a remote host chosen by `GENAI_PROFILE`
(see [config/genai/](config/genai/README.md) and [docs/HANDOFF.md](docs/HANDOFF.md)). Progress is tracked in [docs/PROGRESS.md](docs/PROGRESS.md),
choices in [docs/DECISIONS.md](docs/DECISIONS.md), and the GPU bring-up in [docs/HANDOFF.md](docs/HANDOFF.md).

```bash
make setup          # .venv (Python 3.12) + npm workspaces (packages/*, apps/kiosk, apps/studio)
make dev            # API + studio and kiosk workers + both SPAs on CPU (GENAI_PROFILE=mock):
                    #   kiosk http://127.0.0.1:5173, studio http://127.0.0.1:5174/studio/ (logins operator,
                    #   curator, admin; password in var/.petpop_studio_password)
make mock           # standalone mock server on :8000 (the frozen contract)
make test           # Python and web tests
make gate-0         # acceptance gates 0..6 (3-6 print "SKIPPED (needs a GenAI host)" on the mock profile)
make smoke-stack    # build the Compose stack here, push one job through it, tear it down
make regress        # 30-pet regression set -> tests/regression/metrics.md
```

| Path | What |
| --- | --- |
| `apps/kiosk/` | customer SPA: library mode, kiosk behaviour, phone result page, Storybook, Playwright |
| `apps/studio/` | staff SPA: sign-in, Generate workspace, queue, Storybook, Playwright |
| `packages/core/` | `@petpop/core` (generated API client, PetSpec helpers) and `petpop_core` (schemas, vocab, breeds, parser, manifest, prompt compiler) |
| `packages/viewer/` | `@petpop/viewer`: three.js viewer, morph application, pattern material |
| `packages/ui/` | `@petpop/ui`: portrait frame, tiles, swatches, chips, on-screen keyboard, theme CSS |
| `packages/library/` | `petpop_library`: base-mesh geometry, accessories, colouring; delta extraction, QC, releases |
| `mock-server/` | standalone OpenAPI mock with scripted jobs |
| `backend/api/` | FastAPI app: contract routers (`/kiosk`, `/studio`), auth, DB, artefact store, queue/event bus |
| `backend/core/` | runtime settings and GenAI profiles |
| `backend/worker/` | workers for the `studio` and `kiosk` queues, StageRunner, `stage_a.py` to `stage_f.py`, adapters |
| `pipelines/blender/` | bpy scripts: control renders, wrap, bake, print export, paint check, preview |
| `pipelines/comfy/` | workflow manifests for the GPU host (S3) |
| `assets/` | proxy base meshes, accessory library, selector tiles, LoRA tooling |
| `data/` | JSON Schemas, vocab, OpenAPI, breed presets |
| `fixtures/pets/` | 10-pet fixture pack produced by the pipeline |
| `config/genai/` | GenAI profiles (`mock`, `mac-m4pro`, `nvidia-24gb`): every model, host and timing |
| `mac/` | Mac GenAI host kit: setup, launchd units, shape server, tunnel, runbook |
| `infra/` | Docker Compose (stack + NVIDIA override) and Dockerfiles |

The Blender stages run under a Python 3.11 interpreter with the `bpy` wheel (`PETPOP_BPY_PYTHON`,
default `/opt/bpy/bin/python`). Without it the pipeline falls back to a trimesh stand-in, marked
`fidelity: low`.
