# mock-server

Standalone FastAPI implementation of `data/schema/openapi.json` with no database, queue or Blender.
Run with `make mock` (port 8000). It is frozen from S1 on: any API change is a versioned OpenAPI bump that
updates this server, the TypeScript client and the backend in the same commit.

- Breeds: real presets from `data/breeds/`.
- `/spec/parse`: the rule-based parser from `backend/core/parser.py`.
- Jobs follow `scripts/*.json` with artefacts from `fixtures/pets/`. Name the pet after a script trigger to
  reach a state from the kiosk: `Slowpoke` (slow queue), `Oops` (failed stage), `Plan B` (fallback figurine).
- `PETPOP_MOCK_SPEED` scales script seconds (default 0.1; 0 is instant). `MOCK_SCRIPT` picks the default script.
- Staff endpoints need `X-Staff-Token` (`PETPOP_STAFF_TOKEN`, dev default `dev-staff-token`).
