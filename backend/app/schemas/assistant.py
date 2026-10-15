"""Schemas for the grounded AI assistant and LLM provider interface."""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class AssistantQueryRequest(BaseModel):
    """User query request payload."""

    query: str = Field(..., min_length=2, max_length=500, description="Natural language question")
    route: Optional[str] = Field(None, description="Optional target route scope filter")
    week_of: Optional[str] = Field(None, description="Optional week filter (YYYY-MM-DD)")


class AssistantSource(BaseModel):
    """Citation source for a grounded statement."""

    type: str = Field(..., description="'analysis_record', 'context_note', or 'baseline_rule'")
    id: str = Field(..., description="Unique record or note identifier")
    description: str = Field(..., description="Short summary of the evidence cited")


class AssistantFact(BaseModel):
    """Verified factual point derived from analytical calculations."""

    statement: str
    verified: bool = True


class AssistantQueryResponse(BaseModel):
    """Grounded assistant response with verifiable citations and model status."""

    query: str
    answer: str
    mode: str = Field(default="deterministic", description="'deterministic' or 'llm'")
    model: str = Field(default="deterministic-rules-engine", description="Active model or engine")
    grounded_facts: List[AssistantFact] = Field(default_factory=list)
    sources: List[AssistantSource] = Field(default_factory=list)
    execution_time_ms: float
