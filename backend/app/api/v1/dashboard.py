"""Dashboard overview, route analytics, and weekly timeline endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, Query

from backend.app.core.config import settings
from backend.app.core.exceptions import EntityNotFoundException
from backend.app.core.middleware import sanitize_safe_id
from backend.app.services.aggregation import aggregate_weekly_routes
from backend.app.services.anomaly_detection import AnomalyDetector
from backend.app.services.cost_analysis import compute_route_baselines
from backend.app.services.storage import storage

router = APIRouter(tags=["Dashboard & Analytics"])


def get_or_create_active_run_df() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Ensure at least one analysis run exists and return its dataframe and metadata."""
    latest_id = storage.get_latest_run_id()
    if latest_id:
        try:
            return storage.get_run_results_df(latest_id), storage.get_run_metadata(latest_id)
        except Exception:
            pass

    # Automatically initialize first baseline run on default dataset
    shipments_df, notes, meta = storage.get_dataset()
    weekly = aggregate_weekly_routes(shipments_df)
    weekly_baselines = compute_route_baselines(weekly, max_history_weeks=settings.MAX_HISTORICAL_WEEKS)
    detector = AnomalyDetector(
        threshold_pct=settings.DEFAULT_ANOMALY_THRESHOLD_PCT,
        note_window_days=settings.NOTE_DATE_WINDOW_DAYS,
    )
    analysis_df, analysis_records = detector.detect_anomalies(weekly_baselines, notes)
    contract_df = detector.format_output_contract(analysis_records)

    run_meta = storage.save_run(
        run_id="run_baseline_initial",
        dataset_id=storage.active_dataset_id,
        config={
            "threshold_pct": settings.DEFAULT_ANOMALY_THRESHOLD_PCT,
            "max_history_weeks": settings.MAX_HISTORICAL_WEEKS,
            "note_window_days": settings.NOTE_DATE_WINDOW_DAYS,
        },
        analysis_df=analysis_df,
        contract_df=contract_df,
        execution_time_ms=0.0,
    )
    return analysis_df, run_meta


@router.get("/dashboard/summary", summary="Get Dashboard Overview KPIs")
def get_dashboard_summary() -> Dict[str, Any]:
    """Retrieve operational KPIs, route-type comparison, and top anomalies."""
    df, meta = get_or_create_active_run_df()
    shipments_df, _, ds_meta = storage.get_dataset(meta["dataset_id"])

    flagged_df = df[df["flagged"] == True]
    justified_df = df[df["flagged_label"] == "No (justified)"]
    unexplained_df = df[df["flagged_label"] == "Yes"]

    # Top anomalies
    top_anomalies = []
    if not flagged_df.empty:
        sorted_top = flagged_df.sort_values(by="pct_vs_history", ascending=False).head(6)
        for _, r in sorted_top.iterrows():
            top_anomalies.append({
                "id": f"{r['route']}-{str(r['week_of'])[:10]}",
                "route": r["route"],
                "route_type": r["route_type"],
                "week_of": str(r["week_of"])[:10],
                "cost_per_tonne_km": round(float(r["cost_per_tonne_km"]), 4),
                "vs_own_history": round(float(r["vs_own_history"]), 4) if pd.notnull(r["vs_own_history"]) else None,
                "pct_vs_history": round(float(r["pct_vs_history"]), 1) if pd.notnull(r["pct_vs_history"]) else None,
                "verdict": "Supported" if r["flagged_label"] == "No (justified)" else "Unexplained",
                "matched_note_id": r.get("matched_note_id", ""),
            })

    # Route type distribution
    type_stats = []
    for rt in ["Short", "Medium", "Long"]:
        grp = df[df["route_type"] == rt]
        if not grp.empty:
            type_stats.append({
                "route_type": rt,
                "route_weeks": len(grp),
                "avg_cost_per_tonne_km": round(float(grp["cost_per_tonne_km"].mean()), 3),
            })

    return {
        "dataset_name": ds_meta.name,
        "total_shipments": len(shipments_df),
        "total_routes": int(df["route"].nunique()),
        "total_route_weeks": len(df),
        "flagged_route_weeks": len(flagged_df),
        "unexplained_anomalies": len(unexplained_df),
        "evidence_supported": len(justified_df),
        "avg_cost_per_tonne_km": round(float(df["cost_per_tonne_km"].mean()), 3),
        "route_type_comparison": type_stats,
        "recent_anomalies": top_anomalies,
    }


@router.get("/analytics/weekly-costs", summary="Weekly Freight Cost Trend")
def get_weekly_costs(
    route: Optional[str] = Query(None, description="Filter by canonical route"),
    route_type: Optional[str] = Query(None, description="Filter by route type"),
    limit: Optional[int] = Query(None, ge=1, le=104, description="Limit to last N weeks"),
) -> List[Dict[str, Any]]:
    """Retrieve time-series trend of average freight cost per tonne-km."""
    df, _ = get_or_create_active_run_df()

    if route and route.strip():
        df = df[df["route"].str.lower() == route.strip().lower()]
    if route_type and route_type.strip():
        df = df[df["route_type"].str.lower() == route_type.strip().lower()]

    weekly = (
        df.groupby("week_of", as_index=False)
        .agg(
            avg_cost=("cost_per_tonne_km", "mean"),
            route_weeks=("route", "count"),
            flagged_count=("flagged", "sum"),
        )
        .sort_values("week_of")
    )

    if limit:
        weekly = weekly.tail(limit)

    results = []
    for _, r in weekly.iterrows():
        results.append({
            "week_of": str(r["week_of"])[:10],
            "cost_per_tonne_km": round(float(r["avg_cost"]), 4),
            "route_weeks": int(r["route_weeks"]),
            "flagged_count": int(r["flagged_count"]),
        })
    return results


@router.get("/analytics/routes", summary="List All Analyzed Routes")
def list_routes() -> List[Dict[str, Any]]:
    """List summary statistics for each origin-destination route."""
    df, meta = get_or_create_active_run_df()
    shipments_df, _, _ = storage.get_dataset(meta["dataset_id"])

    route_summaries = []
    for r_name, grp in df.groupby("route"):
        s_grp = shipments_df[shipments_df["route"] == r_name]
        r_type = grp["route_type"].iloc[0]
        avg_cost = grp["cost_per_tonne_km"].mean()
        flagged_count = int(grp["flagged"].sum())
        latest_week = grp.sort_values("week_of").iloc[-1]

        route_summaries.append({
            "route": r_name,
            "origin": r_name.split("-")[0],
            "destination": r_name.split("-")[1],
            "route_type": r_type,
            "total_shipments": len(s_grp),
            "avg_distance_km": round(float(s_grp["distance_km"].mean()), 1) if not s_grp.empty else None,
            "avg_cost_per_tonne_km": round(float(avg_cost), 4),
            "flagged_weeks_count": flagged_count,
            "latest_week": str(latest_week["week_of"])[:10],
            "latest_cost": round(float(latest_week["cost_per_tonne_km"]), 4),
        })

    route_summaries.sort(key=lambda x: x["route"])
    return route_summaries


@router.get("/analytics/routes/{route_id}", summary="Get Single Route Timeline and Metrics")
def get_route_timeline(route_id: str) -> Dict[str, Any]:
    """Retrieve full chronological timeline and baseline details for a route."""
    clean_route = sanitize_safe_id(route_id, "route_id").lower()
    df, meta = get_or_create_active_run_df()

    matched = df[df["route"].str.lower() == clean_route].sort_values("week_of")
    if matched.empty:
        raise EntityNotFoundException("Route", route_id)

    canonical_name = matched["route"].iloc[0]
    r_type = matched["route_type"].iloc[0]

    timeline = []
    for _, r in matched.iterrows():
        timeline.append({
            "week_of": str(r["week_of"])[:10],
            "cost_per_tonne_km": round(float(r["cost_per_tonne_km"]), 4),
            "vs_own_history": round(float(r["vs_own_history"]), 4) if pd.notnull(r["vs_own_history"]) else None,
            "vs_similar_routes": round(float(r["vs_similar_routes"]), 4) if pd.notnull(r["vs_similar_routes"]) else None,
            "pct_vs_history": round(float(r["pct_vs_history"]), 1) if pd.notnull(r["pct_vs_history"]) else None,
            "pct_vs_peers": round(float(r["pct_vs_peers"]), 1) if pd.notnull(r["pct_vs_peers"]) else None,
            "flagged": bool(r["flagged"]),
            "verdict": r["flagged_label"],
            "matched_note_id": r.get("matched_note_id", ""),
            "reason": r.get("reason", ""),
        })

    return {
        "route": canonical_name,
        "origin": canonical_name.split("-")[0],
        "destination": canonical_name.split("-")[1],
        "route_type": r_type,
        "total_weeks": len(matched),
        "avg_cost_per_tonne_km": round(float(matched["cost_per_tonne_km"].mean()), 4),
        "total_flagged": int(matched["flagged"].sum()),
        "timeline": timeline,
    }
