"""Backend directory entry point for FreightIQ FastAPI server.

Ensures imports work whether started from repository root or from inside backend/.
"""
import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent
_root_dir = _backend_dir.parent

for _p in [str(_root_dir), str(_backend_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from backend.app.main import app
except ModuleNotFoundError:
    from app.main import app

__all__ = ["app"]
