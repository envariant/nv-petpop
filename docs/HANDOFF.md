# Handoff: S3 on a remote GenAI host (Mac first)

Since M2.5 the backend is host-agnostic. Everything about a GenAI host (endpoints, model ids, quality,
residency, stage timeouts, expected timings) lives in `config/genai/<profile>.yaml`, selected by
`GENAI_PROFILE`. The worker never names a model or a host, and a test enforces that.

| Profile | Where the GenAI runs | Shape model | Texture | Latency |
| --- | --- | --- | --- | --- |
| `mock` (default) | nowhere: CPU stand-ins in the VM | morphed base mesh + noise | projection | n/a |
| `mac-m4pro` | Apple Silicon M4 Pro 24 GB, MPS, via tunnel | Hunyuan3D-2mv full via ComfyUI, octree 256 / 50 steps; Hunyuan3D-2.1 shape server (octree 192) as fallback and fast path | projection | none (library ~30 min, fast ~15 min) |
| `tripo` | Tripo3D apiv3 (commercial API, `TRIPO_API_KEY`; docs/PROVIDERS.md) | Tripo image-to-model with its own texture, transferred onto the base UVs | transfer | provider task time |
| `nvidia-24gb` | 24 GB NVIDIA box, CUDA | Hunyuan3D-2mv, octree 384 / 50 steps | projection, `hy_paint` optional | 4 min enforced |

The PetPop backend (API, worker, Blender wrap/bake/export) keeps running in the cloud VM. Only ComfyUI, the
shape server and Ollama run on the Mac.

## What you run, in order

### On the Mac (details and troubleshooting in [mac/RUNBOOK.md](../mac/RUNBOOK.md))

1. Clone the repo, then check out `poc`:

   ```bash
   git clone https://github.com/envariant/nv-petpop && cd nv-petpop && git checkout poc
   ```

2. Install the Xcode Command Line Tools if the Mac lacks them (`xcode-select --install`). Nothing else is
   needed beforehand; there is no Homebrew step.

3. Install the pinned tools, Python, venvs and code, pull the Ollama model, write the secrets file, and load the
   three launchd units. Every download is checked against a hash committed in this repo:

   ```bash
   make -C mac setup
   ```

4. Fetch about 21 GB of weights. Each file must match the SHA256 in `pipelines/comfy/models.lock.json`, or
   it is deleted and the command fails. The pins are already committed, so there is nothing to commit after:

   ```bash
   make -C mac models
   ```

5. Start the services and probe them locally:

   ```bash
   make -C mac start && make -C mac check
   ```

6. Open the tunnel. This starts the token-checking proxy and the Cloudflare tunnel, and prints the URLs. For a
   stable hostname from the start, set up the named tunnel first (once, any time after step 3; RUNBOOK §4): a
   free Cloudflare account and a domain on Cloudflare, then `cloudflared tunnel login`, `tunnel create` and
   `tunnel route dns`, and `CF_TUNNEL` / `CF_HOSTNAME` in `~/petpop-genai/genai.env`. Without it you get a quick
   tunnel, no account needed, on a hostname that changes at every start.

   ```bash
   make -C mac tunnel
   ```

### Getting the tunnel URL into the cloud VM

`mac/tunnel.sh` prints six values. Set them as environment variables in the cloud environment
(environment settings, then Edit, then Environment variables), then start a new session:

| Variable | Value |
| --- | --- |
| `GENAI_PROFILE` | `mac-m4pro` |
| `COMFY_URL` | `https://<tunnel host>/comfy` |
| `SHAPE_URL` | `https://<tunnel host>/shape` |
| `OLLAMA_URL` | `https://<tunnel host>/ollama` |
| `EMBED_URL` | `https://<tunnel host>/embed` (image embeddings; served by the shape server's process) |
| `GENAI_TOKEN` | the value in `~/petpop-genai/genai.env` on the Mac (copy it; never paste it into a chat) |

The adapters read these through the profile (`config/genai/mac-m4pro.yaml` names `COMFY_URL`, `SHAPE_URL`, `EMBED_URL`
and `OLLAMA_URL` as the env vars for its services) and send `Authorization: Bearer $GENAI_TOKEN` on every
call. The proxy on the Mac answers 401 without it.

A named tunnel gives a stable hostname, so these are set once. A quick tunnel's hostname changes every time
`tunnel.sh` restarts, so the three URLs must be updated each time. Either way, Cloudflare cuts off any request
that takes more than about 100 s, so the shape server queues each mesh as a job the worker polls (as ComfyUI does
with prompts); no request waits on a model. If
the environment's network access is Limited, add the tunnel host (`trycloudflare.com` or your hostname) to
Allowed domains. This VM reached `trycloudflare.com` on 2026-10-28.

### Back in the cloud session (S3, driven by Claude Code)

1. `python scripts/genai_check.py`: all three services return OK through the tunnel.
2. Bring the stages up one at a time with `PETPOP_ADAPTERS` forcing the rest to mock. The order and each
   step's check:
   - Stage A: `/spec/parse` answers in under 3 s on Ollama.
   - Stage B: `PETPOP_ADAPTERS=shape=mock` keeps D on the mock.
   - Stage C: the four views.
   - Stage D: the shape server, and calibrate the 0.85 IoU threshold for single-view shapes.
3. Run the pipeline in the VM with `make dev`, or `make regress` for the 30-pet set, with
   `GENAI_PROFILE=mac-m4pro`. Use `make dev` rather than `make up` here: the VM's TLS-inspecting proxy is
   trusted by host processes but not by containers.
4. Gates 3 to 6 run on the profile: `make gate-3` ... `make gate-6`. On `mac-m4pro` gate 5 waives the latency
   target, and the regression set takes 6 to 8 hours (30 x 12 to 16 min). Run it overnight, or use
   `--limit` to subset.
5. When a workflow first runs cleanly, set `validated: true` (with the date and host) in
   `scripts/make_comfy_workflows.py`, then run `make workflows`.

## What is ready and what is not

**Proven in the VM**
- `make up` on the mock profile builds and runs api, worker on arq, Postgres, Redis and MinIO.
  `scripts/smoke_stack.sh` pushes one job through all of them and tears them down.
- The full pipeline ran on `mac-m4pro` and `nvidia-24gb` against a fake GenAI host
  (`tests/pipeline/test_genai_hosts.py`). That covers the real ComfyUI, shape-server and Ollama adapters,
  the generated workflows, the residency rules, the bearer token, and the manifest's `genai` block.
- The Mac proxy config passes `caddy validate`. A live check gave 401 without the token, 200 with it, and
  404 for unknown paths.

**Not yet run anywhere**
- **Real models.** None has executed. All six workflows are `meta.validated: false`.
- **Workflow node definitions.** Node class and input names were checked against each pack's source at the
  pinned commit. The output handling (`/history` keys, especially SaveGLB's `3d` list) is from source too,
  but unverified.
- **Mac scripts.** `mac/setup.sh` and the launchd units are written for macOS and were not executed (the VM is
  Linux). The plists parse and the shell scripts pass `bash -n`.
- **Shape server.** `mac/shape_server/server.py` now loads the model the way the fork's own app does: the
  fork's `backend` and `compat_patches` before torch, Tencent's code from `$HY3D_DIR/Hunyuan3D-2.1`, the
  fp16 `.ckpt` from the local weights only. `tests/unit/test_mac_host.py` checks that wiring against stubs;
  the real model has not run.
- **The hy3dmlx MLX port.** Its weights are on Hugging Face (`AgenticVibes/hy3dmlx-shape-v2.1`), but its
  loader code (`github.com/AgenticVibes/hy3dmlx`) is not public and it is not on PyPI. Its published timings
  (12.9 s per step on an M3 Ultra) are also slower than the MPS fork's (7.6 s per step on an M4 Pro), so the
  profile keeps the fork. Another engine can be added under `shape.server` in the profile.

**Pins (the Mac setup is deterministic)**
- **Weights:** every file's SHA256 is committed (`models.yaml` + `models.lock.json`), written from Hugging
  Face's metadata at each pinned revision without downloading anything. Only the untrained S4 LoRA is `TODO`.
- **Code:** ComfyUI, IP-Adapter Plus, the MPS fork and Tencent's Hunyuan3D-2.1 are pinned to commits.
- **Python packages:** every package in the three Mac venvs is `==`-pinned with hashes, wheels only
  (`mac/locks/`, regenerated reproducibly by `mac/lock.sh`).
- **Tools and Python:** uv, Ollama, Caddy, cloudflared and CPython 3.11.17 are pinned releases with hashes
  (`mac/tools.lock`).
- **Ollama model:** the manifest digest is pinned and checked after the pull.
- The fork's `install.sh` is not used: it clones Tencent's repo at HEAD and installs unpinned packages.

**Still open from earlier stages**
- **Proxy base meshes and LoRA.** The base meshes are proxies and the style LoRA is untrained (S4).
- **NSFW classifier.** Not built.
- **VRAM peak column.** `stage_timings.vram_peak_mb` exists but is never filled.
- **Mandrel dimensions.** Still placeholders.
- **Kiosk hardening.** S5 work, not started.
- **Hunyuan3D licence.** It is not granted in the EU, the UK or South Korea; check before any commercial use.

## Later: the NVIDIA box

`GENAI_PROFILE=nvidia-24gb make up` adds `infra/docker-compose.nvidia.yml`, which brings ComfyUI (with the
Hunyuan3D wrapper and MV-Adapter node packs) and Ollama up on the local GPU and reserves the GPU for the
worker. Fetch its weights with `make models GENAI_PROFILE=nvidia-24gb` (checked against the same lock), then run
gates 3 to 6 with the 4-minute target enforced. To opt in to Hunyuan3D-Paint, set `TEXTURE_BACKEND=hy_paint`.
