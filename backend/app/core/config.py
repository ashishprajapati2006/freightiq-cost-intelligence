"""Configuration management for FreightIQ Analytics Engine and FastAPI Backend.

Provides flexible path resolution, storage abstractions, CORS controls,
and deterministic operational thresholds without machine-specific hardcoding.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Set

try:
    from dotenv import load_dotenv
    # Attempt to load .env from project root or current working dir if available
    _env_path = Path.cwd() / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
    else:
        load_dotenv()
except Exception:
    pass


def find_project_root() -> Path:
    """Locate the project root directory.

    Checks:
    1. Environment variable 'PROJECT_ROOT'
    2. Ascending parent directories looking for 'dataset/shipment_records.csv'
    3. Fallback based on relative file location (__file__).parents[3]
    """
    env_root = os.environ.get("PROJECT_ROOT")
    if env_root and Path(env_root).exists():
        return Path(env_root).resolve()

    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "dataset" / "shipment_records.csv").exists():
            return parent.resolve()

    return Path(__file__).resolve().parents[3]


class Settings:
    """Deterministic configuration settings for FreightIQ analytics and API."""

    def __init__(self, project_root: Optional[Path] = None):
        self.PROJECT_ROOT: Path = (project_root or find_project_root()).resolve()
        self.DATASET_DIR: Path = self.PROJECT_ROOT / "dataset"
        self.BACKEND_DIR: Path = self.PROJECT_ROOT / "backend"
        self.OUTPUT_DIR: Path = self.BACKEND_DIR / "output"
        self.STORAGE_DIR: Path = self.BACKEND_DIR / "storage"
        self.DATASETS_STORAGE_DIR: Path = self.STORAGE_DIR / "datasets"
        self.RUNS_STORAGE_DIR: Path = self.STORAGE_DIR / "runs"
        self.MODELS_DIR: Path = self.BACKEND_DIR / "ml_models"

        # Application Metadata
        self.APP_NAME: str = "FreightIQ API"
        self.APP_VERSION: str = "0.2.0"
        self.API_V1_STR: str = "/api/v1"
        self.ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")

        # Dataset paths (bundled default)
        self.SHIPMENTS_FILE: Path = self.DATASET_DIR / "shipment_records.csv"
        self.NOTES_FILE: Path = self.DATASET_DIR / "context_notes.csv"
        self.SAMPLE_OUTPUT_FILE: Path = self.DATASET_DIR / "sample_output_format_v2.csv"
        self.DEFAULT_DATASET_ID: str = "default"

        # Generated outputs
        self.OUTPUT_CSV_FILE: Path = self.OUTPUT_DIR / "freight_cost_anomalies.csv"

        # Upload & Security Limits
        self.MAX_UPLOAD_SIZE_BYTES: int = int(
            os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(25 * 1024 * 1024))  # 25 MB
        )
        raw_cors = os.environ.get(
            "FRONTEND_ORIGINS",
            os.environ.get(
                "CORS_ORIGINS",
                "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173",
            ),
        )
        self.CORS_ORIGINS: List[str] = [
            origin.strip().rstrip("/") for origin in raw_cors.split(",") if origin.strip()
        ]

        # Support Vercel preview branch deployments safely without wildcards
        self.ALLOW_VERCEL_PREVIEWS: bool = os.environ.get(
            "ALLOW_VERCEL_PREVIEWS", "true"
        ).lower() in {"1", "true", "yes"}
        self.CORS_ORIGIN_REGEX: Optional[str] = (
            r"^https://[a-zA-Z0-9_-]+\.vercel\.app$"
            if self.ALLOW_VERCEL_PREVIEWS
            else None
        )

        # Core Analytical Parameters
        self.DEFAULT_ANOMALY_THRESHOLD_PCT: float = float(
            os.environ.get("ANOMALY_THRESHOLD_PCT", "20.0")
        )
        self.MAX_HISTORICAL_WEEKS: int = int(
            os.environ.get("MAX_HISTORICAL_WEEKS", "8")
        )
        self.NOTE_DATE_WINDOW_DAYS: int = int(
            os.environ.get("NOTE_DATE_WINDOW_DAYS", "42")
        )
        self.FLOAT_PRECISION: int = 4

        # Canonical Column Contract
        self.OUTPUT_COLUMNS: List[str] = [
            "route",
            "week_of",
            "cost_per_tonne_km",
            "vs_own_history",
            "vs_similar_routes",
            "flagged",
            "matched_note_id",
            "reason",
        ]

        # Valid route types
        self.VALID_ROUTE_TYPES: Set[str] = {"Short", "Medium", "Long"}

    def ensure_directories(self) -> None:
        """Ensure necessary output and storage directories exist."""
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.DATASETS_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.RUNS_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)


# Global default instance
settings = Settings()
settings.ensure_directories()
