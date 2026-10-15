"""Standard envelope, pagination, health, and error schemas."""

from __future__ import annotations

from typing import Any, Generic, List, Literal, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for pagination and safe sorting."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=25, ge=1, le=500, description="Items per page")
    sort_by: Optional[str] = Field(default=None, description="Field name to sort by")
    sort_dir: Literal["asc", "desc"] = Field(default="asc", description="Sort direction")


class PaginationMeta(BaseModel):
    """Pagination metadata included in paginated responses."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """Standardized generic paginated envelope."""

    items: List[T]
    pagination: PaginationMeta


class HealthResponse(BaseModel):
    """System health and readiness status."""

    status: Literal["healthy", "degraded", "unhealthy"]
    app: str
    version: str
    analysis_engine_ready: bool
    active_dataset_id: str
    total_shipments: int
    total_routes: int
    total_context_notes: int
    uptime_seconds: float


class AppMetadataResponse(BaseModel):
    """System metadata and case-study operational constraints."""

    app_name: str
    version: str
    api_version: str
    case_study_contract_columns: List[str]
    route_types: List[str]
    default_threshold_pct: float
    max_history_weeks: int
    note_window_days: int
    canonical_route_example: str


class ErrorDetail(BaseModel):
    """Structured error descriptor."""

    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Standard error response format for all 4xx and 5xx errors."""

    error: ErrorDetail
    request_id: Optional[str] = None
