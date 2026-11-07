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

### B3 M9 Seed the library (S9, staff time in Studio on a Tripo profile; needs the frozen segmentation schema)

- [x] `docs/HANDOFF-M9.md`: how Nishant seeds the library through Studio on `tripo` or `tripo-manual` (2026-11-01)
- [ ] Every breed preset covered by a family on a labelled mesh; a pattern layer per marking enumeration
- [ ] Gate 9: library walkthrough attract to order under 3 min; 70 % breed recognisability

## Track C: GenAI host (Section 13)

Parked since decision 108 (Nishant moved generation to Tripo); kept so the Mac can serve as a fallback profile.

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
  - [x] Stages E and F limited the figurine (docs/s3/16, 18: the wrap onto the base topology rounded the head, the
    projection ghosted the face). Resolved by decision 116/117: no wrap; Stage E labels the generated mesh and Stage
    F projects onto it in its own UVs
  - [ ] Stage A: one availability probe instead of two, a smaller patch-only output schema, re-measure
  - [ ] Gates 3 to 5 on the new settings, one pet at a time (`PETPOP_REGRESS_LIMIT=1`)
  - [x] Local setups: docs/LOCAL.md (native `make dev` recommended, Docker Compose `make up` with the image pinned to
    linux/amd64), decision 112; was `docs/HANDOFF-LOCAL.md`: development on the Mac itself in Docker (Compose stack; GenAI stays native and
    isolated behind Caddy at `host.docker.internal:8787`, no tunnel; worker image `linux/amd64` because `bpy`
    has no Linux ARM wheel; one 24 GB memory pool shared with the dev stack)
## Track D: commercial GenAI API backend (decisions 108 to 110, docs/PROVIDERS.md)

- [x] Provider layer: manifest-driven providers (`config/providers/tripo-v3.yaml`, `ManifestProvider`), `api`
  image and shape adapters, Stage C skipped when a profile has no views, texture-keeping normalisation, `transfer`
  texture, profile `tripo`, `genai_check` shows the balance; tested against a fake Tripo apiv3 (2026-10-31)
- [x] Manual mode (decision 111, API 3.2.0): profile `tripo-manual`, the `manual` provider, job status `waiting`,
  Studio Manual inbox (story, Playwright test 12), `scripts/run_job.py`; docs/MANUAL-MODE.md, docs/LOCAL.md,
  docs/HANDOFF-TRIPO.md (2026-10-31)
- [x] GenAI profile per job (decision 113, API 3.3.0): `PETPOP_STUDIO_PROFILES`, "Run on" in Generate and the
  one-off Name screen, `GET /studio/profiles`, the profile recorded on each job and batch (2026-10-31)
- [x] Pipelines and quality switches per job (decisions 114, 115, API 3.4.0): single view or multiview (Tripo
  image-to-multiview, four-slot manual tasks; the Mac's multiview path selectable again), HD texture, HD geometry,
  quad; credit estimates from Tripo's pricing (2026-10-31)
- [ ] First real multiview job: check Tripo's left/right convention (docs/HANDOFF-TRIPO.md, step 5)
- [ ] Build the first library batch by hand in manual mode (Nishant, Tripo Studio): one breed per species first
- [ ] Real Tripo jobs once `TRIPO_API_KEY` is in the environment (docs/HANDOFF-TRIPO.md, first steps): `GENAI_PROFILE=tripo python scripts/genai_check.py`,
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
- [ ] S4 real assets: hand-built template meshes (the segmentation reference; the schema, not a mesh, is frozen
  before M9), `petpop_style` LoRA (Nishant)
- [ ] S5 kiosk hardening on the Mac profile (`make gate-6`)
- [ ] S6 production host: Compose on the NVIDIA box, gates 3 to 6 on `nvidia-24gb`, `make regress`

## Track E: unique meshes, one segmentation schema (decision 116)

- [x] Spec: brief Sections 1, 5, 6.5, 6.6, 10, 13, 14 and 16 and CLAUDE.md rewritten; `data/segmentation/{dog,cat}.json`
  (`seg-1`) and `data/schema/segmentation.schema.json`, checked against the template meshes
- [x] Pipeline (decision 117, API 3.5.0): Stage E labels the generated mesh (template fit, nearest-point transfer of
  parts, regions and landmarks; UV unwrap where a mesh has none); Stage F textures, exports and paint-checks the
  figurine's own mesh (`figure_mesh.npz`, `parts.png`, `mesh_id` in the manifest); the provider texture is kept in
  its own UVs
- [x] Fixture pack regenerated by the pipeline: each pet keeps its own `figure_mesh.npz` (decision 119)
- [x] Library L1 (decision 118, API 3.6.0): release 2.0 of meshes keyed by `mesh_id`, each listing the breeds that
  share it; families, part variants and compositions name their mesh; the kiosk loads the family's mesh and shows
  "Same figure shape as ..."; the export composes and paints on that mesh; gate 7
- [x] Library L2 (decision 119, API 3.7.0): Studio publishes each curated figurine as its own mesh (its family on it,
  its texture as the mesh's base layer, tinted by the base colour), with "shared with" labels for breeds on one
  mesh; QC from segmentation and print checks; `meshes_published`; gates 7 and 8 green
- [x] Tripo part segmentation as a per-job switch (decision 121, API 3.8.0): `segment_model` in the manifest (API and
  manual mode), Stage E snaps the schema labels to Tripo's parts; tested against the fake Tripo
- [ ] Judge it on real jobs (Nishant's credits): `parts.png` with the switch off and on for a few breeds; then decide
  on cross-mesh parts with Tripo's part completion

## Track F: one customer app for kiosks and the app stores (decision 122)

- [x] `@petpop/scene`: the framework-free three.js layer (release meshes, pattern material, stamps, stage, composed
  figure), shared by the Vue app and the React Studio viewer
- [x] `apps/customer` in Vue 3 + Pinia + Tailwind: every screen, responsive from phone portrait to desktop landscape,
  `kiosk` and `app` modes; Capacitor 8 Android and iOS projects
- [x] Playwright on kiosk, phone, tablet and desktop; Storybook stories with a coverage test; gates 0, 1, 2 and 7 on
  the customer app; the React kiosk retired
- [ ] Device spike (Nishant): `npm run build:native`, run on an iPhone, an Android phone and a tablet; check the 3D
  frame rate and touch painting
- [x] Native bundle with the showcase assets only (`npm run bundle:native`, about 7 MB, was 82 MB); gate 1 runs the
  walkthrough on it
- [x] Studio in Vue, desktop first and usable on a tablet; Playwright on desktop and tablet; `@petpop/viewer` and the
  React half of `@petpop/ui` deleted (no React left in the apps)
- [x] Deployment roles (decision 124): `PETPOP_DEPLOY=all|cloud|studio`, `make up` per role (RDS, S3, Caddy), the shop's
  sync agent (releases up, bespoke down and back, prints down), docs/DEPLOY.md
- [x] Payment for orders (decision 125, API 3.9.0): HitPay with PayNow and cards, a fake provider for tests, the order
  screen's payment step, the webhook; printing and the result link wait for payment
- [x] Customer accounts (decision 126, API 3.10.0): email and phone codes, Sign in with Apple and Google, one account
  per email and phone with provider linking, profile, orders, sign-out, deletion; guest checkout with a required
  contact and "create an account" at checkout; push (FCM), email (SES) and SMS (SNS) notifications; itemised quotes
- [ ] Variable pricing: price options and extras as quote lines (`backend/api/pricing.py`), and new kinds of extras
- [ ] Nishant: Apple and Google client ids, a Firebase project (push), SES domain and SNS sender id when ready to send
- [ ] Nishant: the first AWS deployment (docs/DEPLOY.md), HitPay sandbox keys and webhook, then live keys and the price

## Track G: breeds as part kits (decision 127, docs/PARTS.md)

- [x] P1 the geometry (`petpop_library/parts.py`: joint frames, assembly, mirroring, leg twists, head angles, the
  automatic first guess, commit checks) and the kit schema (`data/schema/part_kit.schema.json`)
- [x] P2 proxy kits cut from the labelled templates (`scripts/make_proxy_parts.py`, `fixtures/parts/`)
- [x] P3 the Studio part library: upload, first guess, rig edits, poses, commit (API 3.11.0, mock server, client)
- [x] P4 the TypeScript twin (`packages/scene/src/parts.ts`) and Studio's rigging workbench (3D viewport, gizmos,
  symmetry, poses, commit)
- [x] P5 the Blender composition script (`scripts/compose_parts.py`) consuming committed kits and compositions
- [x] P5a parts exported one at a time: per-breed size guesses from the breed database
  (`petpop_library/part_sizes.py`, `data/breeds/dog_part_sizes.json`), uploads fitted to them (API 3.12.0), joints
  guessed from shape with the legs on the floor, and the draft figure script (`scripts/draft_parts.py`, decision 128)
- [x] P5b the shared library of torsos, legs and tails with a head per breed: allowed variants, per-breed stretches,
  default textures, poses that swap variants, kit-2 (API 3.13.0, decision 130)
- [x] P5c the per-breed parts file (`data/breeds/dog_breed_parts.json`), torso presets (shapes) with socket offsets,
  breed head variants, kit-3 (API 3.14.0, decision 131)
- [x] P5d the breed's default texture edited in the workbench: three colours, pattern, markings (API 3.15.0, decision 132)
- [ ] P6 the switch (decision 133 on):
  - [x] P6a releases carry kits and masks (release 3.0, API 3.16.0); masks uploaded with the parts
  - [x] P6b compositions of kits (composition 3.0, API 3.17.0): variants, torso shape, pose, texture
  - [ ] P6c the customer app assembles parts and paints them per part (Shape and Markings tabs for kit breeds)
  - [ ] P6d the print export composes kits
- [ ] Nishant: the shared library (`shared__<kind>__<variant>.glb` per part type) and the breeds' heads (GLBs per
  docs/PARTS.md), each breed's head texture template and masks, and the shared layouts of the torso, legs and tail

