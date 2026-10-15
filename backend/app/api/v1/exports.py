"""CSV export endpoints strictly formatted per RFC-4180 and case-study specifications."""

from __future__ import annotations

import csv
import io
from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import Response

from backend.app.core.exceptions import EntityNotFoundException
from backend.app.core.middleware import sanitize_safe_id
from backend.app.services.storage import storage

router = APIRouter(tags=["CSV Data Exports"])


@router.get("/analysis/runs/{run_id}/export.csv", summary="Export Case-Study Contract CSV")
def export_run_contract_csv(run_id: str) -> Response:
    """Download the exact eight-column case-study contract CSV.

    Columns:
        route, week_of, cost_per_tonne_km, vs_own_history, vs_similar_routes,
        flagged, matched_note_id, reason
    """
    if run_id == "latest":
        latest_id = storage.get_latest_run_id()
        if not latest_id:
            from backend.app.api.v1.dashboard import get_or_create_active_run_df
            _, meta = get_or_create_active_run_df()
            latest_id = meta.get("run_id") if isinstance(meta, dict) else getattr(meta, "run_id", None)
        if not latest_id:
            raise EntityNotFoundException("Analysis Run", "latest")
        safe_id = sanitize_safe_id(latest_id, "run_id")
    else:
        safe_id = sanitize_safe_id(run_id, "run_id")

    contract_df = storage.get_run_contract_df(safe_id)

    output = io.StringIO()
    contract_df.to_csv(output, index=False, quoting=csv.QUOTE_MINIMAL)
    csv_bytes = output.getvalue().encode("utf-8")

    filename = f"freight_analysis_{safe_id}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/shipments/export.csv", summary="Export Filtered Shipments CSV")
def export_shipments_csv(
    route: Optional[str] = Query(None),
    route_type: Optional[str] = Query(None),
) -> Response:
    """Download shipment records as CSV."""
    df, _, _ = storage.get_dataset()

    if route and route.strip():
        df = df[df["route"].str.lower() == route.strip().lower()]
    if route_type and route_type.strip():
        df = df[df["route_type"].str.lower() == route_type.strip().lower()]

    output = io.StringIO()
    df.to_csv(output, index=False, quoting=csv.QUOTE_MINIMAL)
    csv_bytes = output.getvalue().encode("utf-8")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="shipment_records.csv"'},
    )


@router.get("/anomalies/export.csv", summary="Export Anomalies CSV")
def export_anomalies_csv(
    flagged_only: bool = Query(True),
    evidence: Optional[str] = Query("all"),
) -> Response:
    """Download anomaly monitor records as CSV."""
    from backend.app.api.v1.dashboard import get_or_create_active_run_df
    df, meta = get_or_create_active_run_df()

    if flagged_only:
        df = df[df["flagged"] == True]
    if evidence == "supported":
        df = df[df["flagged_label"] == "No (justified)"]
    elif evidence == "unexplained":
        df = df[df["flagged_label"] == "Yes"]

    output = io.StringIO()
    df.to_csv(output, index=False, quoting=csv.QUOTE_MINIMAL)
    csv_bytes = output.getvalue().encode("utf-8")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="flagged_anomalies.csv"'},
    )
