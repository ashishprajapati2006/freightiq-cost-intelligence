"""Dataset upload, schema validation, and import endpoints."""

from __future__ import annotations

import io
from typing import Optional
import pandas as pd
from fastapi import APIRouter, File, Form, UploadFile

from backend.app.core.config import settings
from backend.app.core.data_loader import REQUIRED_SHIPMENT_COLUMNS, load_shipments
from backend.app.core.exceptions import ValidationException
from backend.app.core.middleware import sanitize_safe_id
from backend.app.schemas.dataset import (
    DatasetImportResponse,
    DatasetValidationError,
    DatasetValidationResponse,
)
from backend.app.services.storage import storage

router = APIRouter(prefix="/datasets", tags=["Dataset Ingestion & Validation"])


async def validate_raw_shipment_bytes(content: bytes) -> DatasetValidationResponse:
    """Run comprehensive schema, type, and boundary validation over uploaded shipment CSV bytes."""
    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise ValidationException(
            f"File size ({len(content)} bytes) exceeds maximum limit of {settings.MAX_UPLOAD_SIZE_BYTES} bytes."
        )

    try:
        text = content.decode("utf-8")
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:
        return DatasetValidationResponse(
            is_valid=False,
            total_records=0,
            valid_records=0,
            invalid_records=0,
            errors=[DatasetValidationError(message=f"Malformed CSV syntax: {str(e)}")],
        )

    errors: list[DatasetValidationError] = []

    # 1. Missing columns
    missing_cols = [c for c in REQUIRED_SHIPMENT_COLUMNS if c not in df.columns]
    for c in missing_cols:
        errors.append(
            DatasetValidationError(
                column=c,
                message=f"Required column '{c}' is missing from header.",
            )
        )

    if missing_cols:
        return DatasetValidationResponse(
            is_valid=False,
            total_records=len(df),
            valid_records=0,
            invalid_records=len(df),
            errors=errors,
        )

    total_records = len(df)
    null_counts = {c: int(df[c].isnull().sum()) for c in df.columns}
    for c, cnt in null_counts.items():
        if cnt > 0:
            null_rows = df[df[c].isnull()].index.tolist()[:10]
            for r in null_rows:
                errors.append(
                    DatasetValidationError(
                        row=r + 2,
                        column=c,
                        raw_value="NULL",
                        message=f"Null value found in required column '{c}'.",
                    )
                )

    # Validate numbers
    invalid_qty = df[~(df["quantity_tonnes"] > 0)]
    for r, v in invalid_qty["quantity_tonnes"].items():
        errors.append(
            DatasetValidationError(
                row=int(r) + 2,
                column="quantity_tonnes",
                raw_value=str(v),
                message="Quantity must be strictly positive.",
            )
        )

    invalid_dist = df[~(df["distance_km"] > 0)]
    for r, v in invalid_dist["distance_km"].items():
        errors.append(
            DatasetValidationError(
                row=int(r) + 2,
                column="distance_km",
                raw_value=str(v),
                message="Distance must be strictly positive.",
            )
        )

    invalid_cost = df[~(df["freight_cost_inr"] >= 0)]
    for r, v in invalid_cost["freight_cost_inr"].items():
        errors.append(
            DatasetValidationError(
                row=int(r) + 2,
                column="freight_cost_inr",
                raw_value=str(v),
                message="Freight cost cannot be negative.",
            )
        )

    # Route types
    invalid_types = df[~df["route_type"].isin(settings.VALID_ROUTE_TYPES)]
    for r, v in invalid_types["route_type"].items():
        errors.append(
            DatasetValidationError(
                row=int(r) + 2,
                column="route_type",
                raw_value=str(v),
                message=f"Invalid route_type. Expected one of {settings.VALID_ROUTE_TYPES}.",
            )
        )

    # Dates
    parsed_dates = pd.to_datetime(df["shipment_date"], errors="coerce")
    invalid_dates = df[parsed_dates.isnull()]
    for r, v in invalid_dates["shipment_date"].items():
        errors.append(
            DatasetValidationError(
                row=int(r) + 2,
                column="shipment_date",
                raw_value=str(v),
                message="Invalid shipment date format.",
            )
        )

    valid_mask = (
        (df["quantity_tonnes"] > 0)
        & (df["distance_km"] > 0)
        & (df["freight_cost_inr"] >= 0)
        & (df["route_type"].isin(settings.VALID_ROUTE_TYPES))
        & (parsed_dates.notnull())
    )

    valid_count = int(valid_mask.sum())
    invalid_count = total_records - valid_count
    is_valid = (invalid_count == 0) and (total_records > 0)

    neg_zero_counts = {
        "quantity_tonnes <= 0": len(invalid_qty),
        "distance_km <= 0": len(invalid_dist),
        "freight_cost_inr < 0": len(invalid_cost),
    }

    return DatasetValidationResponse(
        is_valid=is_valid,
        total_records=total_records,
        valid_records=valid_count,
        invalid_records=invalid_count,
        errors=errors[:100],  # Return up to 100 sample issues
        null_counts=null_counts,
        negative_or_zero_counts=neg_zero_counts,
    )


@router.post("/validate", response_model=DatasetValidationResponse, summary="Validate Uploaded Dataset")
async def validate_dataset(
    shipments_file: UploadFile = File(..., description="Shipment records CSV"),
    notes_file: Optional[UploadFile] = File(None, description="Optional context notes CSV"),
) -> DatasetValidationResponse:
    """Inspect and validate CSV schema without storing or replacing the active dataset."""
    shipment_bytes = await shipments_file.read()
    return await validate_raw_shipment_bytes(shipment_bytes)


@router.post("/import", response_model=DatasetImportResponse, summary="Import and Persist Dataset")
async def import_dataset(
    shipments_file: UploadFile = File(..., description="Shipment records CSV"),
    notes_file: Optional[UploadFile] = File(None, description="Optional context notes CSV"),
    dataset_name: str = Form(..., description="Human-readable dataset title"),
    set_active: bool = Form(True, description="Make this the active dataset for subsequent analysis"),
) -> DatasetImportResponse:
    """Validate, persist, and register a new dataset."""
    shipment_bytes = await shipments_file.read()
    val_result = await validate_raw_shipment_bytes(shipment_bytes)

    if not val_result.is_valid:
        raise ValidationException(
            message=f"Dataset import rejected: {val_result.invalid_records} invalid records found.",
            details={"errors": [e.model_dump() for e in val_result.errors[:15]]},
        )

    notes_text = None
    if notes_file:
        notes_bytes = await notes_file.read()
        notes_text = notes_bytes.decode("utf-8")

    shipment_text = shipment_bytes.decode("utf-8")
    meta = storage.save_dataset(
        name=dataset_name,
        shipment_content=shipment_text,
        notes_content=notes_text,
        set_active=set_active,
    )

    return DatasetImportResponse(
        message=f"Dataset '{meta.name}' imported successfully with {meta.shipment_count} valid records.",
        dataset=meta,
        validation=val_result,
    )


@router.get("/{dataset_id}/validation", response_model=DatasetValidationResponse, summary="Get Stored Dataset Validation")
def get_dataset_validation(dataset_id: str) -> DatasetValidationResponse:
    """Run validation report on an existing persisted dataset."""
    safe_id = sanitize_safe_id(dataset_id, "dataset_id")
    target_file = storage.datasets_dir / safe_id / "shipment_records.csv"
    if not target_file.exists():
        raise ValidationException(f"Dataset '{dataset_id}' does not exist.")

    with open(target_file, "rb") as f:
        content = f.read()

    import asyncio
    return asyncio.run(validate_raw_shipment_bytes(content))
