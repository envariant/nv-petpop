# Mac GenAI host runbook (profile `mac-m4pro`)

The Mac (Apple Silicon M4 Pro, 24 GB) hosts the three GenAI services. The PetPop backend (API, worker,
Blender stages) keeps running in the cloud VM, or anywhere else, and reaches the Mac through an
authenticated tunnel.

| Service | Port (localhost only) | What runs | launchd label |
| --- | --- | --- | --- |
| ComfyUI | 8188 | SDXL fp16 + depth ControlNet + IP-Adapter Plus on MPS | `com.petpop.comfyui` |
| Shape server | 8190 | Hunyuan3D-2.1 on the MPS fork (`mac/shape_server`) | `com.petpop.shape` |
| Ollama | 11434 | qwen2.5 7B instruct, Q4 | `com.petpop.ollama` |
| Proxy + tunnel | 8787 | Caddy (bearer token, path routing) + Cloudflare tunnel | started by `mac/tunnel.sh` |

Only one model is resident at a time:
- ComfyUI gets `/free` after every prompt.
- Ollama runs with `OLLAMA_KEEP_ALIVE=0`.
- The shape server unloads after every mesh.

Expect 8 to 12 minutes per pet. The 4-minute target is waived on this profile.

## 0. Before you start

- macOS on Apple Silicon with Homebrew, about 60 GB free (weights about 25 GB, venvs and caches the rest).
- A Hugging Face account. Set `HF_TOKEN` if a download asks for it.
- Read the Tencent Hunyuan community licence: it is not granted in the EU, the UK or South Korea.

## 1. Install (once, about 30 to 60 min)

```bash
git clone https://github.com/envariant/nv-petpop && cd nv-petpop && git checkout poc
```

```bash
make -C mac setup
```

This runs `mac/setup.sh`, which does the following:
- Installs python@3.11, uv, ollama, caddy and cloudflared.
- Clones ComfyUI, ComfyUI_IPAdapter_plus and `VladimirTalyzin/hunyuan3d-2.1-mac` at the commits in `pipelines/comfy/requirements.txt`.
- Creates their venvs and pulls the Ollama model.
- Writes `~/petpop-genai/genai.env` (including a random `GENAI_TOKEN`, chmod 600).
- Loads the three launchd units.

## 2. Download and pin the weights (once, about 25 GB)

```bash
make -C mac models
```

This downloads every `mac-m4pro` entry of `pipelines/comfy/models.yaml` from its pinned Hugging Face
revision into `~/petpop-models`. It checks each file against Hugging Face's own SHA256, then writes the
value into `models.yaml` in place of `TODO`. Commit the pins:

```bash
git add pipelines/comfy/models.yaml && git commit -m "chore(models): pin mac-m4pro weights" && git push
```

## 3. Start and check the services

```bash
make -C mac start
```

```bash
make -C mac check
```

`check` probes ComfyUI `/system_stats`, the shape server `/health` and Ollama `/api/tags` locally. Logs are
in `~/petpop-genai/logs/` (`make -C mac logs`). The first shape request loads Hunyuan3D-2.1, which is slow.

## 4. Open the tunnel and give the VM the URLs

```bash
make -C mac tunnel
```

This runs `mac/tunnel.sh`. It starts Caddy on 127.0.0.1:8787, which answers 401 to any request without
`Authorization: Bearer $GENAI_TOKEN`, and a Cloudflare tunnel to it. It checks all three services through
the tunnel, then prints:

```
GENAI_PROFILE=mac-m4pro
COMFY_URL=https://<words>.trycloudflare.com/comfy
SHAPE_URL=https://<words>.trycloudflare.com/shape
OLLAMA_URL=https://<words>.trycloudflare.com/ollama
GENAI_TOKEN=<value of GENAI_TOKEN in ~/petpop-genai/genai.env>
```

Put these five values in the cloud environment: environment settings, Edit, Environment variables. Copy
`GENAI_TOKEN` from `~/petpop-genai/genai.env`; never paste it into a chat. Then start a new session, which
picks the variables up.

A quick tunnel gets a new random hostname every time `tunnel.sh` starts. For a stable hostname, create a
named tunnel once (needs a Cloudflare account and a domain):

```bash
cloudflared tunnel login
```

```bash
cloudflared tunnel create petpop
```

```bash
cloudflared tunnel route dns petpop genai.example.com
```

```bash
CF_TUNNEL=petpop CF_HOSTNAME=genai.example.com mac/tunnel.sh
```

If the environment's network access is Limited, add the tunnel host (`trycloudflare.com` or your hostname)
under Allowed domains.

## 5. Day to day

| Task | Command |
| --- | --- |
| Status | `make -C mac status` |
| Restart all | `make -C mac restart` |
| Stop all | `make -C mac stop` |
| Logs | `make -C mac logs` |
| Re-check weights | `make -C mac verify` |
| After `git pull` | `make -C mac setup` (idempotent), then `make -C mac restart` |

## Troubleshooting

- **Black or NaN images from SDXL.** The profile uses the fp16-fix VAE (`sdxl_vae_fp16_fix.safetensors`).
  Check it is in `~/petpop-models/vae`.
- **MPS out of memory.** Another model is still resident. Run `make -C mac restart`, and check that nothing
  else holds the GPU (Activity Monitor, GPU History).
- **Shape server fails to import `hy3dshape`.** Check that `HY3D_DIR` points at the fork checkout and that
  `$HY3D_DIR/venv` exists. Re-run `./install.sh --shape-only --skip-weights` inside the fork.
- **Shape server cannot find the weights.** It loads from `~/petpop-models/hf/tencent/Hunyuan3D-2.1` when
  `make -C mac models` has run, and from the Hugging Face cache otherwise.
- **401 through the tunnel.** `GENAI_TOKEN` in the cloud environment does not match `~/petpop-genai/genai.env`.
- **Workflow errors on the first run.** All six workflows are `meta.validated: false`. Fix node inputs in the
  generator (`scripts/make_comfy_workflows.py`), regenerate with `make workflows`, then set
  `validated: true` with the date and host in the generator once a graph has run.
