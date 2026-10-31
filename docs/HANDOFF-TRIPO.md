# Handoff: Tripo, API and manual mode (state on 2026-10-31)

For a new session (for example after `TRIPO_API_KEY` is added to the environment). Read CLAUDE.md, then this,
then docs/PROVIDERS.md and docs/MANUAL-MODE.md. Decisions 108 to 112 explain the why.

## Where things stand

- GenAI runs on a commercial API behind profiles and manifests (docs/PROVIDERS.md): `tripo` (the API) and
  `tripo-manual` (the same requests, run by Nishant in Tripo Studio and uploaded in PetPop Studio's Manual inbox).
  The self-hosted Mac and NVIDIA profiles are parked, not removed.
- Tripo's wire format is the manifest `config/providers/tripo-v3.yaml`, built from Tripo's Python SDK 1.0.0
  (2026-10-14). It has never been called with a real key: the first real call checks it.
- Tested here against fakes: tests/pipeline/test_api_provider.py (fake Tripo apiv3), tests/unit/test_tripo_provider.py,
  test_provider_manifests.py, test_manual_provider.py, test_transfer_texture.py, tests/server/test_manual_mode.py,
  the contract test (API 3.2.0) and Studio's Playwright test 12 (Manual inbox).
- Tripo Studio credits do not apply to the API; Nishant has a small API credit balance for the harness test.

## First steps in the new session

1. Check the key is there, without printing it: `env | grep -c '^TRIPO_API_KEY='` should print 1. If not, the
   environment settings need it (Network secrets or an environment variable named `TRIPO_API_KEY`); never ask for it
   in chat.
2. `GENAI_PROFILE=tripo .venv/bin/python scripts/genai_check.py` shows the API balance and the rights the manifest
   records. Fix the manifest first if the balance call fails (envelope, route, auth).
3. One real job, one at a time, then stop and report: `GENAI_PROFILE=tripo .venv/bin/python scripts/run_job.py
   --species dog --breed beagle --seed 1`. It prints each stage with the Tripo task ids and credits, and the balance
   before and after. Expected: B (text-to-image) and D (image-to-model) succeed, C skipped, E and F local.
   Credits are scarce: no second job without Nishant's go.
4. If a field name is wrong (output URL key, status value, credits path), fix `config/providers/tripo-v3.yaml` only,
   rerun the unit tests, and run `scripts/run_job.py` again with the same `--job` (it resumes from the stored stages).
5. Multiview, once single view works and Nishant agrees to the credits (about 55 with HD texture):
   `scripts/run_job.py --breed beagle --seed 1 --pipeline multiview --job j_beagle_mv`. Check which side Tripo's
   "left" view shows (the pet's own left side has the nose toward image-left); if it is mirrored, swap the left and
   right result paths in `config/providers/tripo-v3.yaml` (decision 114).
6. Then record what was learned: task times (`expected_s`, timeouts), the credits per task, the Stage D IoU against
   the front silhouette (`shape.iou_min` is 0.80, provisional), whether Tripo's text-to-image default model and size
   suit (`image.params`), and whether a private-generation request flag exists (decision 110; `create_extras`).

## Choosing per job

`GENAI_PROFILE` is the default; `PETPOP_STUDIO_PROFILES` (e.g. `tripo-manual,tripo`) lets Studio pick per job or
batch ("Run on"), then the profile's pipeline (single view or multiview) and quality switches (HD texture, HD
geometry, quad), with a credit estimate; each job records all three (decisions 113 to 115, API 3.4.0).

## Manual mode, for building the library now

`GENAI_PROFILE=tripo-manual`, `make dev`, Studio -> Generate (a batch) -> Manual (run each request in Tripo Studio,
upload the output) -> Review -> Library -> Releases. docs/MANUAL-MODE.md is the operator guide; docs/LOCAL.md covers
running it on Nishant's own computer (native `make dev`, or Docker Compose with `make up`).

## Open items (docs/PROGRESS.md, Track D)

- Real API jobs and the manifest's first contact with the live API (above).
- Compare Tripo model versions (`v3.1-20260211`, `P1-20260311`, `P2-20260801`) once credits allow.
- Private generation: a request flag, if Tripo's docs for this access name one.
- Gates 3 to 5 and the regression set on the tripo profiles; Stage E's segmentation on real Tripo meshes (decision 116):
  check `segmentation_valid`, `parts.png` and the landmarks on the first jobs.

## Conventions that matter here

- The worker never names a model or host; vendor details live in manifests, models and options in profiles
  (tests/unit/test_host_agnostic.py enforces it).
- `data/schema/openapi.json` changes only with a version bump that updates mock-server, the TypeScript client
  (`make openapi`) and the backend in the same commit; every Studio screen has a story and a Playwright test.
- Tests run on `GENAI_PROFILE=mock` with the GenAI variables unset, so nothing reaches a real service or spends
  credits: `env -u TRIPO_API_KEY GENAI_PROFILE=mock make test`.
