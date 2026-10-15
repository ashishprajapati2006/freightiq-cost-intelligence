"""Root entry point for FreightIQ FastAPI backend.

Provides seamless compatibility for cloud application servers (Render, Railway, Fly.io).
"""
import sys
from pathlib import Path

# Ensure project root is in sys.path
_root = str(Path(__file__).resolve().parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from backend.app.main import app

__all__ = ["app"]
