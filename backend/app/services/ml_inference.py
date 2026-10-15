"""ML inference service with safe artifact loading, schema validation, and transparent fallback.

Provides high-throughput scoring of weekly route freight observations.
If no validated model is present or artifacts are unreadable, transparently
operates in fallback mode using deterministic baseline deviation heuristics.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

from backend.app.core.config import settings
from backend.app.schemas.ml import (
    MLModelStatus,
    MLPredictionItem,
    MLScoreRequest,
    MLScoreResponse,
)
from backend.app.services.aggregation import aggregate_weekly_routes
from backend.app.services.anomaly_detection import AnomalyDetector
from backend.app.services.cost_analysis import compute_route_baselines
from backend.app.services.ml_features import FEATURE_NAMES, MLFeatureEngineer
from backend.app.services.storage import StorageManager, storage

logger = logging.getLogger("freightiq.ml.inference")


class MLInferenceService:
    """Safe singleton inference engine for FreightIQ anomaly scoring."""

    def __init__(
        self,
        artifacts_dir: Optional[Path] = None,
        storage_service: Optional[StorageManager] = None,
    ):
        self.artifacts_dir = artifacts_dir or settings.MODELS_DIR
        self.storage = storage_service or storage
        self.feature_engineer = MLFeatureEngineer()
        self.model: Optional[Any] = None
        self.scaler: Optional[RobustScaler] = None
        self.metadata: Dict[str, Any] = {}
        self.preprocessing_config: Dict[str, Any] = {}
        self.feature_schema: Dict[str, Any] = {}
        self.is_loaded: bool = False
        self.load_error: Optional[str] = None

        # Attempt safe initialization
        self.reload_model()

    def reload_model(self) -> bool:
        """Safely load model artifacts from the artifacts directory."""
        self.is_loaded = False
        self.load_error = None
        model_file = self.artifacts_dir / "model.joblib"
        meta_file = self.artifacts_dir / "metadata.json"
        preproc_file = self.artifacts_dir / "preprocessing_config.json"
        schema_file = self.artifacts_dir / "feature_schema.json"

        # Check artifact existence
        if not (model_file.exists() and meta_file.exists() and preproc_file.exists()):
            self.load_error = (
                f"Missing model artifacts in {self.artifacts_dir}. Run training command to generate them."
            )
            logger.info("ML Inference Service initialized in FALLBACK mode: %s", self.load_error)
            return False

        try:
            # 1. Load metadata
            with open(meta_file, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)

            # 2. Load preprocessing config
            with open(preproc_file, "r", encoding="utf-8") as f:
                self.preprocessing_config = json.load(f)

            # 3. Load feature schema if available
            if schema_file.exists():
                with open(schema_file, "r", encoding="utf-8") as f:
                    self.feature_schema = json.load(f)

            # 4. Reconstruct RobustScaler from serialized parameters
            scaler = RobustScaler()
            scaler.center_ = np.array(self.preprocessing_config["center"], dtype=np.float64)
            scaler.scale_ = np.array(self.preprocessing_config["scale"], dtype=np.float64)
            scaler.n_features_in_ = len(self.preprocessing_config["feature_names"])
            scaler.feature_names_in_ = np.array(self.preprocessing_config["feature_names"], dtype=object)
            self.scaler = scaler

            # 5. Load model estimator safely
            self.model = joblib.load(model_file)
            self.is_loaded = True
            logger.info(
                "Successfully loaded ML model version: %s (samples: %s)",
                self.metadata.get("model_version", "unknown"),
                self.metadata.get("training_samples", "unknown"),
            )
            return True
        except Exception as e:
            self.load_error = f"Failed to deserialize model artifacts: {str(e)}"
            logger.error("Error loading ML model artifacts: %s", e)
            self.model = None
            self.scaler = None
            self.is_loaded = False
            return False

    def get_status(self) -> MLModelStatus:
        """Return comprehensive governance status of current model."""
        if not self.is_loaded:
            return MLModelStatus(
                status="not_trained" if "Missing" in (self.load_error or "") else "error",
                is_ready=False,
                model_version=None,
                algorithm="IsolationForest",
                fallback_active=True,
                message=self.load_error or "Model not loaded. Using transparent fallback.",
            )

        # Calculate model age
        train_date_str = self.metadata.get("training_date")
        age_days: Optional[float] = None
        if train_date_str:
            try:
                train_dt = datetime.fromisoformat(train_date_str.replace("Z", "+00:00"))
                age_days = round((datetime.now(timezone.utc) - train_dt).total_seconds() / 86400.0, 2)
            except Exception:
                age_days = None

        is_stale = age_days is not None and age_days > 90.0

        return MLModelStatus(
            status="stale" if is_stale else "ready",
            is_ready=True,
            model_version=self.metadata.get("model_version"),
            algorithm=self.metadata.get("algorithm", "IsolationForest"),
            training_date=train_date_str,
            model_age_days=age_days,
            training_samples=self.metadata.get("training_samples"),
            training_data_hash=self.metadata.get("training_data_hash"),
            features_used=self.metadata.get("features_used", FEATURE_NAMES),
            contamination=self.metadata.get("hyperparameters", {}).get("contamination"),
            n_estimators=self.metadata.get("hyperparameters", {}).get("n_estimators"),
            random_state=self.metadata.get("hyperparameters", {}).get("random_state"),
            agreement_with_baseline_pct=self.metadata.get("agreement_with_baseline_pct"),
            fallback_active=False,
            message="Model validated and operating normally." if not is_stale else "Model is older than 90 days. Retraining recommended.",
        )

    def score_feature_matrix(
        self,
        X: pd.DataFrame,
        context_df: Optional[pd.DataFrame] = None,
    ) -> List[MLPredictionItem]:
        """Score an extracted feature matrix, supporting both model execution and fallback mode."""
        valid, errors = self.feature_engineer.validate_schema(X)
        if not valid:
            logger.warning("Feature schema validation issues: %s", errors)
            # Impute missing features safely
            for feat in FEATURE_NAMES:
                if feat not in X.columns:
                    X[feat] = 0.0

        n_rows = len(X)
        if n_rows == 0:
            return []

        # Route/week metadata from context_df if provided
        routes = context_df["route"].tolist() if context_df is not None and "route" in context_df.columns else [None] * n_rows
        weeks = context_df["week_of"].tolist() if context_df is not None and "week_of" in context_df.columns else [None] * n_rows
        costs = context_df["cost_per_tonne_km"].tolist() if context_df is not None and "cost_per_tonne_km" in context_df.columns else [None] * n_rows
        det_flags = context_df["deterministic_flagged"].tolist() if context_df is not None and "deterministic_flagged" in context_df.columns else [None] * n_rows

        if not self.is_loaded or self.model is None or self.scaler is None:
            # TRANSPARENT FALLBACK MODE:
            # Deterministic deviation heuristic without ML
            logger.debug("Executing transparent rule-based fallback scoring.")
            items: List[MLPredictionItem] = []
            for i in range(n_rows):
                row = X.iloc[i]
                pct_hist = max(0.0, float(row.get("pct_vs_history", 0.0)))
                pct_peer = max(0.0, float(row.get("pct_vs_peers", 0.0)))
                max_dev = max(pct_hist, pct_peer)

                # Fallback anomaly score: normalized between 0.0 and 1.0 (reaches 1.0 at 50% deviation)
                norm_score = float(np.clip(max_dev / 50.0, 0.0, 1.0))
                is_anomaly = bool(max_dev >= settings.DEFAULT_ANOMALY_THRESHOLD_PCT)

                tier = (
                    "CRITICAL" if norm_score >= 0.85
                    else "ELEVATED" if norm_score >= 0.70
                    else "MODERATE" if norm_score >= 0.50
                    else "LOW"
                )

                d_flag = det_flags[i]
                agreement = (is_anomaly == d_flag) if d_flag is not None else None

                items.append(
                    MLPredictionItem(
                        route=routes[i],
                        week_of=weeks[i],
                        cost_per_tonne_km=costs[i],
                        raw_decision_score=round(-max_dev / 100.0, 4),
                        ml_anomaly_score=round(norm_score, 4),
                        is_ml_anomaly=is_anomaly,
                        deterministic_flagged=d_flag,
                        agreement=agreement,
                        score_tier=tier,
                    )
                )
            return items

        # MODEL EXECUTION MODE:
        X_feats = X[FEATURE_NAMES].copy().astype(np.float64)
        X_scaled = self.scaler.transform(X_feats)
        raw_scores = self.model.decision_function(X_scaled)
        preds = self.model.predict(X_scaled)

        calib = self.preprocessing_config.get("score_calibration", {})
        max_score = calib.get("max_score", float(np.percentile(raw_scores, 99.5)))
        score_range = calib.get("score_range", 0.5)

        items: List[MLPredictionItem] = []
        for i in range(n_rows):
            raw = float(raw_scores[i])
            is_anomaly = bool(preds[i] == -1)

            # Inverted normalized score: higher is more anomalous
            norm_score = float(np.clip((max_score - raw) / score_range, 0.0, 1.0))

            tier = (
                "CRITICAL" if norm_score >= 0.85
                else "ELEVATED" if norm_score >= 0.70
                else "MODERATE" if norm_score >= 0.50
                else "LOW"
            )

            d_flag = det_flags[i]
            agreement = (is_anomaly == d_flag) if d_flag is not None else None

            items.append(
                MLPredictionItem(
                    route=routes[i],
                    week_of=weeks[i],
                    cost_per_tonne_km=costs[i],
                    raw_decision_score=round(raw, 4),
                    ml_anomaly_score=round(norm_score, 4),
                    is_ml_anomaly=is_anomaly,
                    deterministic_flagged=d_flag,
                    agreement=agreement,
                    score_tier=tier,
                )
            )

        return items

    def score_dataset(self, dataset_id: str = "default") -> MLScoreResponse:
        """Run full weekly aggregation, baseline calculation, and ML scoring on a stored dataset."""
        raw_shipments, notes, _ = self.storage.get_dataset(dataset_id)
        agg_df = aggregate_weekly_routes(raw_shipments)
        baseline_df = compute_route_baselines(agg_df, max_history_weeks=settings.MAX_HISTORICAL_WEEKS)

        detector = AnomalyDetector(
            threshold_pct=settings.DEFAULT_ANOMALY_THRESHOLD_PCT,
            note_window_days=settings.NOTE_DATE_WINDOW_DAYS,
        )
        flagged_df, _ = detector.detect_anomalies(baseline_df, notes)
        flagged_df["deterministic_flagged"] = flagged_df["flagged"].astype(bool)

        engineered_df, X = self.feature_engineer.extract_features(flagged_df, is_training=False)
        predictions = self.score_feature_matrix(X, context_df=engineered_df)

        anomaly_count = sum(1 for p in predictions if p.is_ml_anomaly)
        total = len(predictions)
        rate_pct = round(anomaly_count / max(1, total) * 100.0, 2)

        return MLScoreResponse(
            model_version=self.metadata.get("model_version", "fallback-rule-heuristic")
            if self.is_loaded
            else "fallback-rule-heuristic",
            algorithm=self.metadata.get("algorithm", "IsolationForest")
            if self.is_loaded
            else "RuleHeuristicFallback",
            scored_count=total,
            anomaly_count=anomaly_count,
            anomaly_rate_pct=rate_pct,
            fallback_used=not self.is_loaded,
            predictions=predictions,
            warning=self.load_error if not self.is_loaded else None,
        )


# Global singleton inference service
inference_service = MLInferenceService()
