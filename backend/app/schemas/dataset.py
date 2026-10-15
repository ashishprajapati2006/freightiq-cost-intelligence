"""Pydantic schemas for dataset management and upload validation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DatasetMetadata(BaseModel):
    """Metadata representing an available dataset."""

    dataset_id: str
    name: str
    content_hash: str
    shipment_count: int
    route_count: int
    date_min: str
    date_max: str
    has_notes: bool
    notes_count: int
    created_at: str
    is_active: bool


class DatasetValidationError(BaseModel):
    """Detailed validation issue."""

    row: Optional[int] = None
    column: Optional[str] = None
    message: str
    raw_value: Optional[str] = None


class DatasetValidationResponse(BaseModel):
    """Result of dataset validation checks."""

    is_valid: bool
    total_records: int
    valid_records: int
    invalid_records: int
    errors: List[DatasetValidationError] = Field(default_factory=list)
    null_counts: Dict[str, int] = Field(default_factory=dict)
    negative_or_zero_counts: Dict[str, int] = Field(default_factory=dict)


class DatasetImportResponse(BaseModel):
    """Response returned upon successful dataset import."""

    message: str
    dataset: DatasetMetadata
    validation: DatasetValidationResponse
