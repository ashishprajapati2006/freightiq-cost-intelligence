"""Pydantic schemas for FreightIQ Machine Learning anomaly detection pipeline.

Provides structured models for model status, training parameters, scoring requests/responses,
governance evaluation metrics, and drift monitoring.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MLModelStatus(BaseModel):
    """Status and governance metadata of the current active ML model."""

    status: str = Field(..., description="'ready', 'not_trained', 'stale', or 'drift_detected'")
    is_ready: bool = Field(..., description="Whether a validated model is loaded and ready for inference")
    model_version: Optional[str] = Field(None, description="Unique model version hash or identifier")
    algorithm: str = Field("IsolationForest", description="Underlying algorithm name")
    training_date: Optional[str] = Field(None, description="ISO timestamp of training completion")
    model_age_days: Optional[float] = Field(None, description="Age of current model in days")
    training_samples: Optional[int] = Field(None, description="Number of observation rows in training set")
    training_data_hash: Optional[str] = Field(None, description="SHA-256 hash of training dataset")
    features_used: List[str] = Field(default_factory=list, description="Ordered feature names")
    contamination: Optional[float] = Field(None, description="Contamination parameter used in training")
    n_estimators: Optional[int] = Field(None, description="Number of trees in ensemble")
    random_state: Optional[int] = Field(None, description="Random seed for reproducibility")
    agreement_with_baseline_pct: Optional[float] = Field(
        None, description="Overall agreement rate (%) with deterministic rule in training/holdout"
    )
    fallback_active: bool = Field(False, description="True if inference is running in graceful fallback mode")
    message: Optional[str] = Field(None, description="Descriptive status note or governance warning")


class MLTrainRequest(BaseModel):
    """Parameters to trigger deterministic and reproducible model training."""

    contamination: float = Field(
        0.03,
        ge=0.005,
        le=0.25,
        description="Expected proportion of outliers in the training distribution (default 3%)",
    )
    n_estimators: int = Field(
        150,
        ge=50,
        le=500,
        description="Number of isolation trees in ensemble",
    )
    random_state: int = Field(
        42,
        description="Fixed random seed ensuring 100% reproducible tree structures",
    )
    dataset_id: Optional[str] = Field(
        "default",
        description="Dataset identifier to train on (defaults to bundled canonical records)",
    )
    holdout_weeks: int = Field(
        26,
        ge=4,
        le=52,
        description="Number of trailing weeks reserved for chronological holdout validation",
    )


class MLTrainResponse(BaseModel):
    """Result of an ML model training execution."""

    success: bool
    model_version: str
    message: str
    training_samples: int
    holdout_samples: int
    features_count: int
    training_data_hash: str
    artifacts_saved: List[str]
    metrics_vs_baseline: Dict[str, Any]
    contingency_table: Dict[str, int]
    training_duration_seconds: float


class MLPredictionItem(BaseModel):
    """Anomaly scoring outcome for a single weekly route observation."""

    route: Optional[str] = None
    week_of: Optional[str] = None
    cost_per_tonne_km: Optional[float] = None
    raw_decision_score: float = Field(
        ...,
        description="Raw Isolation Forest decision function score (negative indicates outlier)",
    )
    ml_anomaly_score: float = Field(
        ...,
        description="Normalized anomaly score between 0.0 (normal) and 1.0 (severe outlier)",
    )
    is_ml_anomaly: bool = Field(
        ...,
        description="Boolean classification flag derived from model decision threshold",
    )
    deterministic_flagged: Optional[bool] = Field(
        None,
        description="Authoritative case-study rule verdict (20% baseline deviation)",
    )
    agreement: Optional[bool] = Field(
        None,
        description="True if ML decision matches the deterministic rule verdict",
    )
    score_tier: str = Field(
        "LOW",
        description="Qualitative risk tier: 'LOW', 'MODERATE', 'ELEVATED', 'CRITICAL'",
    )


class MLScoreRequest(BaseModel):
    """Input payload for ML anomaly scoring."""

    dataset_id: Optional[str] = Field("default", description="Dataset identifier to score")
    run_id: Optional[str] = Field(None, description="Analysis run ID to score")
    records: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Optional ad-hoc records containing weekly route features for direct scoring",
    )


class MLScoreResponse(BaseModel):
    """Aggregated scoring response containing predictions and model lineage."""

    model_version: str
    algorithm: str
    scored_count: int
    anomaly_count: int
    anomaly_rate_pct: float
    fallback_used: bool
    predictions: List[MLPredictionItem]
    warning: Optional[str] = None


class MLEvaluationResponse(BaseModel):
    """Full empirical governance evaluation comparing ML against deterministic engine."""

    model_version: str
    evaluation_date: str
    dataset_hash: str
    total_observations: int
    train_observations: int
    holdout_observations: int
    deterministic_flagged_count: int
    ml_flagged_count: int
    contingency_matrix: Dict[str, int]
    agreement_rate_pct: float
    jaccard_similarity: float
    score_quantiles: Dict[str, float]
    feature_importances_proxy: Dict[str, float]
    documented_conclusions: str
    methodological_notes: List[str]


class MLDriftReport(BaseModel):
    """Model monitoring report tracking input schema, feature drift, and model health."""

    status: str = Field(..., description="'healthy', 'warning', or 'drift_detected'")
    model_version: str
    model_age_days: float
    schema_intact: bool
    schema_errors: List[str] = Field(default_factory=list)
    feature_drift: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-feature distribution comparison vs training baseline",
    )
    score_distribution_drift: Optional[Dict[str, Any]] = None
    recommendations: List[str] = Field(default_factory=list)
