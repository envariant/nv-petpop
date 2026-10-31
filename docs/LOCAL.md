# Running the PoC on your own computer

Three ways, from lightest to most production-like. All read `.env` (copy `.env.example`; never commit `.env`).

## 1. Mock only: the apps with no backend work (minutes)

```bash
make setup && make mock          # standalone mock server on :8000 (frozen contract, scripted jobs, demo manual tasks)
```
```bash
cd apps/studio && VITE_MOCK=1 npm run dev     # or: the Studio SPA against MSW, no server at all
```

## 2. Native: `make dev` (recommended for day-to-day)

Everything as local processes: the API, the studio and kiosk workers and both SPAs. No Postgres, Redis or MinIO:
`make dev` uses SQLite, a folder store and an in-process queue under `var/` (`DATABASE_URL`, `REDIS_URL` and
`S3_ENDPOINT` empty).

Prerequisites: [uv](https://docs.astral.sh/uv/) (it installs the Pythons), Node 20+ and git.

```bash
make setup                                                     # .venv (Python 3.12) + npm workspaces
```
```bash
uv venv ~/.petpop-bpy --python 3.11 && uv pip install --python ~/.petpop-bpy/bin/python bpy==5.0.1 -e .
```
```bash
cp .env.example .env    # then set GENAI_PROFILE=tripo-manual, PETPOP_BPY_PYTHON=~/.petpop-bpy/bin/python (full path)
```
```bash
set -a && source .env && set +a && make dev
```

- Blender: the stages run under a Python 3.11 interpreter with the `bpy` wheel (wheels exist for macOS arm64 and
  x86-64, Linux x86-64 and Windows). Without it the pipeline still runs, on a trimesh stand-in (`fidelity: low`).
- Kiosk http://127.0.0.1:5173, Studio http://127.0.0.1:5174/studio/ (logins operator, curator, admin; password
  `PETPOP_STUDIO_PASSWORD`, or the generated one in `var/.petpop_studio_password`).
- `make test` runs the Python and web tests; `make help` lists the rest.

## 3. Docker Compose: `make up` (production-like)

The API, both workers (arq), Postgres 16, Redis and MinIO in containers; Blender's `bpy` is inside the app image.
Needs Docker Desktop (or Docker Engine with Compose v2).

```bash
cp .env.example .env    # set GENAI_PROFILE, POSTGRES_PASSWORD, S3_ACCESS_KEY, S3_SECRET_KEY, PETPOP_SECRET,
                        # PETPOP_STUDIO_PASSWORD (and TRIPO_API_KEY for GENAI_PROFILE=tripo)
```
```bash
make up        # builds petpop-app, starts everything, waits for health; make down stops it
```

- Kiosk and Studio are served by the API on http://127.0.0.1:8000 (`/` and `/studio/`).
- The app image is `linux/amd64` because `bpy` has no Linux ARM wheel; on Apple Silicon Docker Desktop runs it
  under emulation (slower Blender stages). `PETPOP_PLATFORM` overrides.
- `make smoke-stack` builds the stack, pushes one mock job through it and tears it down.

## Which GenAI profile

`GENAI_PROFILE` is the default (kiosk bespoke jobs use it); `PETPOP_STUDIO_PROFILES` lists the others Studio may
pick per job or batch under "Run on" (decision 113), e.g. `GENAI_PROFILE=mock` and
`PETPOP_STUDIO_PROFILES=tripo-manual,tripo`. Switching needs no restart: each job records its own.


| `GENAI_PROFILE` | Needs | Use |
| --- | --- | --- |
| `mock` | nothing | UI and pipeline work without GenAI |
| `tripo-manual` | a Tripo Studio account | build the library by hand (docs/MANUAL-MODE.md) |
| `tripo` | `TRIPO_API_KEY` with API credits | the automated pipeline (docs/PROVIDERS.md) |
| `mac-m4pro`, `nvidia-24gb` | a GenAI host (mac/, infra/) | the self-hosted path, parked (decision 108) |

Secrets live only in `.env` or the environment; nothing in the repo holds a key.
