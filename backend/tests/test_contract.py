"""Unit tests for the eight-column output contract and export schema."""

import io
import pandas as pd
import pytest

from backend.app.core.config import settings
from backend.app.services.evaluation import run_full_pipeline


def test_output_contract_columns_and_types():
    """Verify exact column names, order, and data formatting."""
    _, contract_df = run_full_pipeline()

    # Exact column names and order
    expected_columns = [
        "route",
        "week_of",
        "cost_per_tonne_km",
        "vs_own_history",
        "vs_similar_routes",
        "flagged",
        "matched_note_id",
        "reason",
    ]
    assert list(contract_df.columns) == expected_columns

    # Date formatting check (YYYY-MM-DD)
    date_pattern = r"^\d{4}-\d{2}-\d{2}$"
    assert contract_df["week_of"].str.match(date_pattern).all()

    # Non-empty reason string check
    assert (contract_df["reason"].str.strip().str.len() > 0).all()

    # Flagged label values check
    valid_flag_labels = {"Yes", "No (justified)", "No"}
    assert set(contract_df["flagged"].unique()).issubset(valid_flag_labels)

    # Empty matched note id when unexplained or normal
    unexplained = contract_df[contract_df["flagged"] == "Yes"]
    assert (unexplained["matched_note_id"] == "").all()

    normal = contract_df[contract_df["flagged"] == "No"]
    assert (normal["matched_note_id"] == "").all()

    # Justified has non-empty matched note id
    justified = contract_df[contract_df["flagged"] == "No (justified)"]
    assert (justified["matched_note_id"].str.len() > 0).all()


def test_rfc4180_export_and_reingestion(tmp_path):
    """Verify that exported CSV passes strict CSV parser without tokenization errors."""
    _, contract_df = run_full_pipeline()
    out_file = tmp_path / "test_contract.csv"

    from backend.app.services.anomaly_detection import AnomalyDetector
    detector = AnomalyDetector()
    detector.export_csv(contract_df, out_file)

    # Must parse back cleanly in pandas with exactly 8 columns and 0 errors
    reloaded = pd.read_csv(out_file)
    assert reloaded.shape[1] == 8
    assert len(reloaded) == len(contract_df)
