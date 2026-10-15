"""Unit tests for anomaly detection logic and anti-hallucination guardrails."""

from datetime import date
import pandas as pd
import pytest

from backend.app.schemas.analysis import ContextNote
from backend.app.services.anomaly_detection import AnomalyDetector


@pytest.fixture
def sample_notes():
    return [
        ContextNote(
            note_id="N001",
            date=date(2025, 2, 24),
            applies_to="Chennai-Bangalore",
            note="Heavy flooding on the highway disrupted normal truck movement forcing longer detours and higher trip costs.",
        ),
        ContextNote(
            note_id="N005",
            date=date(2024, 7, 29),
            applies_to="Mumbai-Delhi",
            note="Highway maintenance work caused minor delays; costs were not significantly affected.",
        ),
        ContextNote(
            note_id="N006",
            date=date(2025, 9, 22),
            applies_to="All Routes",
            note="Demand remained stable this quarter with no major disruptions reported.",
        ),
    ]


def test_guardrail_rejects_unaffected_notes_as_justification(sample_notes):
    """Guardrail test: N005 ('costs not significantly affected') and N006 ('no major disruptions')
    must NEVER justify an anomaly."""
    detector = AnomalyDetector(threshold_pct=20.0)

    # Spike on Mumbai-Delhi around 2024-07-29
    df = pd.DataFrame([{
        "route": "Mumbai-Delhi",
        "route_type": "Long",
        "week_of": "2024-07-29",
        "cost_per_tonne_km": 5.0,
        "vs_own_history": 3.5,
        "vs_similar_routes": 3.8,
        "pct_vs_history": 42.8,
        "pct_vs_peers": 31.5,
    }])

    _, records = detector.detect_anomalies(df, sample_notes)
    rec = records[0]

    assert rec.flagged is True
    # Must be marked unexplained because N005 explicitly states costs were unaffected
    assert rec.flagged_label == "Yes"
    assert rec.matched_note_id == ""
    assert "it does not describe a reason for a cost rise" in rec.reason


def test_justified_anomaly_cites_correct_note(sample_notes):
    """Verify that a genuine cost-increasing event produces a justified verdict and cites the note."""
    detector = AnomalyDetector(threshold_pct=20.0)

    # Flood week on Chennai-Bangalore
    df = pd.DataFrame([{
        "route": "Chennai-Bangalore",
        "route_type": "Medium",
        "week_of": "2025-02-24",
        "cost_per_tonne_km": 3.58,
        "vs_own_history": 2.72,
        "vs_similar_routes": 2.58,
        "pct_vs_history": 31.6,
        "pct_vs_peers": 38.7,
    }])

    _, records = detector.detect_anomalies(df, sample_notes)
    rec = records[0]

    assert rec.flagged is True
    assert rec.flagged_label == "No (justified)"
    assert rec.matched_note_id == "N001"
    assert "Matches note N001" in rec.reason


def test_unexplained_anomaly_has_empty_matched_note_id(sample_notes):
    """Verify that an unexplained spike leaves matched_note_id strictly blank."""
    detector = AnomalyDetector(threshold_pct=20.0)

    # Spike on Delhi-Jaipur with no note
    df = pd.DataFrame([{
        "route": "Delhi-Jaipur",
        "route_type": "Short",
        "week_of": "2024-11-11",
        "cost_per_tonne_km": 4.17,
        "vs_own_history": 3.08,
        "vs_similar_routes": 3.45,
        "pct_vs_history": 35.5,
        "pct_vs_peers": 21.0,
    }])

    _, records = detector.detect_anomalies(df, sample_notes)
    rec = records[0]

    assert rec.flagged is True
    assert rec.flagged_label == "Yes"
    assert rec.matched_note_id == ""
    assert "No matching note found" in rec.reason
