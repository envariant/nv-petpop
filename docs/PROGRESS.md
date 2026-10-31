# PetPop PoC progress

Regenerated from BRIEF Sections 13, 16 and 17 after M2.5 merged. Three tracks: **A** the platform (two apps on
one core, Section 17), **B** the library (M7 to M9, Section 16) and **C** the GenAI host (S3 to S6, Section 13).
Order of work in this session: A1 (refactor), B1 (M7), B2 (M8), C1 (S3, when the Mac host is up), then
`docs/HANDOFF-M9.md`. Decisions the brief leaves open go in `docs/DECISIONS.md`.

## Done before this plan

- [x] S0 / M0 contract and mock server (`make gate-0`), S1 / M1 front end (`make gate-1`), S2 / M2 real backend,
  parametric path (`make gate-2`): envariant/nv-petpop#1, #2, #3
- [x] M2.5 host-agnostic GenAI profiles, `mac/` host kit, Compose stack on the mock profile, deterministic Mac
  setup: envariant/nv-petpop#4

## Track A: two apps, one core (Section 17)

### A1 Refactor, no new features (gates 0 to 2 still pass; PR)

- [x] Python `packages/core` (`petpop_core`: PetSpec, manifest schemas, vocab, breed presets, rule parser, prompt
  compiler) and `packages/library` (`petpop_library`: base-mesh geometry, accessories, colouring; later delta
  extraction, QC, release packer and loader); packages never import `backend/` or `apps/`
- [x] TypeScript workspaces: `packages/core` (generated API client and types, spec helpers), `packages/viewer`
  (three.js viewer, pattern material, morph application), `packages/ui` (shared kiosk-frame UI kit); apps import
  packages, packages never import apps
- [x] API 2.0.0: `/api/v1/kiosk/*` (anonymous kiosk session, five-tap ops panel) and `/api/v1/studio/*` (staff
  login, roles operator / curator / admin, jobs, parse, queue); mock server, TypeScript client and backend in
  the same commit
- [x] Two queues, `kiosk` and `studio`, each with its own worker process; only the studio worker builds GenAI
  adapters; the kiosk queue runs Stage F only
- [x] `apps/studio/`: the Build, Brief, Name, Generating and Result screens as the Generate workspace, behind
  staff login, plus the queue panel; Storybook story and Playwright test per screen
- [x] `apps/kiosk/`: library-mode only (Attract, Species, Breed, Design); "Make it unique" behind `KIOSK_BESPOKE`
  (off by default) enqueues a studio job and shows "we'll message you", never a Generating screen
- [x] `make dev` runs the API, both workers and both SPAs; Compose runs both workers
- [x] Gates 0, 1 and 2 pass on the new layout; PR for the refactor

### A2 Contracts

- [x] Contract 1, the library release: `data/schema/release.schema.json`, signed `release-<species>-<n>.tar`,
  its own contract test (built in M8, loaded in M7)
- [x] Contract 2, the composition: `data/schema/composition.schema.json`, the only input to a library export
  (M7)

## Track B: library mode (Section 16)

### B1 M7 Kiosk library mode (`make gate-7`; PR)

- [x] Proxy library built by script from the proxy base meshes: families, region deltas, shell parts, pattern
  layers (signed-distance masks in the UV atlas), packed as a release bundle
- [x] Tables `families`, `region_deltas`, `shell_parts`, `pattern_layers`, `compositions`, `curation_batches`
- [x] Release loader: load at start, keep the last two releases, switch atomically
- [x] Kiosk library API: `GET /kiosk/library/{species}/families`, `/parts?region=`, `/patterns`,
  `POST /kiosk/compositions`, `POST /kiosk/compositions/{id}/export`, `POST /kiosk/compositions/{id}/bespoke`
- [x] Design screen: assembler with live part swap, pattern layers with coverage sliders, colour swatches per
  layer, seam-correct 3D stamps, symmetry, small brush, undo; instant preview (the preview is the final asset)
- [x] Name and order straight to Result; print bundle in about a minute
- [x] Export: Stage F only on the kiosk queue, layers and stamps re-rendered server-side from the composition
  JSON (print matches screen), deltas and shells applied, fused, base and socket, print and paint checks, under
  60 s on CPU
- [x] Gate 7: composition to print bundle under 60 s; stamps cross seams correctly; coverage slider smooth with
  10 layers active; the kiosk completes an order with the GenAI host unreachable

### B2 M8 Studio (`make gate-8`; PR)

- [x] Generate workspace reworked as a batch spec builder (breeds x variants x seeds)
- [x] Batch runner on the studio queue (stages A to E on any profile)
- [x] Region-delta and full-mesh family-delta extraction per figurine
- [x] QC metrics (wrap validity, symmetry error, boundary strain, self-intersection) with auto-reject thresholds
- [x] Review grid with turntables; accept, reject and tag per region; "fix in Blender" round-trip noted
- [x] Parts and pattern editors; publish with versioning (thumbnail and pattern previews regenerated)
- [x] `POST /studio/releases`: signed release bundle; release contract test
- [x] Gate 8 on the mock profile with stand-ins (the 20-figurine yield runs on the Mac profile in S8): parts that need a GenAI host print SKIPPED; "a release bundle
  loads on a clean kiosk"

### B3 M9 Seed the library (S9, staff time on the Mac; needs the frozen base mesh from S4)

- [ ] `docs/HANDOFF-M9.md`: what Nishant does on the Mac to seed the library through Studio
- [ ] Every breed preset covered by a family and a parts set; a pattern layer per marking enumeration
- [ ] Gate 9: library walkthrough attract to order under 3 min; 70 % breed recognisability

## Track C: GenAI host (Section 13)

- [ ] S3 Mac bring-up (after Nishant sets `COMFY_URL`, `SHAPE_URL`, `OLLAMA_URL`, `EMBED_URL`, `GENAI_TOKEN`): gate-3
  precheck, then `PETPOP_ADAPTERS` swaps A, B, C, D one at a time; gates 3 to 5 one pet at a time in the
  foreground; studio worker only. Progress (2026-10-29/30; contact sheets in `docs/s3/`, decisions 86 to 94):
  - [x] Precheck: all services answer through the tunnel (`scripts/genai_check.py`)
  - [x] Fixes found on the way: Pillow 13 depth PNGs, profile-aware health contract check, `PETPOP_REGRESS_LIMIT`
    for one-pet gate runs, launchd reload race in `mac/setup.sh`, model root in `genai.env`
  - [x] Stage A measured: about 11 s per parse (tunnel 1.2 s per call, two availability probes, 0.8 s model load,
    about 370 output tokens), so it falls back to the rule parser; fix listed below
  - [x] Stage B/C sweep (`scripts/image_sweep.py`): proxy-mesh control causes the procedural look; c3 (plain
    txt2img at 1024) is the concept setting; per-view SDXL views cannot hold identity and viewpoint (no back view)
  - [x] MV-Adapter, Hunyuan3D-2mv (full and turbo) and DINOv2-Large pinned and installed on the Mac; DINOv2 served
    as its own `embed` service (`EMBED_URL`, shape server process for now)
  - [x] Score the existing view sets (`image_sweep.py --stage score`) and check the DINOv2 scores against the eye
    (2026-10-30, decision 97: similarity ranks agree but is viewpoint-blind on its own; fill fooled by textured floors)
  - [x] MV-Adapter views (`--stage mv`) for golden_retriever and french_bulldog from their c3 concepts; check the
    left/right convention; then Hunyuan3D-2mv full and turbo on those views (`--stage shape`). 2026-10-30: 02b ran
    after two fixes (decisions 95, 96), 629 s / 447 s per pet at 768 px; real backs; the frenchie's left view
    under-rotated. 2mv full 1347 s (clean, library-grade shape), turbo 258 s (body depth collapses, tail detached),
    docs/s3/5 and 6. Found: 03 decodes with `VoxelToMeshBasic` (unwelded voxel cubes); use `VoxelToMesh` surface net
  - [ ] Next Mac jobs, one at a time, each on Nishant's go (planned 2026-10-30). Before them, on the Mac: `git pull`,
    `make -C mac setup` (renders the new `background_removal` model folder), `make -C mac models` (BiRefNet,
    0.44 GB, decision 98), `make -C mac restart`
    - [x] J1: golden 2mv turbo on the existing views with surface-net meshing (validates 03), then turbo with
      `euler/simple` and `lcm/simple` (is turbo's poor shape the sampler?), about 14 min
    - [x] J2: c3 concept + MV-Adapter for cat:calico, cat:tabby_orange, dog:great_dane (asymmetric coats), then
      DINOv2 scores and BiRefNet mattes: calibrates the left/right balance check, about 36 min
    - [x] J3 (optional): french_bulldog 2mv full with surface net on the existing views: does full tolerate an
      under-rotated side? About 23 min
    - Results 2026-10-30 (decisions 100, 101; docs/s3/7 to 9): surface net validated; turbo's best sampler is
      `euler/simple` but it still collapses depth; side balance is a review flag; full tolerates an under-rotated side
  - [x] Concept A/B for the sharp-focus prompt (decision 99) and the three-quarter concept test (X1 to X4,
    2026-10-30, decision 102, docs/s3/10 to 14): sharp prompt kept, front reference kept, 3/4 reference not adopted
  - [x] Integrate (2026-10-30, decisions 103 to 106): c3 txt2img concept, MV-Adapter views from a grey 90 %
    reference, BiRefNet matting, 2mv full via ComfyUI with the shape server as single-view fallback; bespoke jobs
    take the fast path (single view). Validated on the Mac with real jobs (golden, seed 101): library path 1819 s,
    no fallback, IoU 0.896, wrap valid, watertight; fast path 958 s, shape fine, wrap invalid (shipped unwrapped);
    grey-reference rerun of C to F: much better views (docs/s3/15 to 18)
  - [x] Mark each workflow that has run cleanly on the Mac `validated: true` (`VALIDATED` in
    `scripts/make_comfy_workflows.py`): 01, 02 (2026-10-29), 01b, 02b, 03, 05 (2026-10-30); 03b and 04 are NVIDIA-only
  - [x] Single view from a 3/4 vs a front concept (decision 107, docs/s3/19): mixed on two pets; it follows
    whether the concept shows the tail. Open: "tail visible" prompt test on five pets; no whiskers for cats
  - [ ] Stages E and F now limit the figurine (docs/s3/16, 18): the raw 2mv or 2.1 shape is good, but the wrap onto
    the base topology rounds the head and the four-view projection onto the wrapped mesh ghosts the face (doubled
    eyes and nose) and smears colour. Next: project onto the raw shape and transfer to the base UVs, or weight each
    view by how well the wrapped silhouette matches it; fix the fast path's invalid wraps (inverted triangles)
  - [ ] Stage A: one availability probe instead of two, a smaller patch-only output schema, re-measure
  - [ ] Gates 3 to 5 on the new settings, one pet at a time (`PETPOP_REGRESS_LIMIT=1`)
  - [ ] `docs/HANDOFF-LOCAL.md`: development on the Mac itself in Docker (Compose stack; GenAI stays native and
    isolated behind Caddy at `host.docker.internal:8787`, no tunnel; worker image `linux/amd64` because `bpy`
    has no Linux ARM wheel; one 24 GB memory pool shared with the dev stack)
## Track D: commercial GenAI API backend (decisions 108 to 110, docs/PROVIDERS.md)

- [x] Provider layer: manifest-driven providers (`config/providers/tripo-v3.yaml`, `ManifestProvider`), `api`
  image and shape adapters, Stage C skipped when a profile has no views, texture-keeping normalisation, `transfer`
  texture, profile `tripo`, `genai_check` shows the balance; tested against a fake Tripo apiv3 (2026-10-31)
- [ ] Real Tripo jobs once `TRIPO_API_KEY` is in the environment: `GENAI_PROFILE=tripo python scripts/genai_check.py`,
  then one job per species; record times, credits and IoU; settle `shape.iou_min`, `expected_s` and timeouts
- [ ] Compare Tripo model versions (`v3.1-20260211`, `P1-20260311`, `P2-20260801`) and text-to-image models on the
  five sweep pets; pick `image.params` (model, size) and `shape.params`
- [ ] Private generation: confirm with Nishant's Tripo docs whether a request flag exists; if so, `create_extras`
- [ ] Studio and the regression set on the `tripo` profile (gates 3 to 5 against the API)

- [ ] DINOv2 beyond evaluation, once its scores have been checked against the eye: best-of-N concept selection
  (2 to 3 seeds, scored against the style references with a minimum subject fill), then similarity search and
  de-duplication for the library (M8/M9)
- [ ] Style LoRA from Nishant's curated image set (`assets/lora/DATASET.md`): captions, Kohya layout, Mac training
  config, then `image_sweep.py --lora` for the before/after
- [ ] S4 real assets: hand-built base meshes (frozen before M9), `petpop_style` LoRA (Nishant)
- [ ] S5 kiosk hardening on the Mac profile (`make gate-6`)
- [ ] S6 production host: Compose on the NVIDIA box, gates 3 to 6 on `nvidia-24gb`, `make regress`
