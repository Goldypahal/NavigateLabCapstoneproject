"""
verify/postfix.py — Post-fix verification logic (stretch feature).

After the manager marks an action as done, a new CSV is uploaded for the
"post-fix window". This module compares the post-fix period against the
same baseline to compute % change and ₹ saved.

All calculations are in code — no AI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from calc.energy import compute_baseline, assign_shift, get_shift_assignment
from calc.cost import estimate_energy_cost, estimate_water_cost
from config import settings


@dataclass
class VerificationResult:
    action_id: int
    track: str
    baseline_avg: float             # kWh or kL/day
    postfix_avg: float              # post-fix period average
    pct_change: float               # (postfix - baseline) / baseline * 100
    value_saved: float              # kWh or kL
    cost_saved: float               # ₹
    verdict: str                    # 'improved' | 'no_change' | 'worsened'
    note: str


def verify_energy_fix(
    action_id: int,
    baseline_df: pd.DataFrame,
    postfix_df: pd.DataFrame,
    shift: str,
    baseline_weeks: int = None,
) -> VerificationResult:
    """
    Compare post-fix energy vs. baseline for the same shift.
    Both baseline and post-fix are aggregated to shift totals for fair comparison.
    """
    baseline_weeks = baseline_weeks or settings.BASELINE_WEEKS

    baseline_df = baseline_df.copy()
    postfix_df = postfix_df.copy()

    # Aggregate baseline to shift totals
    b_info = [get_shift_assignment(pd.Timestamp(t)) for t in baseline_df["timestamp"]]
    baseline_df["shift_date"] = [s[0] for s in b_info]
    baseline_df["shift"] = [s[1] for s in b_info]
    baseline_df["weekday"] = [s[2] for s in b_info]
    b_agg = baseline_df.groupby(["shift_date", "shift", "weekday"])["kwh"].sum().reset_index()
    b_agg["timestamp"] = pd.to_datetime(b_agg["shift_date"])

    # Aggregate postfix to shift totals
    p_info = [get_shift_assignment(pd.Timestamp(t)) for t in postfix_df["timestamp"]]
    postfix_df["shift_date"] = [s[0] for s in p_info]
    postfix_df["shift"] = [s[1] for s in p_info]
    postfix_df["weekday"] = [s[2] for s in p_info]
    p_agg = postfix_df.groupby(["shift_date", "shift", "weekday"])["kwh"].sum().reset_index()
    p_agg["timestamp"] = pd.to_datetime(p_agg["shift_date"])

    shift_norm = shift.strip().lower()
    if shift_norm == "morning":
        shift_norm = "day"

    postfix_shift = p_agg[p_agg["shift"] == shift_norm]
    if postfix_shift.empty:
        return VerificationResult(
            action_id=action_id,
            track="energy",
            baseline_avg=0,
            postfix_avg=0,
            pct_change=0,
            value_saved=0,
            cost_saved=0,
            verdict="no_change",
            note=f"No post-fix readings found for shift '{shift}'.",
        )

    ref_ts = pd.Timestamp(postfix_df["timestamp"].max())
    mean_kwh, _, _ = compute_baseline(b_agg, ref_ts, shift_norm, baseline_weeks)

    postfix_avg = float(postfix_shift["kwh"].mean())
    value_saved = round(mean_kwh - postfix_avg, 3)
    pct_change = round((postfix_avg - mean_kwh) / mean_kwh * 100, 2) if mean_kwh > 0 else 0.0
    cost_est = estimate_energy_cost(max(value_saved, 0))

    verdict = "improved" if pct_change < -5 else ("worsened" if pct_change > 5 else "no_change")

    return VerificationResult(
        action_id=action_id,
        track="energy",
        baseline_avg=round(mean_kwh, 3),
        postfix_avg=round(postfix_avg, 3),
        pct_change=pct_change,
        value_saved=max(value_saved, 0.0),
        cost_saved=cost_est.total_cost if value_saved > 0 else 0.0,
        verdict=verdict,
        note=f"Compared {len(postfix_shift)} post-fix {shift} shifts vs {baseline_weeks}-week baseline.",
    )


def verify_water_fix(
    action_id: int,
    baseline_df: pd.DataFrame,
    postfix_df: pd.DataFrame,
) -> VerificationResult:
    """Compare post-fix unaccounted water vs. baseline."""
    for df in (baseline_df, postfix_df):
        df["unaccounted_kl"] = df["intake_kl"] - df["process_kl"] - df["discharge_kl"]

    baseline_avg = float(baseline_df["unaccounted_kl"].mean())
    postfix_avg = float(postfix_df["unaccounted_kl"].mean())
    value_saved = round(baseline_avg - postfix_avg, 3)
    pct_change = round((postfix_avg - baseline_avg) / max(abs(baseline_avg), 0.01) * 100, 2)
    cost_est = estimate_water_cost(max(value_saved, 0))

    verdict = "improved" if pct_change < -10 else ("worsened" if pct_change > 10 else "no_change")

    return VerificationResult(
        action_id=action_id,
        track="water",
        baseline_avg=round(baseline_avg, 3),
        postfix_avg=round(postfix_avg, 3),
        pct_change=pct_change,
        value_saved=max(value_saved, 0.0),
        cost_saved=cost_est.total_cost if value_saved > 0 else 0.0,
        verdict=verdict,
        note=f"Compared {len(postfix_df)} post-fix days vs {len(baseline_df)} baseline days.",
    )

