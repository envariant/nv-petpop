"""PetPop backend. Importing it puts the shared Python packages (packages/*/python) on sys.path, so every entry
point that can import `backend` can import petpop_core and petpop_library too."""
import sys as _sys
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[1]
for _p in (_ROOT / "packages" / "library" / "python", _ROOT / "packages" / "core" / "python"):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
