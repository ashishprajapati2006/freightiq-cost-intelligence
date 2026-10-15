"""Analysis execution, run history, and analytical results endpoints."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.app.core.config import settings
from backend.app.core.exceptions import EntityNotFoundException, ValidationException
from backend.app.core.middleware import sanitize_safe_id
from backend.app.schemas.api import PaginatedResponse, PaginationMeta
from backend.app.services.aggregation import aggregate_weekly_routes
from backend.app.services.anomaly_detection import AnomalyDetector
from backend.app.services.cost_analysis import compute_route_baselines
from backend.app.services.storage import storage

router = APIRouter(prefix="/analysis", tags=["Analysis Engine"])


class RunAnalysisRequest(BaseModel):
    """Configuration payload to trigger an analytical run."""

    dataset_id: Optional[str] = Field(None, description="Dataset identifier (defaults to active dataset)")
    threshold_pct: float = Field(default=20.0, ge=1.0, le=500.0, description="Anomaly deviation threshold percentage")
    max_history_weeks: int = Field(default=8, ge=1, le=52, description="Maximum historical trailing weeks")
    note_window_days: int = Field(default=42, ge=1, le=365, description="Context note matching window in days")


@router.post("/run", summary="Trigger Full Deterministic Analysis Run")
def trigger_analysis(request: RunAnalysisRequest) -> Dict[str, Any]:
    """Execute the end-to-end analytical pipeline on specified dataset."""
    start_time = time.perf_counter()
    target_dataset_id = sanitize_safe_id(request.dataset_id or storage.active_dataset_id, "dataset_id")

    shipments_df, notes, _ = storage.get_dataset(target_dataset_id)
    if shipments_df.empty:
        raise ValidationException("Selected dataset contains no shipment records.")

    # 1. Weekly aggregation
    weekly = aggregate_weekly_routes(shipments_df)

    # 2. Historical & Peer Baselines
    weekly_baselines = compute_route_baselines(weekly, max_history_weeks=request.max_history_weeks)

    # 3. Anomaly Detection & Note Evidence Matching
    detector = AnomalyDetector(
        threshold_pct=request.threshold_pct,
        note_window_days=request.note_window_days,
    )
    analysis_df, analysis_records = detector.detect_anomalies(weekly_baselines, notes)

    # 4. Canonical 8-Column Contract
    contract_df = detector.format_output_contract(analysis_records)

    duration_ms = (time.perf_counter() - start_time) * 1000.0
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    config = {
        "threshold_pct": request.threshold_pct,
        "max_history_weeks": request.max_history_weeks,
        "note_window_days": request.note_window_days,
    }

    run_meta = storage.save_run(
        run_id=run_id,
        dataset_id=target_dataset_id,
        config=config,
        analysis_df=analysis_df,
        contract_df=contract_df,
        execution_time_ms=round(duration_ms, 2),
    )
    return run_meta


@router.get("/runs", summary="List Historical Analysis Runs")
def list_analysis_runs() -> List[Dict[str, Any]]:
    """List all previous analysis runs sorted by timestamp descending."""
    return storage.list_runs()


@router.get("/runs/{run_id}", summary="Get Analysis Run Metadata")
def get_analysis_run(run_id: str) -> Dict[str, Any]:
    """Retrieve metadata, configuration, and status for a specific run."""
    return storage.get_run_metadata(run_id)


@router.get("/runs/{run_id}/metrics", summary="Get High-Level Run Metrics")
def get_run_metrics(run_id: str) -> Dict[str, Any]:
    """Retrieve aggregated summary metrics and distribution breakdowns for a run."""
    meta = storage.get_run_metadata(run_id)
    df = storage.get_run_results_df(run_id)

    by_type = {}
    for rt, grp in df.groupby("route_type"):
        by_type[rt] = {
            "route_weeks": len(grp),
            "avg_cost_per_tonne_km": round(float(grp["cost_per_tonne_km"].mean()), 4),
            "flagged_count": int(grp["flagged"].sum()),
        }

    # Top deviations
    flagged_df = df[df["flagged"] == True]
    top_devs = []
    if not flagged_df.empty:
        sorted_anoms = flagged_df.sort_values(by="pct_vs_history", ascending=False).head(5)
        for _, r in sorted_anoms.iterrows():
            top_devs.append({
                "route": r["route"],
                "week_of": str(r["week_of"])[:10],
                "cost_per_tonne_km": round(float(r["cost_per_tonne_km"]), 4),
                "pct_vs_history": round(float(r["pct_vs_history"]), 1) if pd.notnull(r["pct_vs_history"]) else None,
                "pct_vs_peers": round(float(r["pct_vs_peers"]), 1) if pd.notnull(r["pct_vs_peers"]) else None,
                "verdict": r["flagged_label"],
                "matched_note_id": r.get("matched_note_id", ""),
            })

    return {
        "run_id": meta["run_id"],
        "dataset_id": meta["dataset_id"],
        "metrics": meta["metrics"],
        "by_route_type": by_type,
        "top_deviations": top_devs,
    }


ALLOWED_SORT_FIELDS = {
    "week_of",
    "route",
    "route_type",
    "cost_per_tonne_km",
    "pct_vs_history",
    "pct_vs_peers",
    "flagged",
    "vs_own_history",
    "vs_similar_routes",
}


@router.get("/runs/{run_id}/results", response_model=PaginatedResponse[Dict[str, Any]], summary="Get Paginated Run Results")
def get_run_results(
    run_id: str,
    route: Optional[str] = Query(None, description="Filter by canonical route"),
    route_type: Optional[str] = Query(None, description="Filter by route type"),
    flagged: Optional[str] = Query("all", description="'all', 'flagged', 'clear'"),
    evidence: Optional[str] = Query("all", description="'all', 'supported', 'unexplained'"),
    search: Optional[str] = Query(None, description="Search route or note ID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    sort_by: Optional[str] = Query("week_of"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
) -> PaginatedResponse[Dict[str, Any]]:
    """Retrieve filtered, paginated analytical records for a specific run."""
    df = storage.get_run_results_df(run_id)

    # 1. Filters
    if route and route.strip():
        df = df[df["route"].str.lower() == route.strip().lower()]
    if route_type and route_type.strip():
        df = df[df["route_type"].str.lower() == route_type.strip().lower()]
    if flagged == "flagged":
        df = df[df["flagged"] == True]
    elif flagged == "clear":
        df = df[df["flagged"] == False]

    if evidence == "supported":
        df = df[df["flagged_label"] == "No (justified)"]
    elif evidence == "unexplained":
        df = df[df["flagged_label"] == "Yes"]

    if search and search.strip():
        q = search.strip().lower()
        df = df[
            df["route"].str.lower().str.contains(q, na=False)
            | df["matched_note_id"].str.lower().str.contains(q, na=False)
            | df["reason"].str.lower().str.contains(q, na=False)
        ]

    # 2. Sorting
    if sort_by:
        safe_sort = sort_by.strip()
        if safe_sort not in ALLOWED_SORT_FIELDS:
            raise ValidationException(f"Invalid sort field '{sort_by}'. Allowed fields: {sorted(list(ALLOWED_SORT_FIELDS))}")
        ascending = (sort_dir.lower() == "asc")
        df = df.sort_values(by=safe_sort, ascending=ascending, na_position="last")

    # 3. Pagination
    total_items = len(df)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = min(page, total_pages)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_slice = df.iloc[start_idx:end_idx].copy()

    # Clean dates and nans for JSON output
    records = []
    for _, r in page_slice.iterrows():
        rec = r.to_dict()
        rec["week_of"] = str(rec["week_of"])[:10]
        # Clean NaNs to None
        for k, v in rec.items():
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                rec[k] = None
        records.append(rec)

    return PaginatedResponse(
        items=records,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )
