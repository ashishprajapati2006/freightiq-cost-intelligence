"""Anomaly monitoring, detailed investigation, and qualitative evidence validation endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, Query

from backend.app.core.exceptions import EntityNotFoundException, ValidationException
from backend.app.core.middleware import sanitize_safe_id
from backend.app.schemas.api import PaginatedResponse, PaginationMeta
from backend.app.services.anomaly_detection import AnomalyDetector
from backend.app.services.storage import storage

router = APIRouter(prefix="/anomalies", tags=["Anomaly Monitor & Evidence"])

ALLOWED_ANOMALY_SORT = {
    "week_of",
    "route",
    "route_type",
    "cost_per_tonne_km",
    "vs_own_history",
    "vs_similar_routes",
    "pct_vs_history",
    "pct_vs_peers",
    "flagged_label",
    "matched_note_id",
    "ml_anomaly_score",
}


def ensure_ml_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich dataframe with auxiliary ML anomaly scores without mutating core deterministic logic."""
    if "ml_anomaly_score" in df.columns and df["ml_anomaly_score"].notna().any():
        return df
    try:
        from backend.app.services.ml_features import MLFeatureEngineer
        from backend.app.services.ml_inference import inference_service

        eng = MLFeatureEngineer()
        _, X = eng.extract_features(df, is_training=False)
        preds = inference_service.score_feature_matrix(X, context_df=df)
        df["ml_anomaly_score"] = [p.ml_anomaly_score for p in preds]
        df["is_ml_anomaly"] = [p.is_ml_anomaly for p in preds]
        df["ml_score_tier"] = [p.score_tier for p in preds]
    except Exception:
        df["ml_anomaly_score"] = None
        df["is_ml_anomaly"] = None
        df["ml_score_tier"] = None
    return df


def get_active_results_df() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Helper to fetch current active run dataframe."""
    from backend.app.api.v1.dashboard import get_or_create_active_run_df
    return get_or_create_active_run_df()


@router.get("", response_model=PaginatedResponse[Dict[str, Any]], summary="Paginated Anomaly Monitor")
def get_anomalies(
    search: Optional[str] = Query(None, description="Search route or note ID"),
    route: Optional[str] = Query(None, description="Filter by canonical route"),
    route_type: Optional[str] = Query(None, description="Filter by route type (Short, Medium, Long)"),
    evidence: Optional[str] = Query("all", description="'all', 'supported', or 'unexplained'"),
    flagged: Optional[str] = Query("flagged", description="'flagged', 'all', or 'clear'"),
    min_deviation: Optional[float] = Query(0.0, ge=0.0, description="Minimum percentage deviation"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    sort_by: str = Query("pct_vs_history"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
) -> PaginatedResponse[Dict[str, Any]]:
    """Retrieve filtered, paginated route-week anomaly records."""
    df, _ = get_active_results_df()
    df = ensure_ml_scores(df)

    # Create stable record ID if not already present
    df["id"] = df.apply(lambda r: f"{r['route']}-{str(r['week_of'])[:10]}", axis=1)

    # 1. Flag filter
    if flagged == "flagged":
        df = df[df["flagged"] == True]
    elif flagged == "clear":
        df = df[df["flagged"] == False]

    # 2. Evidence status
    if evidence == "supported":
        df = df[df["flagged_label"] == "No (justified)"]
    elif evidence == "unexplained":
        df = df[df["flagged_label"] == "Yes"]

    # 3. Route & Route type
    if route and route.strip():
        df = df[df["route"].str.lower() == route.strip().lower()]
    if route_type and route_type.strip():
        df = df[df["route_type"].str.lower() == route_type.strip().lower()]

    # 4. Search
    if search and search.strip():
        q = search.strip().lower()
        df = df[
            df["route"].str.lower().str.contains(q, na=False)
            | df["matched_note_id"].str.lower().str.contains(q, na=False)
            | df["reason"].str.lower().str.contains(q, na=False)
        ]

    # 5. Min deviation
    if min_deviation and min_deviation > 0:
        max_dev = np.maximum(
            df["pct_vs_history"].fillna(-999.0),
            df["pct_vs_peers"].fillna(-999.0),
        )
        df = df[max_dev >= min_deviation]

    # 6. Sorting
    safe_sort = sort_by.strip()
    if safe_sort not in ALLOWED_ANOMALY_SORT:
        raise ValidationException(
            f"Invalid sort field '{sort_by}'. Allowed fields: {sorted(list(ALLOWED_ANOMALY_SORT))}"
        )
    ascending = (sort_dir.lower() == "asc")
    df = df.sort_values(by=safe_sort, ascending=ascending, na_position="last")

    # 7. Pagination
    total_items = len(df)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = min(page, total_pages)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_slice = df.iloc[start_idx:end_idx].copy()

    records = []
    for _, r in page_slice.iterrows():
        rec = r.to_dict()
        rec["week_of"] = str(rec["week_of"])[:10]
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


@router.get("/{anomaly_id}", summary="Get Single Anomaly Details")
def get_anomaly_detail(anomaly_id: str) -> Dict[str, Any]:
    """Retrieve full baseline and calculation details for a single route-week anomaly."""
    clean_id = sanitize_safe_id(anomaly_id, "anomaly_id")
    df, meta = get_active_results_df()
    df = ensure_ml_scores(df)
    df["id"] = df.apply(lambda r: f"{r['route']}-{str(r['week_of'])[:10]}", axis=1)

    matched = df[df["id"].str.lower() == clean_id.lower()]
    if matched.empty:
        raise EntityNotFoundException("Anomaly record", anomaly_id)

    rec = matched.iloc[0].to_dict()
    rec["week_of"] = str(rec["week_of"])[:10]
    for k, v in rec.items():
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            rec[k] = None

    return rec


@router.get("/{anomaly_id}/evidence", summary="Inspect Supporting Evidence and Guardrail Audit")
def get_anomaly_evidence(anomaly_id: str) -> Dict[str, Any]:
    """Audit the evidence decision trail, matched note, and anti-hallucination verification."""
    clean_id = sanitize_safe_id(anomaly_id, "anomaly_id")
    df, meta = get_active_results_df()
    df["id"] = df.apply(lambda r: f"{r['route']}-{str(r['week_of'])[:10]}", axis=1)

    matched = df[df["id"].str.lower() == clean_id.lower()]
    if matched.empty:
        raise EntityNotFoundException("Anomaly record", anomaly_id)

    rec = matched.iloc[0]
    route = rec["route"]
    week_str = str(rec["week_of"])[:10]

    _, notes, ds_meta = storage.get_dataset(meta["dataset_id"])
    detector = AnomalyDetector()
    justifying_note, non_justifying_note = detector.find_relevant_notes(route, week_str, notes)

    is_supported = rec["flagged_label"] == "No (justified)"
    verdict_outcome = "SUPPORTED_BY_AUTHENTIC_EVIDENCE" if is_supported else (
        "UNEXPLAINED_NO_APPLICABLE_NOTE" if rec["flagged"] else "WITHIN_BASELINE_TOLERANCE"
    )

    return {
        "anomaly_id": clean_id,
        "route": route,
        "week_of": week_str,
        "cost_per_tonne_km": round(float(rec["cost_per_tonne_km"]), 4),
        "pct_vs_history": round(float(rec["pct_vs_history"]), 1) if pd.notnull(rec["pct_vs_history"]) else None,
        "pct_vs_peers": round(float(rec["pct_vs_peers"]), 1) if pd.notnull(rec["pct_vs_peers"]) else None,
        "flagged": bool(rec["flagged"]),
        "verdict_label": rec["flagged_label"],
        "validation_outcome": verdict_outcome,
        "matched_note": justifying_note.model_dump() if justifying_note else None,
        "closest_non_justifying_note": non_justifying_note.model_dump() if non_justifying_note else None,
        "reason": rec["reason"],
        "audit": {
            "dataset_name": ds_meta.name,
            "rule_threshold": meta.get("configuration", {}).get("threshold_pct", 20.0),
            "anti_hallucination_guardrails_active": True,
            "decision_source": "Deterministic evaluation engine (no LLM hallucination)",
        },
    }
