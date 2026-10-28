# PetPop

Touch-first kiosk that turns a description of a dog or cat into a chibi vinyl-collectible-style figurine:
a textured GLB preview, a watertight print mesh and a fixed-layout UV atlas for the inkjet painter.
The spec is [docs/BRIEF.md](docs/BRIEF.md). Progress is tracked in [docs/PROGRESS.md](docs/PROGRESS.md),
choices in [docs/DECISIONS.md](docs/DECISIONS.md), and the GPU bring-up in [docs/HANDOFF.md](docs/HANDOFF.md).

```bash
make setup          # .venv (Python 3.12) + kiosk npm install
make dev            # API + worker + SPA on CPU (PETPOP_MODE=mock): http://127.0.0.1:5173
make mock           # standalone mock server on :8000 (the frozen contract)
make test           # Python and web tests
make gate-0         # acceptance gates 0..6 (3-5 print "SKIPPED (needs GPU)" in mock mode)
make regress        # 30-pet regression set -> tests/regression/metrics.md
```

| Path | What |
| --- | --- |
| `apps/kiosk/` | React SPA (Vite, TS, Tailwind, r3f), Storybook, Playwright |
| `mock-server/` | standalone OpenAPI mock with scripted jobs |
| `backend/core/` | contract router, schemas, parser, spec merge, mesh utilities |
| `backend/api/` | FastAPI app, DB, artefact store, queue/event bus |
| `backend/worker/` | StageRunner, `stage_a.py` to `stage_f.py`, mock and real adapters |
| `backend/prompts/` | Jinja templates and the prompt compiler |
| `pipelines/blender/` | bpy scripts: control renders, wrap, bake, print export, paint check, preview |
| `pipelines/comfy/` | workflow manifests for the GPU host (S3) |
| `assets/` | proxy base meshes, accessory library, selector tiles, LoRA tooling |
| `data/` | JSON Schemas, vocab, OpenAPI, breed presets |
| `fixtures/pets/` | 10-pet fixture pack produced by the pipeline |
| `infra/` | Docker Compose and Dockerfiles for the GPU host |

The Blender stages run under a Python 3.11 interpreter with the `bpy` wheel (`PETPOP_BPY_PYTHON`,
default `/opt/bpy/bin/python`). Without it the pipeline falls back to a trimesh stand-in, marked
`fidelity: low`.
