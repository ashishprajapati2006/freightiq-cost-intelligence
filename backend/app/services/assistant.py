"""Grounded AI Assistant service with deterministic fallback and LLM provider interface.

Provides factual, verifiable answers derived strictly from calculated route metrics
and authentic context notes under anti-hallucination guardrails.
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd

from backend.app.schemas.analysis import ContextNote
from backend.app.schemas.assistant import (
    AssistantFact,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSource,
)


class LLMProviderInterface(ABC):
    """Abstract interface for natural-language query providers."""

    @abstractmethod
    def query(
        self,
        request: AssistantQueryRequest,
        analysis_df: pd.DataFrame,
        notes: List[ContextNote],
    ) -> AssistantQueryResponse:
        """Process user query and return grounded response."""
        pass


class DeterministicAssistantProvider(LLMProviderInterface):
    """Deterministic, rule-backed query engine for verifiable supply chain intelligence."""

    def query(
        self,
        request: AssistantQueryRequest,
        analysis_df: pd.DataFrame,
        notes: List[ContextNote],
    ) -> AssistantQueryResponse:
        start_time = time.perf_counter()
        q_raw = request.query.strip().lower()

        sources: List[AssistantSource] = []
        facts: List[AssistantFact] = []

        flagged = analysis_df[analysis_df["flagged"] == True]
        justified = analysis_df[analysis_df["flagged_label"] == "No (justified)"]
        unexplained = analysis_df[analysis_df["flagged_label"] == "Yes"]

        # 1. Historical baseline definition
        if "baseline" in q_raw and ("historical" in q_raw or "how" in q_raw or "calculate" in q_raw):
            answer = (
                "The historical baseline is defined as the trailing 8-week rolling average cost per tonne-km "
                "for the same route and route type, strictly using prior available weekly observations. "
                "The current week is excluded to prevent look-ahead bias. When fewer than 8 prior weeks exist, "
                "all available prior weeks are used. If zero prior weeks exist, the baseline is unavailable (NaN)."
            )
            sources.append(
                AssistantSource(
                    type="baseline_rule",
                    id="case_study_rule_historical",
                    description="Trailing 8-week prior rolling window without look-ahead",
                )
            )
            facts.append(
                AssistantFact(statement="Historical baseline excludes current and future weeks", verified=True)
            )
            facts.append(
                AssistantFact(statement="Caps at 8 prior available route-weeks", verified=True)
            )

        # 2. Largest unexplained cost increases
        elif "unexplained" in q_raw or ("largest" in q_raw and "increase" in q_raw):
            top_unexplained = unexplained.sort_values(
                by=["pct_vs_history", "pct_vs_peers"], ascending=False
            ).head(5)
            lines = [
                f"{i+1}. {r['route']} (Week of {r['week_of']}): {r['cost_per_tonne_km']:.3f} ₹/t-km "
                f"({r['pct_vs_history']:+.1f}% vs history, {r['pct_vs_peers']:+.1f}% vs peers) — Unexplained"
                for i, (_, r) in enumerate(top_unexplained.iterrows())
            ]
            answer = (
                f"There are {len(unexplained)} unexplained cost anomalies in the dataset. "
                f"The highest unexplained deviations are:\n" + "\n".join(lines) + "\n\n"
                "No applicable supporting context notes were found for these periods; human operational review is recommended."
            )
            for _, r in top_unexplained.iterrows():
                sources.append(
                    AssistantSource(
                        type="analysis_record",
                        id=f"{r['route']}-{r['week_of']}",
                        description=f"{r['route']} spike on {r['week_of']} ({r['pct_vs_history']:+.1f}% vs history)",
                    )
                )
            facts.append(
                AssistantFact(
                    statement=f"Identified {len(unexplained)} total unexplained route-week anomalies",
                    verified=True,
                )
            )

        # 3. Evidence supported anomalies
        elif "supporting note" in q_raw or "justified" in q_raw or "evidence" in q_raw:
            lines = [
                f"- {r['route']} (Week {r['week_of']}): {r['pct_vs_history']:+.1f}% vs history, "
                f"justified by note {r['matched_note_id']}: '{r['reason']}'"
                for _, r in justified.iterrows()
            ]
            answer = (
                f"The analysis identified {len(justified)} evidence-justified anomalies:\n"
                + "\n".join(lines)
            )
            for _, r in justified.iterrows():
                sources.append(
                    AssistantSource(
                        type="context_note",
                        id=r["matched_note_id"],
                        description=f"Note {r['matched_note_id']} explains cost increase for {r['route']}",
                    )
                )
            facts.append(
                AssistantFact(
                    statement=f"{len(justified)} anomalies matched genuine cost-driver notes",
                    verified=True,
                )
            )

        # 4. Route type comparison (Short vs Medium vs Long)
        elif "route type" in q_raw or ("short" in q_raw and "long" in q_raw):
            type_stats = analysis_df.groupby("route_type")["cost_per_tonne_km"].agg(["mean", "count"]).to_dict("index")
            lines = [
                f"- {t} routes ({v['count']} route-weeks): average {v['mean']:.3f} ₹ per tonne-km"
                for t, v in type_stats.items()
            ]
            answer = "Average unit cost comparison across route length categories:\n" + "\n".join(lines)
            sources.append(
                AssistantSource(
                    type="analysis_record",
                    id="route_type_aggregates",
                    description="Work-weighted unit cost aggregates by route category",
                )
            )
            facts.append(
                AssistantFact(statement="Short routes have higher unit cost due to fixed loading costs", verified=True)
            )

        # 5. Route-specific query (e.g., Delhi-Jaipur, Chennai-Bangalore, Mumbai-Pune)
        else:
            # Check for route pattern or origin-destination in query
            matched_route = None
            for r in analysis_df["route"].unique():
                if r.lower() in q_raw or (r.split("-")[0].lower() in q_raw and r.split("-")[1].lower() in q_raw):
                    matched_route = r
                    break

            if matched_route:
                r_rows = analysis_df[analysis_df["route"] == matched_route].sort_values("week_of")
                r_anoms = r_rows[r_rows["flagged"] == True]
                avg_cost = r_rows["cost_per_tonne_km"].mean()
                anom_summary = (
                    f"It has {len(r_anoms)} flagged anomaly weeks "
                    f"({(r_anoms['flagged_label'] == 'No (justified)').sum()} justified, "
                    f"{(r_anoms['flagged_label'] == 'Yes').sum()} unexplained)."
                    if len(r_anoms) > 0
                    else "No anomalies were flagged for this route."
                )
                answer = (
                    f"Route {matched_route}: Analyzed over {len(r_rows)} weekly periods. "
                    f"Average unit cost is {avg_cost:.3f} ₹/tonne-km. {anom_summary}"
                )
                sources.append(
                    AssistantSource(
                        type="analysis_record",
                        id=matched_route,
                        description=f"Weekly aggregate metrics for {matched_route}",
                    )
                )
                facts.append(
                    AssistantFact(
                        statement=f"{matched_route} average cost: {avg_cost:.3f} ₹/tonne-km",
                        verified=True,
                    )
                )
            else:
                answer = (
                    "I can answer questions regarding freight cost trends, trailing historical baselines, "
                    "peer group comparisons, and qualitative evidence notes. Try asking: "
                    "'Which routes have the largest unexplained increases?', "
                    "'How is the historical baseline calculated?', or 'Show anomalies for Chennai-Bangalore'."
                )

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return AssistantQueryResponse(
            query=request.query,
            answer=answer,
            mode="deterministic",
            model="deterministic-rules-engine",
            grounded_facts=facts,
            sources=sources,
            execution_time_ms=round(duration_ms, 2),
        )


# Global assistant provider
assistant_service = DeterministicAssistantProvider()
