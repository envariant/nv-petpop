# GenAI profiles

One YAML file per GenAI host. `GENAI_PROFILE` selects one (default `mock`), and it is the only place that
names a model, a host, a quality preset, a residency rule, a stage timeout or an expected timing. The
worker reads it through `backend/core/genai.py`. `tests/unit/test_host_agnostic.py` fails if the worker
code names a model, host, port or workflow file.

| Key | Meaning |
| --- | --- |
| `mode` | `mock` (CPU stand-ins) or `real` |
| `quality.presets` / `quality.default` | render sizes, samples, albedo, voxel size, print tris; `PETPOP_QUALITY` picks a preset |
| `timeouts_s` | hard per-stage timeouts (the job fails with the stage name) |
| `expected_s` | expected per-stage seconds and the per-pet range; slower stages are logged |
| `latency` | `target_s` and whether gate 5 enforces it |
| `residency` | `free_comfy_after_call`, `free_comfy_before`, `ollama_keep_alive_s`, `shape_unload_after_call` |
| `services` | `{env, default}` per service; the env var (e.g. `COMFY_URL`) wins; `auth_token_env` names the bearer-token variable |
| `parser` / `image` / `shape` / `texture` | backend per adapter plus its models, workflows and parameters |
| `gates` | IoU and latency thresholds for gates 4 and 5 |

Overrides: `TEXTURE_BACKEND` (projection, flat or hy_paint, where `texture.allowed` permits it) and
`PETPOP_ADAPTERS=shape=mock,...` during a host bring-up. Every job records the profile, its version and
hash, the adapters and every model id (with pins from `pipelines/comfy/models.yaml`) in
`manifest.json` under `genai`. Profiles are validated against `data/schema/genai-profile.schema.json`.
