"""Data ingestion and validation service with rigorous quality checks.

Preserves source files without modification while diagnosing syntax and schema issues.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from backend.app.core.config import settings
from backend.app.schemas.analysis import ContextNote, DataQualityReport, ValidationIssue


REQUIRED_SHIPMENT_COLUMNS = [
    "shipment_id",
    "origin",
    "destination",
    "route_type",
    "material",
    "quantity_tonnes",
    "distance_km",
    "freight_cost_inr",
    "shipment_date",
    "transporter",
]

REQUIRED_NOTE_COLUMNS = ["note_id", "date", "applies_to", "note"]


def load_shipments(
    file_path: Optional[Path | str] = None,
) -> Tuple[pd.DataFrame, DataQualityReport]:
    """Load and validate shipment records from CSV.

    Performs strict schema validation, type conversions, and boundary checks.
    Does NOT silently replace invalid values with zero.

    Returns:
        Tuple of (clean_df, data_quality_report)
    """
    path = Path(file_path or settings.SHIPMENTS_FILE).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Shipment dataset not found at: {path}")

    # Read raw CSV
    df = pd.read_csv(path)

    # Validate header contract
    missing_cols = [c for c in REQUIRED_SHIPMENT_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Shipment CSV missing required columns: {missing_cols}")

    total_records = len(df)
    issues: list[ValidationIssue] = []

    # Check nulls
    null_counts = {col: int(df[col].isnull().sum()) for col in df.columns}
    for col, count in null_counts.items():
        if count > 0:
            null_rows = df[df[col].isnull()].index.tolist()
            for r in null_rows[:10]:
                issues.append(
                    ValidationIssue(
                        row_index=r,
                        field=col,
                        value="NULL/NaN",
                        issue="Null value detected in required column",
                    )
                )

    # Type coercion and validation
    # 1. quantity_tonnes must be float and > 0
    invalid_qty = df[~(df["quantity_tonnes"] > 0)]
    for r, val in invalid_qty["quantity_tonnes"].items():
        issues.append(
            ValidationIssue(
                row_index=int(r),
                field="quantity_tonnes",
                value=str(val),
                issue="Quantity must be strictly positive",
            )
        )

    # 2. distance_km must be float and > 0
    invalid_dist = df[~(df["distance_km"] > 0)]
    for r, val in invalid_dist["distance_km"].items():
        issues.append(
            ValidationIssue(
                row_index=int(r),
                field="distance_km",
                value=str(val),
                issue="Distance must be strictly positive",
            )
        )

    # 3. freight_cost_inr must be non-negative
    invalid_cost = df[~(df["freight_cost_inr"] >= 0)]
    for r, val in invalid_cost["freight_cost_inr"].items():
        issues.append(
            ValidationIssue(
                row_index=int(r),
                field="freight_cost_inr",
                value=str(val),
                issue="Freight cost cannot be negative",
            )
        )

    # 4. route_type must be in {'Short', 'Medium', 'Long'}
    invalid_type = df[~df["route_type"].isin(settings.VALID_ROUTE_TYPES)]
    for r, val in invalid_type["route_type"].items():
        issues.append(
            ValidationIssue(
                row_index=int(r),
                field="route_type",
                value=str(val),
                issue=f"Invalid route_type. Expected one of {settings.VALID_ROUTE_TYPES}",
            )
        )

    # 5. shipment_date parsing
    parsed_dates = pd.to_datetime(df["shipment_date"], errors="coerce")
    invalid_dates = df[parsed_dates.isnull()]
    for r, val in invalid_dates["shipment_date"].items():
        issues.append(
            ValidationIssue(
                row_index=int(r),
                field="shipment_date",
                value=str(val),
                issue="Invalid date format",
            )
        )

    # Filter strictly valid rows (do not guess or fill zeroes)
    valid_mask = (
        (df["quantity_tonnes"] > 0)
        & (df["distance_km"] > 0)
        & (df["freight_cost_inr"] >= 0)
        & (df["route_type"].isin(settings.VALID_ROUTE_TYPES))
        & (parsed_dates.notnull())
    )

    clean_df = df[valid_mask].copy()
    clean_df["shipment_date"] = parsed_dates[valid_mask]
    clean_df["quantity_tonnes"] = clean_df["quantity_tonnes"].astype(float)
    clean_df["distance_km"] = clean_df["distance_km"].astype(float)
    clean_df["freight_cost_inr"] = clean_df["freight_cost_inr"].astype(float)

    # Canonical route
    clean_df["route"] = clean_df["origin"].str.strip() + "-" + clean_df["destination"].str.strip()

    # Compile report
    date_min = clean_df["shipment_date"].min().strftime("%Y-%m-%d")
    date_max = clean_df["shipment_date"].max().strftime("%Y-%m-%d")

    neg_zero_counts = {
        "quantity_tonnes <= 0": len(invalid_qty),
        "distance_km <= 0": len(invalid_dist),
        "freight_cost_inr < 0": len(invalid_cost),
    }

    report = DataQualityReport(
        total_records=total_records,
        valid_records=len(clean_df),
        invalid_records=total_records - len(clean_df),
        null_counts=null_counts,
        negative_or_zero_values=neg_zero_counts,
        unique_routes=int(clean_df["route"].nunique()),
        unique_route_types=sorted(clean_df["route_type"].unique().tolist()),
        date_range=(date_min, date_max),
        issues=issues,
    )

    return clean_df, report


def load_context_notes(file_path: Optional[Path | str] = None) -> list[ContextNote]:
    """Load qualitative context notes from CSV.

    Validates schema and encapsulates notes into strongly-typed ContextNote objects.
    """
    path = Path(file_path or settings.NOTES_FILE).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Context notes file not found at: {path}")

    df = pd.read_csv(path)
    missing_cols = [c for c in REQUIRED_NOTE_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Context notes CSV missing required columns: {missing_cols}")

    notes: list[ContextNote] = []
    for _, row in df.iterrows():
        # Standardize applies_to route formatting
        scope = str(row["applies_to"]).strip().replace("–", "-").replace("—", "-")
        dt = pd.to_datetime(row["date"]).date()
        notes.append(
            ContextNote(
                note_id=str(row["note_id"]).strip(),
                date=dt,
                applies_to=scope,
                note=str(row["note"]).strip(),
            )
        )
    return notes


def diagnose_sample_output(
    file_path: Optional[Path | str] = None,
) -> Tuple[bool, str, list[dict]]:
    """Diagnose the raw sample output file for parsing errors.

    Identifies the exact CSV syntax error without altering the file on disk.
    Line 4 contains an unquoted comma inside the reason field ('(N006, 2025-09-22)'),
    causing standard RFC-4180 parsers to encounter 9 columns instead of 8.

    Returns:
        Tuple of (has_syntax_error, diagnosis_message, parsed_rows_via_resilient_parser)
    """
    path = Path(file_path or settings.SAMPLE_OUTPUT_FILE).resolve()
    if not path.exists():
        return False, f"Sample output file not found at {path}", []

    with open(path, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()

    diagnosis = []
    has_error = False

    # Try standard csv parser
    reader = csv.reader(raw_lines)
    header = next(reader)
    expected_col_count = len(header)

    recovered_rows = []
    for line_idx, line in enumerate(raw_lines[1:], start=2):
        row_fields = list(csv.reader([line]))[0]
        if len(row_fields) != expected_col_count:
            has_error = True
            diagnosis.append(
                f"Line {line_idx} contains {len(row_fields)} fields (expected {expected_col_count}). "
                f"Root cause: Unquoted comma in text: '{line.strip()}'"
            )
            # Resilient recovery: First 7 fields are canonical, remainder is joined as 'reason'
            first_7 = [f.strip() for f in row_fields[:7]]
            reason_field = ",".join(row_fields[7:]).strip()
            row_dict = dict(zip(header, first_7 + [reason_field]))
            recovered_rows.append(row_dict)
        else:
            row_dict = dict(zip(header, [f.strip() for f in row_fields]))
            recovered_rows.append(row_dict)

    diag_str = (
        "CSV PARSER DIAGNOSIS:\n"
        + "\n".join(diagnosis)
        + "\nResolution: The case study contract requires 8 columns: "
        + f"{header}. Our generator encloses string fields in double quotes per RFC 4180."
    )
    return has_error, diag_str, recovered_rows
