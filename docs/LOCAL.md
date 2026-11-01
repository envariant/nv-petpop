# Running the PoC on your own computer

Three ways, from lightest to most production-like. All read `.env` (copy `.env.example`; never commit `.env`).

## 1. Mock only: the apps with no backend work (minutes)

```bash
make setup && make mock          # standalone mock server on :8000 (frozen contract, scripted jobs, demo manual tasks)
```
```bash
cd apps/studio && VITE_MOCK=1 npm run dev     # or: the Studio SPA against MSW, no server at all
```
```bash
cd apps/customer && npm run dev:mock          # the customer app against MSW, no server at all
```

## 2. Native: `make dev` (recommended for day-to-day)

Everything as local processes: the API, the studio and kiosk workers, the customer app and Studio. No Postgres, Redis or MinIO:
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

Ctrl-C stops everything `make dev` started. `make stop` stops any PetPop dev processes of this checkout that are
still running (a crashed or interrupted run, `make mock`); `make dev` runs it first, so a stale run never holds the
ports.

- Blender: the stages run under a Python 3.11 interpreter with the `bpy` wheel (wheels exist for macOS arm64 and
  x86-64, Linux x86-64 and Windows). Without it the pipeline still runs, on a trimesh stand-in (`fidelity: low`).
- What lives outside the repo: the `bpy` environment (`~/.petpop-bpy`, a uv venv, delete it to remove), and the
  tools you install yourself: uv, Node and git; `ffmpeg` (optional: without it no `turntable.mp4`; macOS
  `brew install ffmpeg`, Debian/Ubuntu `apt install ffmpeg`); on Linux, the X/GL libraries `bpy` loads
  (`apt install libgl1 libxi6 libxrender1 libxkbcommon0 libsm6`; macOS needs none); Playwright's browsers for the
  web tests only (`npx playwright install chromium`, cached under `~/.cache/ms-playwright` or
  `~/Library/Caches/ms-playwright`). Python packages go into `.venv` and npm packages into `node_modules`, both
  inside the repo; nothing is installed into the system Python or globally with npm.
- Customer app http://127.0.0.1:5173 (add `?mode=kiosk` for kiosk mode, `?mode=app` to go back), Studio
  http://127.0.0.1:5174/studio/ (logins operator, curator, admin; password
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

- The customer app and Studio are served by the API on http://127.0.0.1:8000 (`/` and `/studio/`).
- The app image is `linux/amd64` because `bpy` has no Linux ARM wheel; on Apple Silicon Docker Desktop runs it
  under emulation (slower Blender stages). `PETPOP_PLATFORM` overrides.
- `make smoke-stack` builds the stack, pushes one mock job through it and tears it down.

## 4. The customer app on devices: Capacitor (decision 122)

`apps/customer` is one Vue build for the browser, the app stores and the kiosk. Two runtime modes:

- `app` (default): the store app and the browser. System keyboard, normal navigation, no idle wipe.
- `kiosk`: the in-store touchscreen. On-screen keyboard, "Still there?" idle wipe, five taps in the top-right
  corner for the staff panel, type scaled to the screen.

The mode comes from `?mode=kiosk` (remembered on the device, so a kiosk is set up once), else the build's
`VITE_MODE`. A dedicated kiosk build: `VITE_MODE=kiosk npm run build`.

Native builds need Xcode (iOS, macOS only) or Android Studio; nothing else is installed globally (the Capacitor
CLI is a dev dependency, and the iOS project uses Swift Package Manager, no CocoaPods).

```bash
cd apps/customer && VITE_API_ORIGIN=http://192.168.1.20:8000 npm run build:native   # build, then copy into ios/ and android/
```
```bash
cd apps/customer && npm run open:ios        # or open:android; run on a simulator or a device from the IDE
```

- `VITE_API_ORIGIN` is the backend the app talks to: inside the native shell there is no same-origin API. For a
  phone on your LAN use your computer's address and start the API with `--host 0.0.0.0`; the backend already
  allows the Capacitor origins (`capacitor://localhost`, `https://localhost`, `http://localhost`), and
  `PETPOP_CORS_ORIGINS` (comma separated) adds others.
- iOS and Android refuse plain `http://` to other hosts by default; for a LAN test, allow it in the app's
  `Info.plist` (NSAppTransportSecurity) or Android network security config, or put the API behind HTTPS.
- App id: `PETPOP_APP_ID` (default `com.petpop.app`) when you run `npx cap add`; change it before the first store
  upload.
- Kiosk hardware: an Android tablet with screen pinning or a device-owner launcher, or an iPad with Guided Access,
  running the native build in kiosk mode; or Chromium in `--kiosk` on a PC, pointed at the API's `/?mode=kiosk`.
- The native bundle currently includes the fixture pack; trimming it to the showcase assets is a follow-up.

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
