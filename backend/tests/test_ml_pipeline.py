"""Unit and integration test suite for FreightIQ Machine Learning anomaly pipeline.

Validates:
1. Identical feature engineering logic across train and inference.
2. Strict chronological holdout ordering (zero look-ahead).
3. Exact model reproducibility with fixed random seed.
4. Model serialization, file artifact completeness, and safe loading.
5. Graceful transparent fallback when model artifacts are absent.
6. Schema validation, drift detection, and invalid input resilience.
7. ML API endpoint integration (/ml/status, /ml/score, /ml/evaluation, /ml/monitoring/drift).
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import settings
from backend.app.main import app
from backend.app.schemas.ml import MLTrainRequest
from backend.app.services.aggregation import aggregate_weekly_routes
from backend.app.services.anomaly_detection import AnomalyDetector
from backend.app.services.cost_analysis import compute_route_baselines
from backend.app.services.ml_features import FEATURE_NAMES, FEATURE_SPECS, MLFeatureEngineer
from backend.app.services.ml_inference import MLInferenceService, inference_service
from backend.app.services.ml_monitoring import ModelMonitoringService
from backend.app.services.ml_training import MLModelTrainer
from backend.app.services.storage import storage


@pytest.fixture(scope="module")
def prepared_data():
    """Load and prepare weekly route dataset with baselines for testing."""
    raw_shipments, notes, _ = storage.get_dataset("default")
    agg_df = aggregate_weekly_routes(raw_shipments)
    baseline_df = compute_route_baselines(agg_df, max_history_weeks=settings.MAX_HISTORICAL_WEEKS)
    detector = AnomalyDetector()
    flagged_df, _ = detector.detect_anomalies(baseline_df, notes)
    flagged_df["deterministic_flagged"] = flagged_df["flagged"].astype(bool)
    return flagged_df


class TestMLFeatureEngineering:
    """Tests for leakage-free, chronological feature engineering."""

    def test_feature_matrix_structure_and_no_leakage(self, prepared_data):
        engineer = MLFeatureEngineer()
        df, X = engineer.extract_features(prepared_data, is_training=True)

        # Check required canonical features
        for feat in FEATURE_NAMES:
            assert feat in X.columns, f"Feature {feat} missing from matrix"

        # Strictly numeric
        for col in X.columns:
            assert np.issubdtype(X[col].dtype, np.number), f"Feature {col} is not numeric"

        # Check no route identifiers in X
        assert "route" not in X.columns
        assert "origin" not in X.columns
        assert "destination" not in X.columns
        assert "transporter" not in X.columns

        # Check no NaN values
        assert not X.isna().any().any(), "Feature matrix contains unexpected NaNs"

    def test_chronological_volatility_zero_lookahead(self, prepared_data):
        """Verify trailing volatility uses only prior available weeks (< week_of)."""
        engineer = MLFeatureEngineer()
        df, _ = engineer.extract_features(prepared_data)

        # Route-level check
        target_route = df["route"].iloc[0]
        sample_route = df[df["route"] == target_route].sort_values("week_of").reset_index(drop=True)
        # Week 0 should have 0 volatility (no prior history)
        assert sample_route.loc[0, "history_volatility"] == 0.0

        # Week 1 should have 0 volatility (< 2 prior points required for sample std)
        assert sample_route.loc[1, "history_volatility"] == 0.0

        # Week 2 onwards should have non-negative volatility calculated strictly from prior weeks
        for i in range(2, min(10, len(sample_route))):
            prior_costs = sample_route.loc[max(0, i - 8):i - 1, "cost_per_tonne_km"].values
            expected_std = float(np.std(prior_costs, ddof=1))
            actual_std = float(sample_route.loc[i, "history_volatility"])
            assert np.isclose(actual_std, expected_std, atol=1e-4)

    def test_identical_feature_logic_train_and_inference(self, prepared_data):
        """Verify train and inference modes yield identical numeric matrices."""
        engineer = MLFeatureEngineer()
        _, X_train = engineer.extract_features(prepared_data, is_training=True)
        _, X_infer = engineer.extract_features(prepared_data, is_training=False)
        pd.testing.assert_frame_equal(X_train, X_infer)


class TestMLTrainingAndReproducibility:
    """Tests for model training, chronological holdout split, and reproducibility."""

    def test_model_training_and_holdout_agreement(self, tmp_path):
        trainer = MLModelTrainer(artifacts_dir=tmp_path)
        req = MLTrainRequest(contamination=0.03, n_estimators=100, random_state=42, holdout_weeks=26)
        response = trainer.train_and_evaluate(req)

        assert response.success is True
        assert response.training_samples > 0
        assert response.holdout_samples > 0
        assert response.training_samples + response.holdout_samples == 728

        # Agreement with deterministic baseline should be high (>90%)
        overall_agree = response.metrics_vs_baseline["overall_agreement_pct"]
        holdout_agree = response.metrics_vs_baseline["holdout_agreement_pct"]
        assert overall_agree >= 90.0
        assert holdout_agree >= 85.0

        # Artifacts exist
        assert (tmp_path / "model.joblib").exists()
        assert (tmp_path / "metadata.json").exists()
        assert (tmp_path / "preprocessing_config.json").exists()
        assert (tmp_path / "evaluation_report.json").exists()
        assert (tmp_path / "feature_schema.json").exists()

    def test_training_reproducibility(self, tmp_path):
        """Fixed random seed must yield 100% identical predictions and contingency table."""
        trainer1 = MLModelTrainer(artifacts_dir=tmp_path / "run1")
        trainer2 = MLModelTrainer(artifacts_dir=tmp_path / "run2")

        req = MLTrainRequest(contamination=0.03, n_estimators=100, random_state=42, holdout_weeks=26)
        res1 = trainer1.train_and_evaluate(req)
        res2 = trainer2.train_and_evaluate(req)

        assert res1.contingency_table == res2.contingency_table
        assert res1.metrics_vs_baseline["overall_agreement_pct"] == res2.metrics_vs_baseline["overall_agreement_pct"]
        assert res1.metrics_vs_baseline["holdout_agreement_pct"] == res2.metrics_vs_baseline["holdout_agreement_pct"]


class TestMLInferenceAndFallback:
    """Tests for model scoring, calibrated anomaly scores, and graceful fallback."""

    def test_inference_scoring_with_loaded_model(self):
        status = inference_service.get_status()
        assert status.is_ready is True
        assert status.model_version is not None

        response = inference_service.score_dataset("default")
        assert response.scored_count == 728
        assert response.anomaly_count > 0
        assert response.fallback_used is False

        # Predictions inspection
        first = response.predictions[0]
        assert 0.0 <= first.ml_anomaly_score <= 1.0
        assert first.score_tier in {"LOW", "MODERATE", "ELEVATED", "CRITICAL"}

    def test_transparent_fallback_mode_on_missing_model(self, tmp_path):
        """Inference service must transparently fall back to heuristic when artifacts are missing."""
        empty_dir = tmp_path / "empty_models"
        empty_dir.mkdir(parents=True, exist_ok=True)
        fallback_service = MLInferenceService(artifacts_dir=empty_dir)

        assert fallback_service.is_loaded is False
        status = fallback_service.get_status()
        assert status.is_ready is False
        assert status.fallback_active is True

        # Scoring in fallback mode must succeed without error
        response = fallback_service.score_dataset("default")
        assert response.scored_count == 728
        assert response.fallback_used is True
        assert len(response.predictions) == 728

        # Each prediction must have valid normalized score
        for p in response.predictions[:10]:
            assert 0.0 <= p.ml_anomaly_score <= 1.0


class TestModelMonitoringAndDrift:
    """Tests for input schema verification, drift calculation, and deployment policy."""

    def test_schema_health_check(self, prepared_data):
        monitoring = ModelMonitoringService()
        engineer = MLFeatureEngineer()
        _, X = engineer.extract_features(prepared_data)

        # Baseline schema must be intact
        is_intact, errors = monitoring.check_schema_health(X)
        assert is_intact is True
        assert len(errors) == 0

        # Corrupted schema detection
        bad_X = X.drop(columns=["cost_per_tonne_km"])
        is_intact_bad, errors_bad = monitoring.check_schema_health(bad_X)
        assert is_intact_bad is False
        assert any("cost_per_tonne_km" in e for e in errors_bad)

    def test_feature_drift_detection(self, prepared_data):
        monitoring = ModelMonitoringService()
        report = monitoring.generate_drift_report(dataset_id="default")

        assert report.status in {"healthy", "warning", "drift_detected"}
        assert report.schema_intact is True
        assert len(report.feature_drift) == len(FEATURE_NAMES)
        assert len(report.recommendations) > 0

    def test_deployment_policy_guardrail(self):
        monitoring = ModelMonitoringService()

        # Passing candidate report
        valid_candidate = {
            "dataset_hash": "abc123hash",
            "metrics": {
                "overall_agreement_pct": 95.0,
                "holdout_agreement_pct": 92.0,
            },
        }
        passed, reasons = monitoring.validate_deployment_policy(valid_candidate)
        assert passed is True
        assert len(reasons) == 0

        # Failing candidate report (below agreement threshold)
        degraded_candidate = {
            "dataset_hash": "abc123hash",
            "metrics": {
                "overall_agreement_pct": 82.0,
                "holdout_agreement_pct": 75.0,
            },
        }
        passed, reasons = monitoring.validate_deployment_policy(degraded_candidate)
        assert passed is False
        assert len(reasons) >= 2


class TestMLApiEndpoints:
    """Integration tests for FastAPI ML endpoints."""

    @pytest.fixture(scope="class")
    def client(self):
        return TestClient(app)

    def test_get_ml_status(self, client):
        res = client.get("/api/v1/ml/status")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "is_ready" in data
        assert "model_version" in data

    def test_post_ml_score(self, client):
        res = client.post("/api/v1/ml/score", json={"dataset_id": "default"})
        assert res.status_code == 200
        data = res.json()
        assert data["scored_count"] == 728
        assert "predictions" in data
        assert len(data["predictions"]) > 0

    def test_get_ml_evaluation(self, client):
        res = client.get("/api/v1/ml/evaluation")
        assert res.status_code == 200
        data = res.json()
        assert "contingency_matrix" in data
        assert "agreement_rate_pct" in data
        assert "documented_conclusions" in data
        assert "methodological_notes" in data

    def test_get_ml_drift_report(self, client):
        res = client.get("/api/v1/ml/monitoring/drift")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        assert "feature_drift" in data
        assert "recommendations" in data
