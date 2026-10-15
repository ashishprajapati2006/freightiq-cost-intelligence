"""Feature engineering module for FreightIQ machine-learning anomaly detection.

Extracts leakage-free, temporally consistent features for both training and inference.
Strictly respects chronological constraints (zero look-ahead) and avoids route identifier leakage.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger("freightiq.ml.features")

# Canonical feature list utilized by the Isolation Forest pipeline
FEATURE_NAMES: List[str] = [
    "cost_per_tonne_km",
    "pct_vs_history",
    "pct_vs_peers",
    "momentum_1w",
    "history_volatility",
    "z_score_history",
]


class FeatureMetadata(BaseModel):
    """Specification of an engineered feature."""

    name: str
    dtype: str
    description: str
    fill_value: float = 0.0
    expected_min: Optional[float] = None
    expected_max: Optional[float] = None


FEATURE_SPECS: Dict[str, FeatureMetadata] = {
    "cost_per_tonne_km": FeatureMetadata(
        name="cost_per_tonne_km",
        dtype="float64",
        description="Work-weighted freight cost per tonne-km in INR",
        fill_value=2.5,
        expected_min=0.1,
        expected_max=50.0,
    ),
    "pct_vs_history": FeatureMetadata(
        name="pct_vs_history",
        dtype="float64",
        description="Percentage deviation from trailing 8-week historical baseline",
        fill_value=0.0,
        expected_min=-100.0,
        expected_max=500.0,
    ),
    "pct_vs_peers": FeatureMetadata(
        name="pct_vs_peers",
        dtype="float64",
        description="Percentage deviation from same-week peer route average",
        fill_value=0.0,
        expected_min=-100.0,
        expected_max=500.0,
    ),
    "momentum_1w": FeatureMetadata(
        name="momentum_1w",
        dtype="float64",
        description="1-week absolute unit cost delta from immediately prior available week",
        fill_value=0.0,
        expected_min=-20.0,
        expected_max=20.0,
    ),
    "history_volatility": FeatureMetadata(
        name="history_volatility",
        dtype="float64",
        description="Rolling sample standard deviation of unit cost over trailing <= 8 weeks",
        fill_value=0.0,
        expected_min=0.0,
        expected_max=10.0,
    ),
    "z_score_history": FeatureMetadata(
        name="z_score_history",
        dtype="float64",
        description="Standardized unit cost deviation relative to trailing volatility",
        fill_value=0.0,
        expected_min=-10.0,
        expected_max=20.0,
    ),
}


class MLFeatureEngineer:
    """Deterministic feature extractor for freight cost observations."""

    def __init__(self, feature_names: Optional[List[str]] = None):
        self.feature_names = feature_names or list(FEATURE_NAMES)

    def extract_features(
        self,
        weekly_df: pd.DataFrame,
        is_training: bool = False,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Extract ML features from aggregated weekly route data with baselines.

        Args:
            weekly_df: DataFrame containing at least:
                'route', 'route_type', 'week_of', 'cost_per_tonne_km',
                'vs_own_history', 'vs_similar_routes'.
            is_training: Flag indicating whether this extraction is for model fitting.

        Returns:
            Tuple of (engineered_df, feature_matrix_df)
        """
        df = weekly_df.copy()

        # Ensure sorted chronologically per corridor
        df = df.sort_values(["route", "route_type", "week_of"]).reset_index(drop=True)

        # 1. Base deviation percentages (if not already calculated)
        if "pct_vs_history" not in df.columns:
            df["pct_vs_history"] = np.where(
                df["vs_own_history"].notna() & (df["vs_own_history"] > 0),
                (df["cost_per_tonne_km"] - df["vs_own_history"]) / df["vs_own_history"] * 100.0,
                np.nan,
            )

        if "pct_vs_peers" not in df.columns:
            df["pct_vs_peers"] = np.where(
                df["vs_similar_routes"].notna() & (df["vs_similar_routes"] > 0),
                (df["cost_per_tonne_km"] - df["vs_similar_routes"]) / df["vs_similar_routes"] * 100.0,
                np.nan,
            )

        # 2. 1-week momentum (lag delta per route)
        df["cost_lag1"] = df.groupby(["route", "route_type"])["cost_per_tonne_km"].shift(1)
        df["momentum_1w"] = df["cost_per_tonne_km"] - df["cost_lag1"]

        # 3. Trailing historical volatility (standard deviation of up to 8 prior available weeks)
        def calc_trailing_volatility(series: pd.Series) -> pd.Series:
            stds: List[float] = []
            vals = series.values
            for i in range(len(vals)):
                # Strictly prior weeks (zero look-ahead: max(0, i-8) to i)
                prior = vals[max(0, i - 8):i]
                if len(prior) >= 2:
                    stds.append(float(np.std(prior, ddof=1)))
                else:
                    stds.append(0.0)
            return pd.Series(stds, index=series.index)

        df["history_volatility"] = df.groupby(
            ["route", "route_type"], group_keys=False
        )["cost_per_tonne_km"].apply(calc_trailing_volatility)

        # 4. Standardized Z-Score against trailing history
        # (cost - baseline) / volatility with epsilon stabilization
        diff = df["cost_per_tonne_km"] - df["vs_own_history"].fillna(df["cost_per_tonne_km"])
        vol = df["history_volatility"].replace(0.0, np.nan)
        df["z_score_history"] = (diff / vol).fillna(0.0)

        # 5. Build clean feature matrix with safe fill values
        X = pd.DataFrame(index=df.index)
        for feat in self.feature_names:
            spec = FEATURE_SPECS.get(feat)
            fill_val = spec.fill_value if spec else 0.0
            if feat in df.columns:
                X[feat] = df[feat].fillna(fill_val).astype("float64")
            else:
                logger.warning("Feature '%s' missing from input. Imputing with default %s.", feat, fill_val)
                X[feat] = fill_val

        return df, X

    def validate_schema(self, X: pd.DataFrame) -> Tuple[bool, List[str]]:
        """Verify that an inference feature matrix satisfies the required schema."""
        errors: List[str] = []
        for feat in self.feature_names:
            if feat not in X.columns:
                errors.append(f"Missing required feature: '{feat}'")
            elif not np.issubdtype(X[feat].dtype, np.number):
                errors.append(f"Feature '{feat}' must be numeric, got {X[feat].dtype}")
        return len(errors) == 0, errors

    @classmethod
    def get_feature_schema(cls) -> Dict[str, Any]:
        """Return serialized feature schema dictionary for model governance."""
        return {
            "feature_names": FEATURE_NAMES,
            "features": {k: v.model_dump() for k, v in FEATURE_SPECS.items()},
        }
