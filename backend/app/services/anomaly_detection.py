"""Deterministic anomaly detection and evidence-validation engine.

Flags unusual freight cost increases against historical and peer baselines
and matches qualitative context notes under strict anti-hallucination guardrails.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.app.core.config import settings
from backend.app.schemas.analysis import ContextNote, OutputContractRow, RouteWeekAnalysis


class AnomalyDetector:
    """Configurable, deterministic anomaly detection engine."""

    def __init__(
        self,
        threshold_pct: Optional[float] = None,
        note_window_days: Optional[int] = None,
    ):
        self.threshold_pct: float = (
            threshold_pct
            if threshold_pct is not None
            else settings.DEFAULT_ANOMALY_THRESHOLD_PCT
        )
        self.note_window_days: int = (
            note_window_days
            if note_window_days is not None
            else settings.NOTE_DATE_WINDOW_DAYS
        )

    def find_relevant_notes(
        self, route: str, week_of_str: str, notes: list[ContextNote]
    ) -> Tuple[Optional[ContextNote], Optional[ContextNote]]:
        """Search context notes for route and date applicability.

        Returns:
            Tuple of (justifying_note, closest_non_justifying_note)
            - justifying_note: Genuine cost-increasing event within the applicable time window.
            - closest_non_justifying_note: Note that applies geographically or temporally but
              explicitly reports stable conditions or unaffected costs.
        """
        route_clean = route.strip().lower()
        week_dt = datetime.strptime(week_of_str, "%Y-%m-%d").date()

        # Check justifying notes first
        justifying_candidates = []
        non_justifying_candidates = []

        for n in notes:
            scope = n.applies_to.strip().lower()
            scope_matches = (scope == route_clean) or (scope == "all routes")
            if not scope_matches:
                continue

            # Temporal distance
            days_diff = (week_dt - n.date).days
            # Active window: note event occurred up to window_days before the week, or within 7 days
            if -7 <= days_diff <= self.note_window_days:
                if n.is_cost_driver:
                    justifying_candidates.append((abs(days_diff), n))
                else:
                    non_justifying_candidates.append((abs(days_diff), n))

        justifying_candidates.sort(key=lambda x: x[0])
        non_justifying_candidates.sort(key=lambda x: x[0])

        justifying_note = justifying_candidates[0][1] if justifying_candidates else None
        closest_non_justifying = (
            non_justifying_candidates[0][1] if non_justifying_candidates else None
        )

        return justifying_note, closest_non_justifying

    def detect_anomalies(
        self, analysis_df: pd.DataFrame, notes: list[ContextNote]
    ) -> Tuple[pd.DataFrame, list[RouteWeekAnalysis]]:
        """Run deterministic anomaly classification over the baseline analysis DataFrame.

        Rules:
            1. Flagged if pct_vs_history >= threshold OR pct_vs_peers >= threshold.
            2. If flagged and a genuine cost-driver note matches:
               - flagged_label: 'No (justified)'
               - matched_note_id: Note ID
               - reason: Grounded citation of the note and its context.
            3. If flagged and no genuine cost-driver note matches:
               - flagged_label: 'Yes'
               - matched_note_id: '' (strictly blank)
               - reason: Explicit statement that cost increase is unexplained.
            4. If not flagged:
               - flagged_label: 'No'
               - matched_note_id: ''
               - reason: Within normal baseline expectations.
        """
        records: list[RouteWeekAnalysis] = []
        df = analysis_df.copy()

        for _, row in df.iterrows():
            route = str(row["route"])
            origin = str(row.get("origin", route.split("-")[0]))
            dest = str(row.get("destination", route.split("-")[1]))
            rtype = str(row["route_type"])
            week_str = str(row["week_of"])
            cost = float(row["cost_per_tonne_km"])

            v_hist = row.get("vs_own_history")
            v_hist = float(v_hist) if pd.notnull(v_hist) else None
            p_hist = row.get("pct_vs_history")
            p_hist = float(p_hist) if pd.notnull(p_hist) else None

            v_peer = row.get("vs_similar_routes")
            v_peer = float(v_peer) if pd.notnull(v_peer) else None
            p_peer = row.get("pct_vs_peers")
            p_peer = float(p_peer) if pd.notnull(p_peer) else None

            # Anomaly trigger: exceeds either available baseline by threshold
            hist_exceeded = p_hist is not None and p_hist >= self.threshold_pct
            peer_exceeded = p_peer is not None and p_peer >= self.threshold_pct
            is_anomaly = bool(hist_exceeded or peer_exceeded)

            justifying_note, non_justifying_note = self.find_relevant_notes(
                route, week_str, notes
            )

            if is_anomaly:
                if justifying_note is not None:
                    flagged_label = "No (justified)"
                    matched_note_id = justifying_note.note_id
                    reason = (
                        f"Matches note {justifying_note.note_id} dated {justifying_note.date}: "
                        f"{justifying_note.note}"
                    )
                else:
                    flagged_label = "Yes"
                    matched_note_id = ""
                    if non_justifying_note is not None:
                        reason = (
                            f"The closest note ({non_justifying_note.note_id}, {non_justifying_note.date}) "
                            f"mentions: '{non_justifying_note.note}' -- it does not describe a reason for a cost rise "
                            f"on this route. No genuine justification found; flagged for review."
                        )
                    else:
                        reason = (
                            "No matching note found for this route or date range. "
                            "Cost rise looks unexplained and worth a human review."
                        )
            else:
                flagged_label = "No"
                matched_note_id = ""
                reason = "Cost per tonne-km is within normal operating ranges relative to historical and peer baselines."

            rec = RouteWeekAnalysis(
                route=route,
                origin=origin,
                destination=dest,
                route_type=rtype,
                week_of=week_str,
                cost_per_tonne_km=cost,
                vs_own_history=v_hist,
                vs_similar_routes=v_peer,
                pct_vs_history=p_hist,
                pct_vs_peers=p_peer,
                history_count=int(row.get("history_count", 0)),
                peer_count=int(row.get("peer_count", 0)),
                is_rising=bool(p_hist is not None and p_hist > 0),
                flagged=is_anomaly,
                flagged_label=flagged_label,
                matched_note_id=matched_note_id,
                reason=reason,
            )
            records.append(rec)

        res_df = pd.DataFrame([r.model_dump() for r in records])
        return res_df, records

    def format_output_contract(
        self, analyses: list[RouteWeekAnalysis]
    ) -> pd.DataFrame:
        """Format analysis results to match the exact eight-column case-study contract.

        Columns:
            route, week_of, cost_per_tonne_km, vs_own_history, vs_similar_routes,
            flagged, matched_note_id, reason
        """
        rows = []
        for r in analyses:
            # Format vs_own_history
            if r.pct_vs_history is not None:
                hist_str = f"{r.pct_vs_history:+.1f}% vs this route's past average"
            else:
                hist_str = "Baseline unavailable"

            # Format vs_similar_routes
            if r.pct_vs_peers is not None:
                peer_str = f"{r.pct_vs_peers:+.1f}% vs similar-length routes this week"
            else:
                peer_str = "Peer baseline unavailable"

            rows.append(
                {
                    "route": r.route,
                    "week_of": r.week_of,
                    "cost_per_tonne_km": round(r.cost_per_tonne_km, 2),
                    "vs_own_history": hist_str,
                    "vs_similar_routes": peer_str,
                    "flagged": r.flagged_label,
                    "matched_note_id": r.matched_note_id,
                    "reason": r.reason,
                }
            )

        contract_df = pd.DataFrame(rows, columns=settings.OUTPUT_COLUMNS)
        return contract_df

    def export_csv(
        self, contract_df: pd.DataFrame, output_path: Optional[Path | str] = None
    ) -> Path:
        """Export contract DataFrame to CSV with strict RFC-4180 quoting.

        Prevents parsing errors by quoting any fields containing commas.
        """
        dest = Path(output_path or settings.OUTPUT_CSV_FILE).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        contract_df.to_csv(dest, index=False, quoting=csv.QUOTE_MINIMAL, encoding="utf-8")
        return dest
