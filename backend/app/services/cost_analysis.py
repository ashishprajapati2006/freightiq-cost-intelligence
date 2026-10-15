"""Baseline tracking and percentage deviation calculation service.

Computes:
1. Historical trailing baseline (at most 8 prior observations, strictly no look-ahead).
2. Similar-route peer baseline (same week and route type, self-excluded).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_route_baselines(
    weekly_df: pd.DataFrame, max_history_weeks: int = 8
) -> pd.DataFrame:
    """Compute historical and peer comparison baselines strictly per the assignment contract.

    Args:
        weekly_df: Aggregated route-week DataFrame from aggregate_weekly_routes().
        max_history_weeks: Maximum number of prior observations to average (default: 8).

    Guarantees:
        - vs_own_history strictly excludes current week and future weeks (zero look-ahead).
        - If fewer than 8 prior weeks exist, averages all available prior observations.
        - If 0 prior observations exist, returns NaN (missing baseline).
        - vs_similar_routes excludes the route itself from the peer group.
        - If no other routes of the same route_type exist in that week, returns NaN.
    """
    if weekly_df.empty:
        return weekly_df.copy()

    df = weekly_df.copy().sort_values(["route", "route_type", "week_of"]).reset_index(drop=True)

    # Pre-index for high performance
    route_groups = {
        (r, rt): grp.sort_values("week_of").copy()
        for (r, rt), grp in df.groupby(["route", "route_type"])
    }
    peer_groups = {
        (w, rt): grp.copy()
        for (w, rt), grp in df.groupby(["week_of", "route_type"])
    }

    hist_means: list[float] = []
    hist_counts: list[int] = []
    peer_means: list[float] = []
    peer_counts: list[int] = []

    for _, row in df.iterrows():
        route = row["route"]
        rtype = row["route_type"]
        week = row["week_of"]

        # 1. Trailing Historical Baseline
        r_hist = route_groups.get((route, rtype))
        if r_hist is not None:
            # Strictly prior weeks
            priors = r_hist[r_hist["week_of"] < week].tail(max_history_weeks)
            count = len(priors)
            hist_counts.append(count)
            if count > 0:
                hist_means.append(float(priors["cost_per_tonne_km"].mean()))
            else:
                hist_means.append(np.nan)
        else:
            hist_counts.append(0)
            hist_means.append(np.nan)

        # 2. Similar-route Peer Baseline
        w_peers = peer_groups.get((week, rtype))
        if w_peers is not None:
            # Exclude route itself
            eligible_peers = w_peers[w_peers["route"] != route]
            p_count = len(eligible_peers)
            peer_counts.append(p_count)
            if p_count > 0:
                peer_means.append(float(eligible_peers["cost_per_tonne_km"].mean()))
            else:
                peer_means.append(np.nan)
        else:
            peer_counts.append(0)
            peer_means.append(np.nan)

    df["vs_own_history"] = hist_means
    df["history_count"] = hist_counts
    df["vs_similar_routes"] = peer_means
    df["peer_count"] = peer_counts

    # Percentage deviations
    df["pct_vs_history"] = np.where(
        df["vs_own_history"] > 0,
        (df["cost_per_tonne_km"] - df["vs_own_history"]) / df["vs_own_history"] * 100.0,
        np.nan,
    )

    df["pct_vs_peers"] = np.where(
        df["vs_similar_routes"] > 0,
        (df["cost_per_tonne_km"] - df["vs_similar_routes"]) / df["vs_similar_routes"] * 100.0,
        np.nan,
    )

    return df
