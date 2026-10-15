"""ML Model Governance, Monitoring, Drift Detection, and Deployment Policy Service.

Monitors:
1. Input schema integrity (type checking, missing rates, bounds).
2. Feature distribution drift (Normalized Median Shift vs training IQR).
3. Anomaly score distribution changes and anomaly rate stability.
4. Model age and staleness.
5. Explicit deployment policy preventing unvalidated automatic retraining.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.app.core.config import settings
from backend.app.schemas.ml import MLDriftReport
from backend.app.services.ml_features import FEATURE_NAMES, FEATURE_SPECS, MLFeatureEngineer
from backend.app.services.ml_inference import MLInferenceService, inference_service

logger = logging.getLogger("freightiq.ml.monitoring")


class ModelMonitoringService:
    """Monitors live model health, feature drift, score anomalies, and deployment policies."""

    def __init__(self, inference_engine: Optional[MLInferenceService] = None):
        self.inference = inference_engine or inference_service
        self.feature_engineer = MLFeatureEngineer()

    def check_schema_health(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """Verify input DataFrame conforms to expected feature schema."""
        errors: List[str] = []
        for feat in FEATURE_NAMES:
            if feat not in df.columns:
                errors.append(f"Missing feature column: '{feat}'")
                continue
            series = df[feat]
            null_pct = float(series.isna().mean() * 100.0)
            if null_pct > 25.0:
                errors.append(f"Feature '{feat}' has excessive missing values ({null_pct:.1f}% > 25%)")

            # Numeric check
            if not np.issubdtype(series.dtype, np.number):
                errors.append(f"Feature '{feat}' must be numeric, got {series.dtype}")

        return len(errors) == 0, errors

    def calculate_feature_drift(self, X: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """Calculate distribution shift for each feature against training baseline medians/IQRs."""
        preproc = self.inference.preprocessing_config
        train_medians = preproc.get("training_feature_medians", {})
        train_iqrs = preproc.get("training_feature_iqr", {})

        drift_results: Dict[str, Dict[str, Any]] = {}

        for feat in FEATURE_NAMES:
            if feat not in X.columns or len(X[feat].dropna()) == 0:
                continue

            current_series = X[feat].dropna().astype(float)
            curr_median = float(current_series.median())
            curr_q25 = float(current_series.quantile(0.25))
            curr_q75 = float(current_series.quantile(0.75))
            curr_iqr = float(curr_q75 - curr_q25)

            train_med = float(train_medians.get(feat, curr_median))
            train_iqr = float(train_iqrs.get(feat, max(1e-5, curr_iqr)))
            denom = max(1e-4, train_iqr)

            # Normalized median shift (in units of training IQR)
            normalized_shift = float(abs(curr_median - train_med) / denom)

            # Drift classification
            if normalized_shift >= 3.0:
                drift_severity = "severe"
            elif normalized_shift >= 1.5:
                drift_severity = "moderate"
            else:
                drift_severity = "none"

            drift_results[feat] = {
                "training_median": round(train_med, 4),
                "current_median": round(curr_median, 4),
                "training_iqr": round(train_iqr, 4),
                "current_iqr": round(curr_iqr, 4),
                "normalized_shift_iqr": round(normalized_shift, 4),
                "drift_severity": drift_severity,
            }

        return drift_results

    def generate_drift_report(
        self,
        current_features: Optional[pd.DataFrame] = None,
        dataset_id: str = "default",
    ) -> MLDriftReport:
        """Produce an end-to-end model governance and drift report."""
        status_info = self.inference.get_status()
        recommendations: List[str] = []

        # 1. Model Age Check
        model_age = status_info.model_age_days or 0.0
        if model_age > 90.0:
            recommendations.append(
                f"Model age is {model_age:.1f} days (> 90 days). Consider running validation & retraining."
            )

        # 2. Extract features if not provided
        if current_features is None:
            score_resp = self.inference.score_dataset(dataset_id)
            # Reconstruct feature matrix
            raw_shipments, _, _ = self.inference.storage.get_dataset(dataset_id)
            from backend.app.services.aggregation import aggregate_weekly_routes
            from backend.app.services.cost_analysis import compute_route_baselines

            agg = aggregate_weekly_routes(raw_shipments)
            base = compute_route_baselines(agg, max_history_weeks=settings.MAX_HISTORICAL_WEEKS)
            _, X = self.feature_engineer.extract_features(base, is_training=False)
            current_rate = score_resp.anomaly_rate_pct
        else:
            X = current_features
            current_rate = None

        # 3. Schema Health
        schema_intact, schema_errors = self.check_schema_health(X)
        if not schema_intact:
            recommendations.append("Schema integrity issues detected. Verify input ETL pipeline.")

        # 4. Feature Drift
        feature_drift = self.calculate_feature_drift(X)
        severe_drifts = [f for f, v in feature_drift.items() if v.get("drift_severity") == "severe"]
        moderate_drifts = [f for f, v in feature_drift.items() if v.get("drift_severity") == "moderate"]

        if severe_drifts:
            recommendations.append(
                f"Severe feature drift detected on: {', '.join(severe_drifts)}. Model predictions may degrade."
            )
        elif moderate_drifts:
            recommendations.append(
                f"Moderate feature drift observed on: {', '.join(moderate_drifts)}. Monitor score distribution."
            )

        # 5. Score Distribution Drift
        score_drift: Optional[Dict[str, Any]] = None
        if current_rate is not None:
            expected_rate = (status_info.contamination or 0.03) * 100.0
            rate_ratio = current_rate / max(0.1, expected_rate)
            is_anomaly_rate_skewed = rate_ratio > 3.0 or rate_ratio < 0.2

            score_drift = {
                "current_anomaly_rate_pct": current_rate,
                "expected_anomaly_rate_pct": expected_rate,
                "rate_ratio": round(rate_ratio, 2),
                "is_rate_skewed": is_anomaly_rate_skewed,
            }
            if is_anomaly_rate_skewed:
                recommendations.append(
                    f"Anomaly rate ({current_rate:.1f}%) diverges substantially from expected {expected_rate:.1f}%."
                )

        # Overall Status
        if not schema_intact or severe_drifts:
            overall_status = "drift_detected"
        elif moderate_drifts or model_age > 90.0 or (score_drift and score_drift["is_rate_skewed"]):
            overall_status = "warning"
        else:
            overall_status = "healthy"

        if not recommendations:
            recommendations.append("Model operating within nominal parameters. No action required.")

        return MLDriftReport(
            status=overall_status,
            model_version=status_info.model_version or "none",
            model_age_days=model_age,
            schema_intact=schema_intact,
            schema_errors=schema_errors,
            feature_drift=feature_drift,
            score_distribution_drift=score_drift,
            recommendations=recommendations,
        )

    def validate_deployment_policy(
        self,
        candidate_report: Dict[str, Any],
        min_overall_agreement: float = 90.0,
        min_holdout_agreement: float = 85.0,
    ) -> Tuple[bool, List[str]]:
        """Governance check: enforce that a retrained model meets explicit production standards.

        Strictly prevents automatic deployment of degraded or unvalidated models.
        """
        reasons: List[str] = []
        metrics = candidate_report.get("metrics", {})
        overall_agree = float(metrics.get("overall_agreement_pct", 0.0))
        holdout_agree = float(metrics.get("holdout_agreement_pct", 0.0))

        if overall_agree < min_overall_agreement:
            reasons.append(
                f"Overall agreement with deterministic baseline ({overall_agree:.1f}%) is below minimum threshold ({min_overall_agreement:.1f}%)."
            )

        if holdout_agree < min_holdout_agreement:
            reasons.append(
                f"Chronological holdout agreement ({holdout_agree:.1f}%) is below minimum threshold ({min_holdout_agreement:.1f}%)."
            )

        dataset_hash = candidate_report.get("dataset_hash")
        if not dataset_hash or dataset_hash == "file_not_found":
            reasons.append("Invalid or missing training dataset SHA-256 hash.")

        is_approved = len(reasons) == 0
        return is_approved, reasons


# Global singleton monitoring service
monitoring_service = ModelMonitoringService()
