"""Context notes exploration, impact classification, and related cases endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from backend.app.core.exceptions import EntityNotFoundException
from backend.app.core.middleware import sanitize_safe_id
from backend.app.services.storage import storage

router = APIRouter(prefix="/context-notes", tags=["Context Notes Evidence"])


@router.get("", summary="List All Context Notes")
def list_context_notes(
    search: Optional[str] = Query(None, description="Search note text or ID"),
    scope: Optional[str] = Query(None, description="Filter by corridor route scope"),
) -> List[Dict[str, Any]]:
    """Retrieve all qualitative context notes with route applicability and impact classification."""
    _, notes, _ = storage.get_dataset()

    results = []
    for n in notes:
        if scope and scope.strip():
            if n.applies_to.lower() != scope.strip().lower() and n.applies_to.lower() != "all routes":
                continue

        if search and search.strip():
            q = search.strip().lower()
            if q not in n.note_id.lower() and q not in n.note.lower() and q not in n.applies_to.lower():
                continue

        results.append({
            "note_id": n.note_id,
            "date": n.date.strftime("%Y-%m-%d"),
            "applies_to": n.applies_to,
            "note": n.note,
            "is_cost_driver": n.is_cost_driver,
        })

    results.sort(key=lambda x: x["date"], reverse=True)
    return results


@router.get("/{note_id}", summary="Get Single Context Note and Related Anomalies")
def get_context_note(note_id: str) -> Dict[str, Any]:
    """Retrieve note details, guardrail classification, and any associated anomaly cases."""
    safe_id = sanitize_safe_id(note_id, "note_id").upper()
    _, notes, _ = storage.get_dataset()

    matched = next((n for n in notes if n.note_id.upper() == safe_id), None)
    if not matched:
        raise EntityNotFoundException("Context Note", note_id)

    # Check for route-weeks where this note was matched
    from backend.app.api.v1.dashboard import get_or_create_active_run_df
    df, _ = get_or_create_active_run_df()

    related_weeks = []
    matched_cases = df[df["matched_note_id"].str.upper() == safe_id]
    for _, r in matched_cases.iterrows():
        related_weeks.append({
            "id": f"{r['route']}-{str(r['week_of'])[:10]}",
            "route": r["route"],
            "week_of": str(r["week_of"])[:10],
            "cost_per_tonne_km": round(float(r["cost_per_tonne_km"]), 4),
            "pct_vs_history": round(float(r["pct_vs_history"]), 1) if pd.notnull(r["pct_vs_history"]) else None,
            "verdict": r["flagged_label"],
        })

    return {
        "note_id": matched.note_id,
        "date": matched.date.strftime("%Y-%m-%d"),
        "applies_to": matched.applies_to,
        "note": matched.note,
        "is_cost_driver": matched.is_cost_driver,
        "related_cases_count": len(related_weeks),
        "related_cases": related_weeks,
    }
