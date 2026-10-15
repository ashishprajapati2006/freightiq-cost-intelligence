"""Route-level and weekly shipment aggregation service.

Ensures strict Monday-to-Sunday week grouping and mathematically consistent
work-weighted unit-cost aggregation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Union

import numpy as np
import pandas as pd


def get_monday_week_start(dt: Union[date, datetime, str, pd.Timestamp]) -> str:
    """Return the Monday date string (YYYY-MM-DD) for any given calendar date.

    Weeks run Monday to Sunday per case-study contract.
    Monday (weekday 0) -> same date.
    Sunday (weekday 6) -> previous Monday (-6 days).
    """
    if isinstance(dt, str):
        parsed = pd.to_datetime(dt)
    elif isinstance(dt, (date, datetime, pd.Timestamp)):
        parsed = pd.to_datetime(dt)
    else:
        raise ValueError(f"Unsupported date format: {type(dt)}")

    # Monday offset
    monday = parsed - pd.Timedelta(days=parsed.weekday())
    return monday.strftime("%Y-%m-%d")


def canonical_route(origin: str, destination: str) -> str:
    """Standardize route representation as Origin-Destination."""
    return f"{origin.strip()}-{destination.strip()}"


def aggregate_weekly_routes(df: pd.DataFrame) -> pd.DataFrame:
    """Group shipment records by origin, destination, route_type, and Monday week.

    Formula:
        cost_per_tonne_km = sum(freight_cost_inr) / sum(quantity_tonnes * distance_km)

    Denominator Semantics:
        Work done is calculated individually per shipment (tonnes * km) and then
        summed across the route-week. This strictly avoids mathematical distortions
        caused by multiplying total quantity by an unweighted average distance.

    Returns:
        DataFrame with columns:
        ['origin', 'destination', 'route', 'route_type', 'week_of',
         'total_cost', 'total_work_tonne_km', 'shipment_count', 'cost_per_tonne_km']
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "origin",
                "destination",
                "route",
                "route_type",
                "week_of",
                "total_cost",
                "total_work_tonne_km",
                "shipment_count",
                "cost_per_tonne_km",
            ]
        )

    work_df = df.copy()

    # Assign Monday week
    if "week_of" not in work_df.columns:
        work_df["week_of"] = work_df["shipment_date"].apply(get_monday_week_start)

    # Individual shipment work done in tonne-km
    work_df["work_done"] = work_df["quantity_tonnes"] * work_df["distance_km"]

    # Canonical route
    if "route" not in work_df.columns:
        work_df["route"] = work_df.apply(
            lambda r: canonical_route(str(r["origin"]), str(r["destination"])), axis=1
        )

    # Group aggregation
    grouped = (
        work_df.groupby(
            ["origin", "destination", "route", "route_type", "week_of"], as_index=False
        )
        .agg(
            total_cost=("freight_cost_inr", "sum"),
            total_work_tonne_km=("work_done", "sum"),
            shipment_count=("shipment_id", "count"),
        )
    )

    # Exact work-weighted cost per tonne-km
    grouped["cost_per_tonne_km"] = np.where(
        grouped["total_work_tonne_km"] > 0,
        grouped["total_cost"] / grouped["total_work_tonne_km"],
        np.nan,
    )

    # Sort chronologically by route and week
    grouped = grouped.sort_values(["route", "route_type", "week_of"]).reset_index(
        drop=True
    )
    return grouped
