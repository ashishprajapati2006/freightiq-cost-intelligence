"""Machine Learning anomaly detection API endpoints for FreightIQ.

Provides endpoints for model status, reproducible training, scoring inference,
governance evaluation reports, and feature drift monitoring.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.core.config import settings
from backend.app.schemas.ml import (
    MLDriftReport,
    MLEvaluationResponse,
    MLModelStatus,
    MLScoreRequest,
    MLScoreResponse,
    MLTrainRequest,
    MLTrainResponse,
)
from backend.app.services.ml_features import FEATURE_NAMES, MLFeatureEngineer
from backend.app.services.ml_inference import inference_service
from backend.app.services.ml_monitoring import monitoring_service
from backend.app.services.ml_training import MLModelTrainer

logger = logging.getLogger("freightiq.api.ml")

router = APIRouter(prefix="/ml", tags=["Machine Learning Anomaly Detection"])


@router.get(
    "/status",
    response_model=MLModelStatus,
    summary="Get current ML model status and governance metadata",
)
def get_ml_status() -> MLModelStatus:
    """Retrieve operational status, version hash, age, and baseline agreement rate of the loaded model."""
    return inference_service.get_status()


@router.post(
    "/train",
    response_model=MLTrainResponse,
    summary="Trigger reproducible model training and baseline evaluation",
)
def train_ml_model(request: Optional[MLTrainRequest] = None) -> MLTrainResponse:
    """Execute chronological holdout training of Isolation Forest.

    Evaluates candidate model against the deterministic baseline and serializes
    versioned model artifacts. Reloads the active inference engine upon completion.
    """
    req = request or MLTrainRequest()
    trainer = MLModelTrainer()
    try:
        result = trainer.train_and_evaluate(req)
        # Hot-reload the active inference service with new artifacts
        inference_service.reload_model()
        return result
    except Exception as e:
        logger.error("ML model training failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model training failed: {str(e)}",
        )


@router.post(
    "/score",
    response_model=MLScoreResponse,
    summary="Score freight observations with calibrated anomaly scores",
)
def score_anomalies(request: Optional[MLScoreRequest] = None) -> MLScoreResponse:
    """Score weekly route observations using the validated ML model or transparent fallback.

    Returns calibrated anomaly scores (0.0 normal - 1.0 critical) alongside deterministic flags.
    """
    req = request or MLScoreRequest()
    try:
        if req.records and len(req.records) > 0:
            import pandas as pd

            rec_df = pd.DataFrame(req.records)
            engineer = MLFeatureEngineer()
            _, X = engineer.extract_features(rec_df, is_training=False)
            items = inference_service.score_feature_matrix(X, context_df=rec_df)
            anomaly_cnt = sum(1 for item in items if item.is_ml_anomaly)
            return MLScoreResponse(
                model_version=inference_service.metadata.get("model_version", "fallback-heuristic")
                if inference_service.is_loaded
                else "fallback-heuristic",
                algorithm="IsolationForest" if inference_service.is_loaded else "RuleHeuristicFallback",
                scored_count=len(items),
                anomaly_count=anomaly_cnt,
                anomaly_rate_pct=round(anomaly_cnt / max(1, len(items)) * 100.0, 2),
                fallback_used=not inference_service.is_loaded,
                predictions=items,
            )
        else:
            dataset_id = req.dataset_id or "default"
            return inference_service.score_dataset(dataset_id)
    except Exception as e:
        logger.error("Scoring failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scoring error: {str(e)}",
        )


@router.get(
    "/evaluation",
    response_model=MLEvaluationResponse,
    summary="Get empirical evaluation report comparing ML against deterministic baseline",
)
def get_ml_evaluation() -> MLEvaluationResponse:
    """Retrieve full governance evaluation report with contingency matrix and documented conclusions."""
    eval_file = settings.MODELS_DIR / "evaluation_report.json"
    if not eval_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No evaluation report found. Train a model first via POST /api/v1/ml/train.",
        )

    try:
        with open(eval_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return MLEvaluationResponse(
            model_version=data.get("model_version", "unknown"),
            evaluation_date=data.get("evaluation_date", ""),
            dataset_hash=data.get("dataset_hash", ""),
            total_observations=data.get("total_observations", 0),
            train_observations=data.get("train_observations", 0),
            holdout_observations=data.get("holdout_observations", 0),
            deterministic_flagged_count=data.get("contingency_matrix_full", {}).get("both_flagged", 0)
            + data.get("contingency_matrix_full", {}).get("det_only", 0),
            ml_flagged_count=data.get("contingency_matrix_full", {}).get("both_flagged", 0)
            + data.get("contingency_matrix_full", {}).get("ml_only", 0),
            contingency_matrix=data.get("contingency_matrix_full", {}),
            agreement_rate_pct=data.get("metrics", {}).get("overall_agreement_pct", 0.0),
            jaccard_similarity=data.get("metrics", {}).get("overall_jaccard", 0.0),
            score_quantiles=data.get("metrics", {}).get("score_quantiles", {}),
            feature_importances_proxy={feat: 1.0 for feat in FEATURE_NAMES},
            documented_conclusions=data.get("documented_conclusions", ""),
            methodological_notes=data.get("methodological_notes", []),
        )
    except Exception as e:
        logger.error("Failed to read evaluation report: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reading evaluation report: {str(e)}",
        )


@router.get(
    "/monitoring/drift",
    response_model=MLDriftReport,
    summary="Get feature distribution drift and model health report",
)
def get_ml_drift_report(
    dataset_id: str = Query("default", description="Dataset ID to check against training baseline")
) -> MLDriftReport:
    """Analyze input schema health, feature drift vs training IQRs, and score distribution stability."""
    try:
        return monitoring_service.generate_drift_report(dataset_id=dataset_id)
    except Exception as e:
        logger.error("Failed to generate drift report: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating drift report: {str(e)}",
        )
