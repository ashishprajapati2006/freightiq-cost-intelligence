"""Health, system readiness, metadata, and dataset discovery endpoints."""

from __future__ import annotations

import time
from typing import List
from fastapi import APIRouter

from backend.app.core.config import settings
from backend.app.schemas.api import AppMetadataResponse, HealthResponse
from backend.app.schemas.dataset import DatasetMetadata
from backend.app.services.storage import storage

router = APIRouter(tags=["Health & Metadata"])


@router.get("/health", response_model=HealthResponse, summary="System Health and Readiness")
def get_health() -> HealthResponse:
    """Check application availability, dataset readiness, and analysis engine status."""
    try:
        active_meta = storage.get_dataset_metadata(storage.active_dataset_id)
        ready = True
        status = "healthy"
        shipments_count = active_meta.shipment_count
        routes_count = active_meta.route_count
        notes_count = active_meta.notes_count
    except Exception:
        ready = False
        status = "degraded"
        shipments_count = 0
        routes_count = 0
        notes_count = 0

    uptime = time.time() - storage.start_time

    return HealthResponse(
        status=status,
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        analysis_engine_ready=ready,
        active_dataset_id=storage.active_dataset_id,
        total_shipments=shipments_count,
        total_routes=routes_count,
        total_context_notes=notes_count,
        uptime_seconds=round(uptime, 2),
    )


@router.get("/metadata", response_model=AppMetadataResponse, summary="Application Operational Metadata")
def get_metadata() -> AppMetadataResponse:
    """Retrieve operational parameters, column contracts, and constraints."""
    return AppMetadataResponse(
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        api_version="v1",
        case_study_contract_columns=settings.OUTPUT_COLUMNS,
        route_types=sorted(list(settings.VALID_ROUTE_TYPES)),
        default_threshold_pct=settings.DEFAULT_ANOMALY_THRESHOLD_PCT,
        max_history_weeks=settings.MAX_HISTORICAL_WEEKS,
        note_window_days=settings.NOTE_DATE_WINDOW_DAYS,
        canonical_route_example="Mumbai-Pune",
    )


@router.get("/datasets", response_model=List[DatasetMetadata], summary="List Available Datasets")
def list_datasets() -> List[DatasetMetadata]:
    """Retrieve all stored datasets with content hashes and summary metrics."""
    return storage.list_datasets()


@router.get("/datasets/{dataset_id}", response_model=DatasetMetadata, summary="Get Dataset Details")
def get_dataset(dataset_id: str) -> DatasetMetadata:
    """Retrieve metadata for a specific dataset."""
    return storage.get_dataset_metadata(dataset_id)
