# mock-server

Standalone FastAPI implementation of `data/schema/openapi.json` with no database, queue or Blender.
Run with `make mock` (port 8000). It is frozen from S1 on: any API change is a versioned OpenAPI bump that
updates this server, the TypeScript client and the backend in the same commit.

- Breeds: real presets from `data/breeds/`.
- `/spec/parse`: the rule-based parser from `packages/core/python/petpop_core/parser.py`.
- Jobs follow `scripts/*.json` with artefacts from `fixtures/pets/`. Name the pet after a script trigger to
  reach a state from the Studio Generate workspace: `Slowpoke` (slow queue), `Oops` (failed stage), `Plan B` (fallback figurine).
- `PETPOP_MOCK_SPEED` scales script seconds (default 0.1; 0 is instant). `MOCK_SCRIPT` picks the default script.
- `/studio/*` needs a bearer token from `POST /studio/auth/login`: users `operator`, `curator`, `admin`, password
  `PETPOP_STUDIO_PASSWORD` (default `petpop-dev`). The kiosk ops panel (`/kiosk/ops`) needs `X-Staff-Token`
  (`PETPOP_STAFF_TOKEN`, default `dev-staff-token`). `KIOSK_BESPOKE=1` enables `/kiosk/bespoke`.
