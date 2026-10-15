"""Schemas for evaluation harness, reproducibility benchmarks, and token/cost tracking."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ReproducibilityResponse(BaseModel):
    """Result of multi-run deterministic comparison."""

    num_runs: int
    is_reproducible: bool
    total_records: int
    flagged_total: int
    justified_count: int
    unexplained_count: int
    discrepancies: List[str] = Field(default_factory=list)
    execution_duration_ms: float


class UnitCheckItem(BaseModel):
    """Individual rule verification check."""

    name: str
    passed: bool
    error: Optional[str] = None


class EvaluationTestsResponse(BaseModel):
    """Execution results for the programmatic verification test suite."""

    total_tests: int
    passed: int
    failed: int
    all_passed: bool
    checks: List[UnitCheckItem]
    execution_duration_ms: float


class UsageRunResponse(BaseModel):
    """Cost and resource accounting for an analysis or model execution."""

    run_id: str
    model: str = "Not connected"
    model_version: str = "none"
    provider_status: str = "Deterministic local execution (zero provider API cost)"
    llm_calls: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: float = 0.0
    execution_duration_ms: float = 0.0
