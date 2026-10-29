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

- [ ] Contract 1, the library release: `data/schema/release.schema.json`, signed `release-<species>-<n>.tar`,
  its own contract test (built in M8, loaded in M7)
- [ ] Contract 2, the composition: `data/schema/composition.schema.json`, the only input to a library export
  (M7)

## Track B: library mode (Section 16)

### B1 M7 Kiosk library mode (`make gate-7`; PR)

- [ ] Proxy library built by script from the proxy base meshes: families, region deltas, shell parts, pattern
  layers (signed-distance masks in the UV atlas), packed as a release bundle
- [ ] Tables `families`, `region_deltas`, `shell_parts`, `pattern_layers`, `compositions`, `curation_batches`
- [ ] Release loader: load at start, keep the last two releases, switch atomically
- [ ] Kiosk library API: `GET /kiosk/library/{species}/families`, `/parts?region=`, `/patterns`,
  `POST /kiosk/compositions`, `POST /kiosk/compositions/{id}/export`, `POST /kiosk/compositions/{id}/bespoke`
- [ ] Design screen: assembler with live part swap, pattern layers with coverage sliders, colour swatches per
  layer, seam-correct 3D stamps, symmetry, small brush, undo; instant preview (the preview is the final asset)
- [ ] Name and order straight to Result; print bundle in about a minute
- [ ] Export: Stage F only on the kiosk queue, layers and stamps re-rendered server-side from the composition
  JSON (print matches screen), deltas and shells applied, fused, base and socket, print and paint checks, under
  60 s on CPU
- [ ] Gate 7: composition to print bundle under 60 s; stamps cross seams correctly; coverage slider smooth with
  10 layers active; the kiosk completes an order with the GenAI host unreachable

### B2 M8 Studio (`make gate-8`; PR)

- [ ] Generate workspace reworked as a batch spec builder (breeds x variants x seeds)
- [ ] Batch runner on the studio queue (stages A to E on any profile)
- [ ] Region-delta and full-mesh family-delta extraction per figurine
- [ ] QC metrics (wrap validity, symmetry error, boundary strain, self-intersection) with auto-reject thresholds
- [ ] Review grid with turntables; accept, reject and tag per region; "fix in Blender" round-trip noted
- [ ] Parts and pattern editors; publish with versioning (thumbnail and pattern previews regenerated)
- [ ] `POST /studio/releases`: signed release bundle; release contract test
- [ ] Gate 8 on the mock profile with stand-ins: parts that need a GenAI host print SKIPPED; "a release bundle
  loads on a clean kiosk"

### B3 M9 Seed the library (S9, staff time on the Mac; needs the frozen base mesh from S4)

- [ ] `docs/HANDOFF-M9.md`: what Nishant does on the Mac to seed the library through Studio
- [ ] Every breed preset covered by a family and a parts set; a pattern layer per marking enumeration
- [ ] Gate 9: library walkthrough attract to order under 3 min; 70 % breed recognisability

## Track C: GenAI host (Section 13)

- [ ] S3 Mac bring-up (after Nishant sets `COMFY_URL`, `SHAPE_URL`, `OLLAMA_URL`, `GENAI_TOKEN`): gate-3
  precheck, then `PETPOP_ADAPTERS` swaps A, B, C, D one at a time; gates 3 to 5 one pet at a time in the
  foreground; studio worker only
- [ ] S4 real assets: hand-built base meshes (frozen before M9), `petpop_style` LoRA (Nishant)
- [ ] S5 kiosk hardening on the Mac profile (`make gate-6`)
- [ ] S6 production host: Compose on the NVIDIA box, gates 3 to 6 on `nvidia-24gb`, `make regress`
