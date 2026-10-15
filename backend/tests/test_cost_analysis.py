"""Unit tests for baseline calculation rules."""

import numpy as np
import pandas as pd
import pytest

from backend.app.services.cost_analysis import compute_route_baselines


def test_historical_baseline_strictly_excludes_current_week():
    """Verify zero look-ahead: current week is strictly excluded."""
    data = [
        {"route": "Route-A", "route_type": "Short", "week_of": "2024-01-01", "cost_per_tonne_km": 2.0},
        {"route": "Route-A", "route_type": "Short", "week_of": "2024-01-08", "cost_per_tonne_km": 4.0},
    ]
    df = pd.DataFrame(data)
    result = compute_route_baselines(df)

    # Week 1: no prior weeks -> NaN
    assert np.isnan(result.loc[result["week_of"] == "2024-01-01", "vs_own_history"].values[0])
    # Week 2: only Week 1 is prior -> 2.0 (not (2.0 + 4.0)/2 = 3.0)
    w2_hist = result.loc[result["week_of"] == "2024-01-08", "vs_own_history"].values[0]
    assert pytest.approx(w2_hist, rel=1e-6) == 2.0


def test_historical_baseline_caps_at_eight_observations():
    """Verify historical baseline rolling window caps at at most 8 prior observations."""
    rows = []
    # 12 consecutive weeks with costs 1, 2, ..., 12
    for i in range(1, 13):
        rows.append({
            "route": "Route-A",
            "route_type": "Short",
            "week_of": f"2024-{i:02d}-01",
            "cost_per_tonne_km": float(i),
        })
    df = pd.DataFrame(rows)
    result = compute_route_baselines(df, max_history_weeks=8)

    # For week 12 (cost 12), the 8 prior weeks are weeks 4 through 11 (costs 4, 5, 6, 7, 8, 9, 10, 11)
    # Mean of 4..11 = (4 + 11) / 2 = 7.5
    w12 = result.loc[result["week_of"] == "2024-12-01"].iloc[0]
    assert w12["history_count"] == 8
    assert pytest.approx(w12["vs_own_history"], rel=1e-6) == 7.5


def test_peer_baseline_excludes_current_route():
    """Verify peer baseline excludes self from average."""
    data = [
        {"route": "Route-A", "route_type": "Medium", "week_of": "2024-01-01", "cost_per_tonne_km": 2.0},
        {"route": "Route-B", "route_type": "Medium", "week_of": "2024-01-01", "cost_per_tonne_km": 4.0},
        {"route": "Route-C", "route_type": "Medium", "week_of": "2024-01-01", "cost_per_tonne_km": 6.0},
    ]
    df = pd.DataFrame(data)
    result = compute_route_baselines(df)

    # For Route-A, peers are B (4.0) and C (6.0) -> mean = 5.0
    a_peer = result.loc[result["route"] == "Route-A", "vs_similar_routes"].values[0]
    assert pytest.approx(a_peer, rel=1e-6) == 5.0
    # For Route-B, peers are A (2.0) and C (6.0) -> mean = 4.0
    b_peer = result.loc[result["route"] == "Route-B", "vs_similar_routes"].values[0]
    assert pytest.approx(b_peer, rel=1e-6) == 4.0


def test_missing_baselines_remain_nan():
    """Verify missing baselines remain NaN without padding or extrapolation."""
    # Only 1 route in this route_type and first week
    data = [
        {"route": "Solo-Route", "route_type": "Long", "week_of": "2024-01-01", "cost_per_tonne_km": 5.0}
    ]
    df = pd.DataFrame(data)
    result = compute_route_baselines(df)

    assert np.isnan(result["vs_own_history"].values[0])
    assert np.isnan(result["vs_similar_routes"].values[0])
    assert np.isnan(result["pct_vs_history"].values[0])
    assert np.isnan(result["pct_vs_peers"].values[0])
