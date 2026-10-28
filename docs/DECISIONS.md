# Decisions

Choices made where BRIEF.md is silent or ambiguous. Newest at the bottom.

1. **Branch.** The cloud session is pinned to branch `claude/serene-darwin-imby77`; it plays the role CLAUDE.md gives `poc`. Each milestone is also pushed as a snapshot branch `milestone/mN` with a PR against `main`, so every milestone gets its own PR while work continues.
2. **Proxy base meshes moved into S0.** The fixture pack (S0) and the Build-screen preview (S1) both need the base meshes, so `scripts/make_proxy_base.py` and `scripts/check_base_mesh.py` are built first.
3. **Python layout.** One project venv (`.venv`, Python 3.12) for API, worker, mock server and tests. Blender scripts run as subprocesses under the bpy interpreter (`PETPOP_BPY_PYTHON`, default `/opt/bpy/bin/python`, Python 3.11 + `bpy` 5.0), mirroring the production "Blender via subprocess" design. Shared contract models and the rule-based parser live in `backend/core/` and are imported by the mock server.
4. **Rendering engine.** Workbench and EEVEE need EGL/GPU and crash headless; all mock renders use Cycles on CPU at low samples.
5. **PetSpec enumerations.** Closed sets chosen where Section 3 lists none: body.size tiny/small/medium/large, build slim/standard/stocky, a 12-name coat palette (custom hex maps to the nearest name), 12 patterns (the Build screen shows the 8 that fit the species), markings white_blaze/white_socks/white_chest/dark_mask/points, 6 eye colours, 5 nose colours. `overrides` only allows `ears.asymmetry`. `ears.tufted` (cat) drives the `ear_tuft` morph.
6. **Cat morph list (spec gap).** Section 10 says "cat: 12, no brachy split, add ear_tuft", which does not add up from 15. Chosen: drop `brachy`, `ear_drop`, `tail_curl`, `leg_len`, add `ear_tuft` (12). `vocab.species_substitutes` maps the dropped dog targets onto cat ones. To confirm with whoever builds the hand-made cat mesh.
7. **Morph weights** range -1..1 with 0 = the base mesh; slot contributions are summed and clamped. `ears.asymmetry` is prompt-only in the PoC (no per-side morph exists in Section 10).
8. **Units.** Base meshes, wraps and print meshes are in millimetres (1 Blender unit = 1 mm), 90 mm tall; GLBs keep those units and the viewers fit the camera to the bounds.
9. **Region masks.** Pattern and marking regions are baked once per base mesh into two UV-space RGBA masks (`mask_a.png`, `mask_b.png`). The preview shader, the mock renders and the albedo bake read the same masks, so swatches, preview and output agree.
10. **One contract router.** `backend/core/contract.py` defines every `/api/v1` route once against an implementation protocol; the mock server and the backend mount it, so their OpenAPI is identical by construction and `data/schema/openapi.json` is generated from it (`make openapi`), with a drift check in gate-0.
11. **Mock script selection.** The mock server picks a script by pet name (`Slowpoke`, `Oops`, `Plan B`), otherwise `MOCK_SCRIPT` (default `normal`), so every kiosk state is reachable from the touchscreen with no headers.
12. **Fixture pack v1** is produced by the numpy/trimesh stand-in (`make_fixtures.py --lowfi`, `fidelity: low`); S2 regenerates it from the real mock-mode pipeline. About 32 MB.
13. **GPU gates.** Gates 3 to 5 exit 0 after printing `gate-N: SKIPPED (needs GPU)` in mock mode and never print PASSED; gate-6 likewise skips (needs the kiosk screen and GPU).
14. **MSW parser.** Standalone mode (`VITE_MOCK=1`) uses a small TypeScript synonym matcher over `vocab.json` instead of the Python rule parser; it is only for demos without a backend.
