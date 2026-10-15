"""Pydantic schemas and data transfer objects for FreightIQ Analytics."""

from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class ShipmentRecord(BaseModel):
    """Schema for individual shipment records."""

    shipment_id: str
    origin: str
    destination: str
    route_type: Literal["Short", "Medium", "Long"]
    material: str
    quantity_tonnes: float = Field(gt=0, description="Payload weight in tonnes")
    distance_km: float = Field(gt=0, description="Transit distance in kilometers")
    freight_cost_inr: float = Field(ge=0, description="Total freight cost in INR")
    shipment_date: date
    transporter: str

    @property
    def canonical_route(self) -> str:
        return f"{self.origin.strip()}-{self.destination.strip()}"

    @property
    def work_done_tonne_km(self) -> float:
        return self.quantity_tonnes * self.distance_km


class ContextNote(BaseModel):
    """Schema for qualitative context notes with guardrail classification."""

    note_id: str
    date: date
    applies_to: str
    note: str

    @property
    def is_cost_driver(self) -> bool:
        """Evaluate whether this note describes a genuine upward cost driver.

        Guardrail: Notes that describe unaffected costs, stable conditions,
        improved roads, or unassociated toll plazas must not justify a cost spike.
        """
        text = self.note.lower()
        negative_indicators = [
            "costs were not significantly affected",
            "not part of this dataset",
            "without a rate change",
            "no major disruptions",
            "no significant disruptions",
            "movement remained normal",
            "returned to normal conditions",
            "improved road conditions",
        ]
        if any(neg in text for neg in negative_indicators):
            return False

        positive_indicators = [
            "higher trip costs",
            "detours",
            "temporary surcharge",
            "pushing up transportation costs",
            "diesel prices rose",
            "disrupted normal truck movement",
        ]
        return any(pos in text for pos in positive_indicators)


class RouteWeekAggregate(BaseModel):
    """Schema for aggregated weekly route metrics."""

    origin: str
    destination: str
    route: str
    route_type: Literal["Short", "Medium", "Long"]
    week_of: date
    total_cost: float
    total_work_tonne_km: float
    shipment_count: int
    cost_per_tonne_km: float


class RouteWeekAnalysis(BaseModel):
    """Complete analytical record with baseline comparisons and verdicts."""

    route: str
    origin: str
    destination: str
    route_type: str
    week_of: str  # YYYY-MM-DD (Monday)
    cost_per_tonne_km: float
    vs_own_history: Optional[float] = None
    vs_similar_routes: Optional[float] = None
    pct_vs_history: Optional[float] = None
    pct_vs_peers: Optional[float] = None
    history_count: int = 0
    peer_count: int = 0
    is_rising: bool = False
    flagged: bool = False
    flagged_label: str = "No"  # "Yes", "No (justified)", "No"
    matched_note_id: str = ""
    reason: str = ""


class OutputContractRow(BaseModel):
    """Exact eight-column output schema required by the case study."""

    route: str
    week_of: str
    cost_per_tonne_km: float
    vs_own_history: str
    vs_similar_routes: str
    flagged: str
    matched_note_id: str
    reason: str


class ValidationIssue(BaseModel):
    """Data quality or schema issue descriptor."""

    row_index: int
    field: str
    value: str
    issue: str


class DataQualityReport(BaseModel):
    """Summary report of dataset quality and validation results."""

    total_records: int
    valid_records: int
    invalid_records: int
    null_counts: dict[str, int]
    negative_or_zero_values: dict[str, int]
    unique_routes: int
    unique_route_types: list[str]
    date_range: tuple[str, str]
    issues: list[ValidationIssue] = Field(default_factory=list)
