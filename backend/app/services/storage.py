"""Lightweight, file-based persistence and storage abstraction service.

Stores datasets, qualitative notes, execution runs, and analytical artifacts
with content hashing (SHA-256) and audit logging.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.app.core.config import settings
from backend.app.core.data_loader import load_context_notes, load_shipments
from backend.app.core.exceptions import EntityNotFoundException, SecurityException
from backend.app.core.middleware import sanitize_safe_id
from backend.app.schemas.analysis import ContextNote
from backend.app.schemas.dataset import DatasetMetadata


def compute_sha256(content: str | bytes) -> str:
    """Calculate SHA-256 hash of text or bytes."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


class StorageManager:
    """Manages persistence for datasets, analytical runs, and evaluation logs."""

    def __init__(self):
        self.settings = settings
        self.datasets_dir: Path = self.settings.DATASETS_STORAGE_DIR
        self.runs_dir: Path = self.settings.RUNS_STORAGE_DIR
        self.active_dataset_id: str = self.settings.DEFAULT_DATASET_ID
        self.start_time: float = time.time()
        self.initialize_default_dataset()

    def initialize_default_dataset(self) -> None:
        """Register the bundled case-study dataset as the default dataset if not already present."""
        default_dir = self.datasets_dir / self.settings.DEFAULT_DATASET_ID
        default_dir.mkdir(parents=True, exist_ok=True)
        meta_file = default_dir / "metadata.json"

        shipments_src = self.settings.SHIPMENTS_FILE
        notes_src = self.settings.NOTES_FILE

        if not meta_file.exists() and shipments_src.exists():
            with open(shipments_src, "r", encoding="utf-8") as f:
                shipment_text = f.read()
            chash = compute_sha256(shipment_text)

            shutil.copy2(shipments_src, default_dir / "shipment_records.csv")
            has_notes = False
            notes_count = 0
            if notes_src.exists():
                shutil.copy2(notes_src, default_dir / "context_notes.csv")
                notes = load_context_notes(notes_src)
                has_notes = True
                notes_count = len(notes)

            df, _ = load_shipments(shipments_src)

            meta = DatasetMetadata(
                dataset_id=self.settings.DEFAULT_DATASET_ID,
                name="Bundled Shipment Records (Default)",
                content_hash=chash,
                shipment_count=len(df),
                route_count=int(df["route"].nunique()),
                date_min=df["shipment_date"].min().strftime("%Y-%m-%d"),
                date_max=df["shipment_date"].max().strftime("%Y-%m-%d"),
                has_notes=has_notes,
                notes_count=notes_count,
                created_at=datetime.now(timezone.utc).isoformat(),
                is_active=True,
            )
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta.model_dump(), f, indent=2)

    def list_datasets(self) -> List[DatasetMetadata]:
        """List all available stored datasets."""
        datasets: List[DatasetMetadata] = []
        for d in self.datasets_dir.iterdir():
            if d.is_dir() and (d / "metadata.json").exists():
                try:
                    with open(d / "metadata.json", "r", encoding="utf-8") as f:
                        data = json.load(f)
                        data["is_active"] = (data["dataset_id"] == self.active_dataset_id)
                        datasets.append(DatasetMetadata(**data))
                except Exception:
                    continue
        datasets.sort(key=lambda x: (x.dataset_id != self.active_dataset_id, x.name))
        return datasets

    def get_dataset_metadata(self, dataset_id: str) -> DatasetMetadata:
        """Retrieve metadata for a specific dataset."""
        safe_id = sanitize_safe_id(dataset_id, "dataset_id")
        meta_file = self.datasets_dir / safe_id / "metadata.json"
        if not meta_file.exists():
            raise EntityNotFoundException("Dataset", dataset_id)

        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["is_active"] = (safe_id == self.active_dataset_id)
            return DatasetMetadata(**data)

    def get_dataset(
        self, dataset_id: Optional[str] = None
    ) -> Tuple[pd.DataFrame, List[ContextNote], DatasetMetadata]:
        """Load shipment records and context notes for a dataset."""
        target_id = sanitize_safe_id(dataset_id or self.active_dataset_id, "dataset_id")
        ds_dir = self.datasets_dir / target_id
        if not ds_dir.exists():
            raise EntityNotFoundException("Dataset", target_id)

        shipments_file = ds_dir / "shipment_records.csv"
        notes_file = ds_dir / "context_notes.csv"

        df, _ = load_shipments(shipments_file)
        notes = load_context_notes(notes_file) if notes_file.exists() else []
        meta = self.get_dataset_metadata(target_id)
        return df, notes, meta

    def save_dataset(
        self,
        name: str,
        shipment_content: str,
        notes_content: Optional[str] = None,
        set_active: bool = False,
    ) -> DatasetMetadata:
        """Save a new dataset from raw text content."""
        chash = compute_sha256(shipment_content)
        dataset_id = f"ds_{chash[:12]}"

        ds_dir = self.datasets_dir / dataset_id
        ds_dir.mkdir(parents=True, exist_ok=True)

        shipments_file = ds_dir / "shipment_records.csv"
        with open(shipments_file, "w", encoding="utf-8") as f:
            f.write(shipment_content)

        has_notes = False
        notes_count = 0
        if notes_content and notes_content.strip():
            notes_file = ds_dir / "context_notes.csv"
            with open(notes_file, "w", encoding="utf-8") as f:
                f.write(notes_content)
            notes = load_context_notes(notes_file)
            has_notes = True
            notes_count = len(notes)

        df, _ = load_shipments(shipments_file)

        meta = DatasetMetadata(
            dataset_id=dataset_id,
            name=name.strip(),
            content_hash=chash,
            shipment_count=len(df),
            route_count=int(df["route"].nunique()),
            date_min=df["shipment_date"].min().strftime("%Y-%m-%d"),
            date_max=df["shipment_date"].max().strftime("%Y-%m-%d"),
            has_notes=has_notes,
            notes_count=notes_count,
            created_at=datetime.now(timezone.utc).isoformat(),
            is_active=set_active,
        )
        with open(ds_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta.model_dump(), f, indent=2)

        if set_active:
            self.active_dataset_id = dataset_id

        return meta

    def save_run(
        self,
        run_id: str,
        dataset_id: str,
        config: Dict[str, Any],
        analysis_df: pd.DataFrame,
        contract_df: pd.DataFrame,
        execution_time_ms: float,
    ) -> Dict[str, Any]:
        """Persist analysis run metadata, full dataframe JSON, and contract CSV."""
        safe_id = sanitize_safe_id(run_id, "run_id")
        run_dir = self.runs_dir / safe_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 1. Export contract CSV with strict quoting
        csv_file = run_dir / "export.csv"
        contract_df.to_csv(csv_file, index=False, quoting=csv.QUOTE_MINIMAL, encoding="utf-8")

        # 2. Persist full analysis dataframe as JSON
        results_file = run_dir / "results.json"
        analysis_df.to_json(results_file, orient="records", date_format="iso")

        flagged_count = int(analysis_df["flagged"].sum())
        justified_count = int((analysis_df["flagged_label"] == "No (justified)").sum())
        unexplained_count = int((analysis_df["flagged_label"] == "Yes").sum())
        avg_cost = float(analysis_df["cost_per_tonne_km"].mean())

        metadata = {
            "run_id": safe_id,
            "dataset_id": dataset_id,
            "status": "COMPLETED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "execution_time_ms": execution_time_ms,
            "configuration": config,
            "metrics": {
                "total_route_weeks": len(analysis_df),
                "flagged_total": flagged_count,
                "justified_count": justified_count,
                "unexplained_count": unexplained_count,
                "avg_cost_per_tonne_km": round(avg_cost, settings.FLOAT_PRECISION),
                "unique_routes": int(analysis_df["route"].nunique()),
            },
        }

        with open(run_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    def get_run_metadata(self, run_id: str) -> Dict[str, Any]:
        """Fetch metadata for an analysis run."""
        safe_id = sanitize_safe_id(run_id, "run_id")
        meta_file = self.runs_dir / safe_id / "metadata.json"
        if not meta_file.exists():
            raise EntityNotFoundException("Analysis Run", run_id)
        with open(meta_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_runs(self) -> List[Dict[str, Any]]:
        """List all analysis runs ordered by creation time descending."""
        runs: List[Dict[str, Any]] = []
        for d in self.runs_dir.iterdir():
            if d.is_dir() and (d / "metadata.json").exists():
                try:
                    with open(d / "metadata.json", "r", encoding="utf-8") as f:
                        runs.append(json.load(f))
                except Exception:
                    continue
        runs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return runs

    def get_run_results_df(self, run_id: str) -> pd.DataFrame:
        """Load the analytical records DataFrame for a run."""
        safe_id = sanitize_safe_id(run_id, "run_id")
        res_file = self.runs_dir / safe_id / "results.json"
        if not res_file.exists():
            raise EntityNotFoundException("Analysis Run Results", run_id)
        return pd.read_json(res_file, orient="records")

    def get_run_contract_df(self, run_id: str) -> pd.DataFrame:
        """Load the 8-column contract DataFrame for a run."""
        safe_id = sanitize_safe_id(run_id, "run_id")
        csv_file = self.runs_dir / safe_id / "export.csv"
        if not csv_file.exists():
            raise EntityNotFoundException("Analysis Run Contract", run_id)
        return pd.read_csv(csv_file, dtype={"matched_note_id": str}).fillna({"matched_note_id": ""})

    def get_latest_run_id(self) -> Optional[str]:
        """Get the ID of the most recent analysis run."""
        runs = self.list_runs()
        return runs[0]["run_id"] if runs else None


# Global singleton storage manager
storage = StorageManager()
