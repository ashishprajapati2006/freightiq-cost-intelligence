"""Unit tests for route-level and weekly shipment aggregation."""

from datetime import date
import pandas as pd
import pytest

from backend.app.services.aggregation import (
    aggregate_weekly_routes,
    canonical_route,
    get_monday_week_start,
)


def test_monday_week_start_mapping():
    """Verify that every day of the week maps to its correct Monday."""
    # 2024-01-01 is Monday
    assert get_monday_week_start("2024-01-01") == "2024-01-01"
    # 2024-01-02 is Tuesday -> maps to 2024-01-01
    assert get_monday_week_start("2024-01-02") == "2024-01-01"
    # 2024-01-07 is Sunday -> maps to 2024-01-01
    assert get_monday_week_start("2024-01-07") == "2024-01-01"
    # 2024-01-08 is next Monday
    assert get_monday_week_start("2024-01-08") == "2024-01-08"


def test_canonical_route_formatting():
    """Verify consistent origin-destination string formatting."""
    assert canonical_route(" Mumbai ", " Pune ") == "Mumbai-Pune"
    assert canonical_route("Delhi", "Jaipur") == "Delhi-Jaipur"


def test_work_weighted_cost_aggregation():
    """Verify mathematically consistent aggregation: sum(cost) / sum(qty * dist)."""
    # Create two shipments on the same route and week with varying distances and quantities
    # Shipment 1: 10 tonnes, 100 km, cost 2000 INR -> work = 1000 tonne-km
    # Shipment 2: 20 tonnes, 200 km, cost 6000 INR -> work = 4000 tonne-km
    # Total cost = 8000 INR, Total work = 5000 tonne-km -> cost_per_tonne_km = 8000 / 5000 = 1.60
    # Note: simple unweighted average of rates: (2000/1000 + 6000/4000)/2 = (2.0 + 1.5)/2 = 1.75 != 1.60!
    data = [
        {
            "shipment_id": "S1",
            "origin": "Mumbai",
            "destination": "Pune",
            "route_type": "Short",
            "quantity_tonnes": 10.0,
            "distance_km": 100.0,
            "freight_cost_inr": 2000.0,
            "shipment_date": pd.to_datetime("2024-01-02"),
        },
        {
            "shipment_id": "S2",
            "origin": "Mumbai",
            "destination": "Pune",
            "route_type": "Short",
            "quantity_tonnes": 20.0,
            "distance_km": 200.0,
            "freight_cost_inr": 6000.0,
            "shipment_date": pd.to_datetime("2024-01-05"),
        },
    ]
    df = pd.DataFrame(data)
    result = aggregate_weekly_routes(df)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["route"] == "Mumbai-Pune"
    assert row["week_of"] == "2024-01-01"
    assert row["total_cost"] == 8000.0
    assert row["total_work_tonne_km"] == 5000.0
    assert pytest.approx(row["cost_per_tonne_km"], rel=1e-6) == 1.60
    assert row["shipment_count"] == 2
