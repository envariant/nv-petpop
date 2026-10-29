# Mac GenAI host runbook (profile `mac-m4pro`)

The Mac (Apple Silicon M4 Pro, 24 GB) hosts the three GenAI services. The PetPop backend (API, worker,
Blender stages) keeps running in the cloud VM, or anywhere else, and reaches the Mac through an
authenticated tunnel.

| Service | Port (localhost only) | What runs | launchd label |
| --- | --- | --- | --- |
| ComfyUI | 8188 | SDXL fp16 + depth ControlNet + IP-Adapter Plus on MPS | `com.petpop.comfyui` |
| Shape server | 8190 | Hunyuan3D-2.1 on the MPS fork (`mac/shape_server`), octree 192 / 30 steps | `com.petpop.shape` |
| Ollama | 11434 | qwen2.5 7B instruct, Q4 | `com.petpop.ollama` |
| Proxy + tunnel | 8787 | Caddy (bearer token, path routing) + Cloudflare tunnel | started by `mac/tunnel.sh` |

Only one model is resident at a time:
- ComfyUI gets `/free` after every prompt.
- Ollama runs with `OLLAMA_KEEP_ALIVE=0`.
- The shape server unloads after every mesh.

Expect 12 to 16 minutes per pet; shape alone is about 6 (the fork's M4 Pro benchmark). The 4-minute target is
waived on this profile.

Everything the Mac runs is pinned in this repo and checked before use, so two Macs set up from the same commit
run the same bytes:

| What | Pinned in | Checked by |
| --- | --- | --- |
| uv, Ollama, Caddy, cloudflared | `mac/tools.lock` (release + SHA256/512) | `setup.sh`, before unpacking |
| CPython 3.11.17 | `mac/tools.lock` | the pinned uv (its built-in hashes) |
| Python packages (3 venvs) | `mac/locks/{comfyui,shape,tools}.txt` (every package `==` + hashes, wheels only) | `uv pip sync --require-hashes` |
| ComfyUI, IP-Adapter Plus, the MPS fork, Tencent's Hunyuan3D-2.1 | `pipelines/comfy/requirements.txt` (commits) | `setup.sh`, after checkout |
| Weights | `pipelines/comfy/models.yaml` + `models.lock.json` (revision + SHA256 per file) | `make -C mac models` / `verify` |
| Ollama model | `models.yaml` (`manifest_digest`) | `setup.sh`, after the pull |

Nothing comes from Homebrew, and the fork's `install.sh` is not run: it clones Tencent's repo at HEAD and installs
unpinned packages. `setup.sh` does the same steps from the pins instead.

## 0. Before you start

- macOS 15 or later on Apple Silicon, with the Xcode Command Line Tools (`xcode-select --install`). About 45 GB
  free: weights 20.5 GB, the Ollama model 4.7 GB, venvs and caches the rest. No Homebrew needed.
- A Hugging Face account. Set `HF_TOKEN` if a download asks for it.
- Read the Tencent Hunyuan community licence: it is not granted in the EU, the UK or South Korea.

## 1. Install (once, about 30 to 60 min)

```bash
git clone https://github.com/envariant/nv-petpop && cd nv-petpop && git checkout poc
```

```bash
make -C mac setup
```

This runs `mac/setup.sh`, which does the following, all under `~/petpop-genai`:
- Downloads uv, Ollama, Caddy and cloudflared at the releases in `mac/tools.lock` into `opt/` (linked from
  `bin/`), refusing any file whose hash differs.
- Installs CPython 3.11.17 with that uv into `python/`.
- Checks out ComfyUI, ComfyUI_IPAdapter_plus, `VladimirTalyzin/hunyuan3d-2.1-mac` and Tencent's
  `Hunyuan3D-2.1` (inside the fork, where the fork expects it) at their pinned commits.
- Syncs three venvs in `venvs/` (comfyui, shape, tools) from the hash-locked `mac/locks/*.txt`.
- Pulls the Ollama model into `ollama/` and checks its manifest digest against the pin.
- Writes `genai.env` (including a random `GENAI_TOKEN`, chmod 600) and loads the three launchd units.

Re-running it is safe and is how you take an update: it re-checks every pin and leaves what already matches.

## 2. Fetch the weights (once, about 20.5 GB)

```bash
make -C mac models
```

This downloads every `mac-m4pro` entry of `pipelines/comfy/models.yaml` from its pinned Hugging Face revision
into `~/petpop-models`, hashing each file as it arrives. A file that does not match the SHA256 committed in
`pipelines/comfy/models.lock.json` is deleted and the command fails, so the directory only ever holds the
pinned bytes. The pins were written from Hugging Face's metadata (`scripts/models.py --pin --from-hub`), so
there is nothing to commit afterwards. `make -C mac verify` re-hashes everything later.

## 3. Start and check the services

```bash
make -C mac start
```

```bash
make -C mac check
```

`check` probes ComfyUI `/system_stats`, the shape server `/health` and Ollama `/api/tags` locally. Logs are
in `~/petpop-genai/logs/` (`make -C mac logs`). The first shape job loads Hunyuan3D-2.1, which is slow; the
shape server's `/health` shows `busy: true` while a mesh is being made.

## 4. Open the tunnel and give the VM the URLs

The VM reaches the Mac through a Cloudflare tunnel: `cloudflared` (installed by `setup.sh`, pinned in
`mac/tools.lock`, at `~/petpop-genai/bin/cloudflared`) makes an outbound connection to Cloudflare, so there is no
port forwarding. Pick one of two kinds; the named tunnel is the one to use if you want the URLs set once.

**Named tunnel: stable hostname (recommended).** It needs a free Cloudflare account and a domain whose DNS is on
Cloudflare (its nameservers point to Cloudflare). Do this once, any time after `make -C mac setup`:

1. Log in. A browser opens to authorise your account and pick the domain; this writes `~/.cloudflared/cert.pem`.

   ```bash
   ~/petpop-genai/bin/cloudflared tunnel login
   ```

2. Create the tunnel. Its credentials go to `~/.cloudflared/<tunnel id>.json`; keep that file private and never
   commit it.

   ```bash
   ~/petpop-genai/bin/cloudflared tunnel create petpop
   ```

3. Point a hostname at it (this creates the DNS record in Cloudflare):

   ```bash
   ~/petpop-genai/bin/cloudflared tunnel route dns petpop genai.example.com
   ```

4. Make it the default: add these two lines to `~/petpop-genai/genai.env`, which `tunnel.sh` reads on every start.

   ```
   CF_TUNNEL=petpop
   CF_HOSTNAME=genai.example.com
   ```

**Quick tunnel: no account.** Without `CF_TUNNEL` and `CF_HOSTNAME`, `tunnel.sh` asks Cloudflare's free quick
tunnel service for a random `https://<words>.trycloudflare.com` hostname. Nothing to sign up for, but the hostname
changes every time `tunnel.sh` starts (so the three URLs in the cloud environment must be updated each time) and
Cloudflare offers quick tunnels for testing only.

Then, either way:

```bash
make -C mac tunnel
```

This runs `mac/tunnel.sh`. It starts Caddy on 127.0.0.1:8787, which answers 401 to any request without
`Authorization: Bearer $GENAI_TOKEN`, and the tunnel to it. It checks all three services through the tunnel,
then prints:

```
GENAI_PROFILE=mac-m4pro
COMFY_URL=https://<tunnel host>/comfy
SHAPE_URL=https://<tunnel host>/shape
OLLAMA_URL=https://<tunnel host>/ollama
GENAI_TOKEN=<value of GENAI_TOKEN in ~/petpop-genai/genai.env>
```

Put these five values in the cloud environment: environment settings, Edit, Environment variables. Copy
`GENAI_TOKEN` from `~/petpop-genai/genai.env`; never paste it into a chat. Then start a new session, which
picks the variables up. The tunnel serves only while `make -C mac tunnel` runs (it is not a launchd service).

If the environment's network access is Limited, add the tunnel host (your hostname, or `trycloudflare.com`)
under Allowed domains.

**Why no request waits on a model.** Cloudflare ends any request whose answer takes longer than about 100 s
(HTTP 524). ComfyUI work is already a queued prompt that the worker polls, and the shape server works the same
way: `POST /v1/shape` queues a mesh and answers at once with a job id, the worker polls `GET /v1/shape/<id>`
every few seconds, then downloads `GET /v1/shape/<id>/mesh`. A mesh can take its six minutes without any one
request lasting more than a second.

## 5. Day to day

| Task | Command |
| --- | --- |
| Status | `make -C mac status` |
| Restart all | `make -C mac restart` |
| Stop all | `make -C mac stop` |
| Logs | `make -C mac logs` |
| Re-check weights | `make -C mac verify` |
| After `git pull` | `make -C mac setup` (idempotent), then `make -C mac restart` |
| Take package upgrades | move `EXCLUDE_NEWER` in `mac/lock.sh`, `make -C mac lock`, commit, then `make -C mac setup` |

## 6. Multi-view: MV-Adapter and Hunyuan3D-2mv (library quality, being evaluated)

Per-view SDXL cannot hold identity and viewpoint at once (S3 sweep), so the library path is being tried with
MV-Adapter (four consistent views from the concept) and Hunyuan3D-2mv (shape from all four). Both run inside
ComfyUI; the shape server (Hunyuan3D-2.1, single view) is unchanged. About 21 GB more weights:

```bash
git pull
make -C mac setup     # clones ComfyUI-MVAdapter at its pinned commit, adds its packages, links ComfyUI/petpop-models
make -C mac models    # MV-Adapter, SDXL as a diffusers folder (fp16), its VAE, Hunyuan3D-2mv and -2mv-turbo
make -C mac restart && make -C mac check
```

Nothing changes in the tunnel. The VM then drives both through `scripts/image_sweep.py --stage mv` and
`--stage shape`. The pipeline itself does not use them yet.

### Moving the weights to another disk

The model root is `PETPOP_MODELS` in `~/petpop-genai/genai.env` (default `~/petpop-models`; no spaces in the
path). Setup and `make -C mac models/verify` read it from there; ComfyUI, the shape server and the
`ComfyUI/petpop-models` link get it when setup re-renders them.

```bash
make -C mac stop
mv ~/petpop-models /Volumes/Fast/petpop-models   # or copy, then delete the old folder once verify passes
# edit ~/petpop-genai/genai.env: PETPOP_MODELS=/Volumes/Fast/petpop-models
make -C mac setup && make -C mac verify && make -C mac start
```

An external disk must be mounted before you log in, or the services start without their weights.

## Troubleshooting

- **Black or NaN images from SDXL.** The profile uses the fp16-fix VAE (`sdxl_vae_fp16_fix.safetensors`).
  Check it is in `~/petpop-models/vae`.
- **MPS out of memory.** Another model is still resident. Run `make -C mac restart`, and check that nothing
  else holds the GPU (Activity Monitor, GPU History).
- **Shape server fails to import `hy3dshape`, `backend` or `compat_patches`.** Check that `HY3D_DIR` points
  at the fork checkout and that `$HY3D_DIR/Hunyuan3D-2.1` exists. Re-run `make -C mac setup`.
- **Shape server answers 503 "no weights".** It loads only from
  `~/petpop-models/hf/tencent/Hunyuan3D-2.1/hunyuan3d-dit-v2-1` and never downloads (`HF_HUB_OFFLINE=1`). Run
  `make -C mac models`.
- **`setup.sh` stops on a hash or digest mismatch.** Something upstream changed under a pinned name (a
  re-published release, a moved Ollama tag). Nothing was installed from it. Re-pin deliberately: edit
  `mac/tools.lock`, re-run `mac/lock.sh` for Python packages (`make -C mac lock`), or update the digest in
  `models.yaml`, and commit.
- **401 through the tunnel.** `GENAI_TOKEN` in the cloud environment does not match `~/petpop-genai/genai.env`.
- **Workflow errors on the first run.** All six workflows are `meta.validated: false`. Fix node inputs in the
  generator (`scripts/make_comfy_workflows.py`), regenerate with `make workflows`, then set
  `validated: true` with the date and host in the generator once a graph has run.
