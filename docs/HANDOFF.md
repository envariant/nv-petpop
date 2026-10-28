# Handoff: what the GPU host needs for S3

S0 to S2 are done and gated in the cloud (`make gate-0`, `gate-1`, `gate-2` all pass). The latest
regression table is in `tests/regression/metrics.md` (mock mode: 30/30 complete, all watertight, all wraps
valid, one topology per species). The whole product runs on
CPU in mock mode: kiosk, API, worker, Blender wrap/bake/export/paint check, fixtures and the regression
set. S3 swaps the three GPU services in behind the existing adapters, so the API, worker stages and SPA do
not change. This page lists what that needs, in order.

## 1. Hardware and OS

- 1x 24 GB NVIDIA GPU (RTX 4090 or L4 class), 16-core CPU, 64 GB RAM, 500 GB NVMe (BRIEF Section 9).
- Ubuntu 22.04/24.04, a recent NVIDIA driver, Docker Engine with Compose v2, and the NVIDIA Container
  Toolkit (`docker run --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` must work).
- Outbound HTTPS to huggingface.co, github.com, registry.ollama.ai and Docker Hub during setup only.
- A LAN address for the kiosk thin client and phones (QR links): set `PETPOP_PUBLIC_URL`.

## 2. Secrets and configuration (`.env`, never committed)

Copy `.env.example` to `.env` and fill:

| Variable | Notes |
| --- | --- |
| `PETPOP_MODE=real` | switches all four adapters to the GPU services |
| `PETPOP_SECRET` | 32+ random bytes; signs artefact URLs and the 7-day result links |
| `PETPOP_STAFF_TOKEN` | staff panel token (LAN only) |
| `POSTGRES_PASSWORD`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | for the postgres and minio containers |
| `PETPOP_PUBLIC_URL` | e.g. `http://192.168.1.20:8000`, used in QR links |
| `PETPOP_FULFIL_DIR` | the folder the print station watches (bind-mount it into `api`) |
| `PETPOP_MODELS` | weights root, default `/srv/models` (read-only mount) |
| `PETPOP_COMFY_RESTART_CMD` | optional, e.g. `docker restart petpop-comfyui-1`, used by the 30 s watchdog |

## 3. Pins that must be filled in on the box (S3 work, then committed)

1. **ComfyUI commit**: `ARG COMFY_COMMIT` in `infra/Dockerfile.comfyui`.
2. **Custom node packs**: the commit column in `pipelines/comfy/requirements.txt` (Hunyuan3DWrapper,
   IPAdapter_plus, controlnet_aux, BiRefNet, MVAdapter). `install_nodes.sh` refuses unpinned entries.
3. **Model weights**: `sha256` for every entry in `pipelines/comfy/models.yaml`. Also check each URL
   against its model card. The URLs are best guesses from the brief and the Hugging Face layouts I know,
   and none were downloaded here. `make models` refuses entries without a hash and verifies every file.
4. **Ollama**: `docker compose exec ollama ollama pull qwen2.5:7b-instruct-q4_K_M`.
5. **Licences**: read the Tencent Hunyuan community licence terms before any commercial use (`LICENSES.md`).

## 4. The six ComfyUI workflows (do not exist yet)

Build them in the ComfyUI editor, export in API format to `pipelines/comfy/`, and add `"meta": {"version": "1"}`.
The worker fills inputs **by node title**, so each workflow must expose exactly the titled inputs and
outputs in `pipelines/comfy/README.md`. In summary: `01_concept_front.json` (B),
`02_views_ipadapter.json` and `02b_views_mvadapter.json` (C), `03_shape_hy2mv.json` (D),
`03b_shape_hy21_single.json` (D fallback) and `04_texture_hy_paint.json` (texture). The adapters that
call them are in `backend/worker/backends/real/comfy.py`. They are written against the brief but have
never run against a live ComfyUI, so expect to adjust output parsing (`/history` keys for GLB outputs)
and the `normalise_glb` axis handling on first contact.

Depth and silhouette inputs already exist. The `control` stage renders 16-bit depth for the five cameras
from the morphed base mesh, and the worker uploads them through `/upload/image`.

## 5. Bring-up order (one adapter at a time)

`PETPOP_ADAPTERS` overrides single adapters, so the rest stay on their mocks. You can also run from the
cloud session with `COMFY_URL` and `OLLAMA_URL` tunnelled to the box.

1. `make up` and `make models`. Then `curl $COMFY_URL/system_stats` and `curl $OLLAMA_URL/api/tags`.
2. Stage A: `PETPOP_ADAPTERS=parser=real`. `/spec/parse` must answer in under 3 s, and it falls back to the rules parser if Ollama is down.
3. Stage B: `PETPOP_ADAPTERS=parser=real,image=real`. Run only the concept graph first (Stage C keeps using the mock until `02_*` exists).
4. Stage C: add the views graph, then compare IP-Adapter against MV-Adapter on the 30-pet set by Stage D confidence.
5. Stage D: `shape=real`. Confirm `/free` with `unload_models` runs between C and D (it is in `ComfyShapeBackend.multiview`), calibrate the 0.85 IoU threshold, and exercise the single-view fallback.
6. Texture: `texture=real` (Hunyuan3D-Paint on the wrapped OBJ with the fixed UVs). Per-region colour correction runs automatically in real mode.
7. All real: `PETPOP_MODE=real` with no overrides.

## 6. Gates 3 to 5

In mock mode these print `SKIPPED (needs GPU)`. With `PETPOP_MODE=real` each one checks service health,
runs the contract test against the backend with the real adapters (`tests/contract -k backend`), and runs
`scripts/regress.py --gate N`. The thresholds are in `GATES` in `scripts/regress.py`. Gate 4 adds mean
IoU >= 0.85. Gate 5 adds p50 <= 150 s and max <= 240 s per job on a warm GPU.

Use `PETPOP_PROFILE=full` (the default in real mode) for the brief's resolutions: 1024/768 px, 2048 albedo,
0.15 mm voxels and 250 k print tris. Stage timeouts are the brief's values in real mode
(A 10, B 60, C 90, D 150, E 90, F 120 s). The Blender stages (wrap, print remesh, turntable) run in the
worker container on CUDA. Time them first: the 0.15 mm voxel remesh is the most likely stage to blow
F's 120 s budget.

## 7. Known gaps to close in S3 and S4

- **Base meshes are proxies** (`assets/base/*/`, built by `scripts/make_proxy_base.py`). S4 replaces them
  with the hand-built meshes from Section 10, then: `scripts/check_base_mesh.py --strict`, `make tiles`,
  `make fixtures`. Spec gap to settle: the cat morph list (DECISIONS 6).
- **Style LoRA** (`petpop_style`): `assets/lora/make_training_set.py` and `kohya_petpop_style.toml` are
  ready but were not run. Run them on the real meshes in S4.
- **NSFW classifier** on concepts (Section 11) is not implemented. Add it to Stage B on the GPU host
  (a false positive just regenerates).
- **VRAM peak** per stage (`stage_timings.vram_peak_mb`) has a column but is not filled. Read it from
  ComfyUI `/system_stats` around each call.
- **Real adapters are untested**: `comfy.py`, `ollama.py` and the `RedisBus`/arq and `S3Store` paths
  have never run. `make dev` uses SQLite, the local store and the local bus.
- **Mandrel geometry** in `config/mandrel.json` is a placeholder until the painter fixture is measured
  (Section 14).
- **Kiosk hardening** (S5): Chromium `--kiosk` launch, the browser/API restart watchdog and the 5-person
  touch review are not done. The visual direction (candy, studio or toybox) is still to be picked.

## 8. Useful commands

```bash
make up                         # compose stack (api, worker, comfyui, ollama, postgres, redis, minio)
make models                     # pinned weights + SHA256 verification
make gate-3                     # then gate-4, gate-5 (real mode)
make regress                    # 30-pet metrics table -> tests/regression/metrics.md
PETPOP_FAIL_STAGE=D make regress  # fallbacks by fault injection
```
