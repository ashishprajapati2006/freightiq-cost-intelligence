"""Granular shipment records explorer and detail endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, Query

from backend.app.core.exceptions import EntityNotFoundException, ValidationException
from backend.app.core.middleware import sanitize_safe_id
from backend.app.schemas.api import PaginatedResponse, PaginationMeta
from backend.app.services.storage import storage

router = APIRouter(prefix="/shipments", tags=["Shipment Explorer"])

ALLOWED_SHIPMENT_SORT = {
    "shipment_id",
    "shipment_date",
    "origin",
    "destination",
    "route_type",
    "material",
    "quantity_tonnes",
    "distance_km",
    "freight_cost_inr",
    "transporter",
}


@router.get("", response_model=PaginatedResponse[Dict[str, Any]], summary="Paginated Shipment Explorer")
def get_shipments(
    search: Optional[str] = Query(None, description="Search route, shipment ID, or material"),
    route: Optional[str] = Query(None, description="Filter by canonical route"),
    route_type: Optional[str] = Query(None, description="Filter by route type (Short, Medium, Long)"),
    origin: Optional[str] = Query(None, description="Filter by origin city"),
    destination: Optional[str] = Query(None, description="Filter by destination city"),
    material: Optional[str] = Query(None, description="Filter by material"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    sort_by: str = Query("shipment_date"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
) -> PaginatedResponse[Dict[str, Any]]:
    """Retrieve filtered, paginated shipment records from the active dataset."""
    df, _, _ = storage.get_dataset()

    # 1. Filters
    if route and route.strip():
        df = df[df["route"].str.lower() == route.strip().lower()]
    if route_type and route_type.strip():
        df = df[df["route_type"].str.lower() == route_type.strip().lower()]
    if origin and origin.strip():
        df = df[df["origin"].str.lower() == origin.strip().lower()]
    if destination and destination.strip():
        df = df[df["destination"].str.lower() == destination.strip().lower()]
    if material and material.strip():
        df = df[df["material"].str.lower() == material.strip().lower()]

    if search and search.strip():
        q = search.strip().lower()
        df = df[
            df["shipment_id"].str.lower().str.contains(q, na=False)
            | df["route"].str.lower().str.contains(q, na=False)
            | df["material"].str.lower().str.contains(q, na=False)
            | df["transporter"].str.lower().str.contains(q, na=False)
        ]

    # 2. Sorting
    safe_sort = sort_by.strip()
    if safe_sort not in ALLOWED_SHIPMENT_SORT:
        raise ValidationException(
            f"Invalid sort field '{sort_by}'. Allowed fields: {sorted(list(ALLOWED_SHIPMENT_SORT))}"
        )
    ascending = (sort_dir.lower() == "asc")
    df = df.sort_values(by=safe_sort, ascending=ascending)

    # 3. Pagination
    total_items = len(df)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    page = min(page, total_pages)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_slice = df.iloc[start_idx:end_idx].copy()

    records = []
    for _, r in page_slice.iterrows():
        rec = r.to_dict()
        rec["shipment_date"] = str(rec["shipment_date"])[:10]
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


@router.get("/{shipment_id}", summary="Get Shipment Detail")
def get_shipment_by_id(shipment_id: str) -> Dict[str, Any]:
    """Retrieve complete record for a single shipment ID."""
    safe_id = sanitize_safe_id(shipment_id, "shipment_id").upper()
    df, _, _ = storage.get_dataset()

    matched = df[df["shipment_id"].str.upper() == safe_id]
    if matched.empty:
        raise EntityNotFoundException("Shipment", shipment_id)

    row = matched.iloc[0].to_dict()
    row["shipment_date"] = str(row["shipment_date"])[:10]
    return row
