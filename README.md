# PetPop

Touch-first kiosk that turns a description of a dog or cat into a chibi vinyl-collectible-style figurine:
a textured GLB preview, a watertight print mesh and a fixed-layout UV atlas for the inkjet painter.
The spec is [docs/BRIEF.md](docs/BRIEF.md); progress is tracked in [docs/PROGRESS.md](docs/PROGRESS.md) and
choices in [docs/DECISIONS.md](docs/DECISIONS.md).

```bash
make setup          # .venv (Python 3.12) + kiosk npm install
make mock           # standalone mock server on :8000 (the frozen contract)
make dev            # API + worker + SPA, CPU only (PETPOP_MODE=mock)
make test           # Python and web unit/contract tests
make gate-0         # acceptance gates 0..6 (3-5 print "SKIPPED (needs GPU)" in mock mode)
```

Blender stages run under a Python 3.11 interpreter with the `bpy` wheel (`PETPOP_BPY_PYTHON`, default
`/opt/bpy/bin/python`); without it the pipeline falls back to a trimesh stand-in marked `fidelity: low`.
