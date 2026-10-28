# Handoff: S3 on a remote GenAI host (Mac first)

Since M2.5 the backend is host-agnostic. Everything about a GenAI host (endpoints, model ids, quality,
residency, stage timeouts, expected timings) lives in `config/genai/<profile>.yaml`, selected by
`GENAI_PROFILE`. The worker never names a model or a host, and a test enforces that.

| Profile | Where the GenAI runs | Shape model | Texture | Latency |
| --- | --- | --- | --- | --- |
| `mock` (default) | nowhere: CPU stand-ins in the VM | morphed base mesh + noise | projection | n/a |
| `mac-m4pro` | Apple Silicon M4 Pro 24 GB, MPS, via tunnel | Hunyuan3D-2.1 (MPS fork), octree 256 / 30 steps | projection | waived (8 to 12 min) |
| `nvidia-24gb` | 24 GB NVIDIA box, CUDA | Hunyuan3D-2mv, octree 384 / 50 steps | projection, `hy_paint` optional | 4 min enforced |

The PetPop backend (API, worker, Blender wrap/bake/export) keeps running in the cloud VM. Only ComfyUI, the
shape server and Ollama run on the Mac.

## What you run, in order

### On the Mac (details and troubleshooting in [mac/RUNBOOK.md](../mac/RUNBOOK.md))

1. Clone the repo, then check out `poc`:

   ```bash
   git clone https://github.com/envariant/nv-petpop && cd nv-petpop && git checkout poc
   ```

2. Install Homebrew packages, ComfyUI with IP-Adapter Plus, the Hunyuan3D-2.1 MPS fork and Ollama, the
   secrets file, and the three launchd units:

   ```bash
   make -C mac setup
   ```

3. Download about 25 GB of weights, check them against Hugging Face's SHA256, and write the pins into
   `pipelines/comfy/models.yaml`:

   ```bash
   make -C mac models
   ```

4. Commit the pins:

   ```bash
   git add pipelines/comfy/models.yaml && git commit -m "chore(models): pin mac-m4pro weights" && git push
   ```

5. Start the services and probe them locally:

   ```bash
   make -C mac start && make -C mac check
   ```

6. Open the tunnel. This starts the token-checking proxy and the Cloudflare tunnel, and prints the URLs:

   ```bash
   make -C mac tunnel
   ```

### Getting the tunnel URL into the cloud VM

`mac/tunnel.sh` prints five values. Set them as environment variables in the cloud environment
(environment settings, then Edit, then Environment variables), then start a new session:

| Variable | Value |
| --- | --- |
| `GENAI_PROFILE` | `mac-m4pro` |
| `COMFY_URL` | `https://<tunnel host>/comfy` |
| `SHAPE_URL` | `https://<tunnel host>/shape` |
| `OLLAMA_URL` | `https://<tunnel host>/ollama` |
| `GENAI_TOKEN` | the value in `~/petpop-genai/genai.env` on the Mac (copy it; never paste it into a chat) |

The adapters read these through the profile (`config/genai/mac-m4pro.yaml` names `COMFY_URL`, `SHAPE_URL`
and `OLLAMA_URL` as the env vars for its services) and send `Authorization: Bearer $GENAI_TOKEN` on every
call. The proxy on the Mac answers 401 without it.

A quick tunnel's hostname changes every time `tunnel.sh` restarts, so the three URLs must be updated each
time. A named tunnel (`CF_TUNNEL` / `CF_HOSTNAME`, see the runbook) gives a stable hostname you set once. If
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
   target, and the regression set takes about 5 hours (30 x 8 to 12 min). Run it overnight, or use
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
- **Shape server.** `mac/shape_server/server.py` calls the upstream Hunyuan3D-2.1 API
  (`Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(path, subfolder, device, dtype)`). The MPS fork keeps
  that API but documents only its Gradio UI, so the first run may need small fixes.
- **The hy3dmlx MLX port.** It could not be found, so the profile uses the PyTorch MPS fork. A different
  engine can be added under `shape.server` in the profile.

**Pins**
- Model files and revisions were verified against the Hugging Face API, and ComfyUI, the node packs and the
  MPS fork are pinned to their commits as of 2026-10-28.
- The weight SHA256 values are `TODO` until `make -C mac models` (or `scripts/models.py --pin` on the NVIDIA
  box) writes them.

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
worker. Pin its weights with `scripts/models.py --pin --profile nvidia-24gb --dest /srv/models`, then run
gates 3 to 6 with the 4-minute target enforced. To opt in to Hunyuan3D-Paint, set `TEXTURE_BACKEND=hy_paint`.
