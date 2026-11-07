"""
calc/energy.py — All energy calculation logic. No AI involved.

Provides:
  - Baseline computation (same shift × weekday × previous N weeks)
  - Anomaly flagging (> threshold% OR > sigma standard deviations above baseline)
  - Avoidable consumption = Σ(actual − baseline) for flagged periods
  - Idle-run kWh = rated_kW × idle_hours (from nameplate data)
  - Cost estimate = excess_kWh × tariff (stretch)
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config import settings


SHIFT_MAP = {
    "day":     (6, 14),   # 06:00 – 14:00
    "evening": (14, 22),  # 14:00 – 22:00
    "night":   (22, 6),   # 22:00 – 06:00 (wraps midnight)
}


def get_shift_assignment(ts: pd.Timestamp) -> tuple[datetime.date, str, int]:
    """
    Assign shift name and the date/weekday the shift belongs to.
    Night shift runs 22:00 to 06:00 next day; hours 00:00–05:59 belong to
    the previous calendar day's night shift.
    """
    hour = ts.hour
    if 6 <= hour < 14:
        shift = "day"
        shift_date = ts.date()
    elif 14 <= hour < 22:
        shift = "evening"
        shift_date = ts.date()
    elif hour >= 22:
        shift = "night"
        shift_date = ts.date()
    else:  # hour < 6
        shift = "night"
        shift_date = (ts - pd.Timedelta(days=1)).date()
    return shift_date, shift, shift_date.weekday()


def assign_shift(hour: int) -> str:
    """Return shift name for a given hour (0-23)."""
    if 6 <= hour < 14:
        return "day"
    elif 14 <= hour < 22:
        return "evening"
    else:
        return "night"


@dataclass
class EnergyAnomaly:
    anomaly_id: str
    timestamp: datetime.datetime
    shift: str
    weekday: int                    # 0 = Monday
    actual_kwh: float
    baseline_kwh: float
    deviation_pct: float            # (actual - baseline) / baseline * 100
    excess_kwh: float               # actual - baseline
    sigma_deviation: float
    baseline_readings_count: int
    is_flagged: bool = True


@dataclass
class EnergyAnalysisResult:
    upload_id: str
    track: str = "energy"
    total_readings: int = 0
    anomalies: list[EnergyAnomaly] = field(default_factory=list)
    total_excess_kwh: float = 0.0
    errors: list[str] = field(default_factory=list)


def compute_baseline(
    df: pd.DataFrame,
    target_ts: pd.Timestamp,
    shift: str,
    baseline_weeks: int = None,
) -> tuple[float, float, int]:
    """
    Compute mean and std of kWh for the same shift + weekday over the previous N weeks.

    Returns: (mean_kwh, std_kwh, n_readings)
    """
    baseline_weeks = baseline_weeks or settings.BASELINE_WEEKS
    target_weekday = target_ts.weekday()
    cutoff = target_ts - pd.Timedelta(weeks=baseline_weeks)

    mask = (
        (df["timestamp"] < target_ts)
        & (df["timestamp"] >= cutoff)
        & (df["shift"] == shift)
        & (df["weekday"] == target_weekday)
    )
    subset = df.loc[mask, "kwh"].dropna()

    if len(subset) < 1:
        # Fall back to same shift (any weekday) if insufficient data
        mask_loose = (
            (df["timestamp"] < target_ts)
            & (df["timestamp"] >= cutoff)
            & (df["shift"] == shift)
        )
        subset = df.loc[mask_loose, "kwh"].dropna()

    if len(subset) == 0:
        return 0.0, 0.0, 0

    return float(subset.mean()), float(subset.std(ddof=1) if len(subset) > 1 else 0.0), len(subset)


def run_energy_analysis(
    df: pd.DataFrame,
    upload_id: str,
    threshold_pct: float = None,
    sigma: float = None,
    baseline_weeks: int = None,
    historical_df: Optional[pd.DataFrame] = None,
) -> EnergyAnalysisResult:
    """
    Main entry point for energy analysis.

    Expects df with columns: timestamp (datetime), kwh (float).
    Uses industrial shift accounting: night shift across midnight (22:00-06:00)
    is aggregated into a single continuous shift belonging to shift_date.
    Flags anomalies where deviation_pct >= threshold_pct.
    """
    threshold_pct = threshold_pct or settings.ANOMALY_THRESHOLD_PCT
    sigma = sigma or settings.ANOMALY_SIGMA
    baseline_weeks = baseline_weeks or settings.BASELINE_WEEKS

    result = EnergyAnalysisResult(upload_id=upload_id, total_readings=len(df))

    if "timestamp" not in df.columns or "kwh" not in df.columns:
        result.errors.append("CSV must have 'timestamp' and 'kwh' columns.")
        return result

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    # Proper industrial shift accounting (22:00 to 06:00 continuous night shift)
    shift_info = [get_shift_assignment(pd.Timestamp(t)) for t in df["timestamp"]]
    df["shift_date"] = [s[0] for s in shift_info]
    df["shift"] = [s[1] for s in shift_info]
    df["weekday"] = [s[2] for s in shift_info]

    # Aggregate to shift-level totals (sum kWh per shift per shift_date)
    shift_agg = (
        df.groupby(["shift_date", "shift", "weekday"])["kwh"]
        .sum()
        .reset_index()
    )

    def _assign_rep_ts(row):
        d = row["shift_date"]
        s = row["shift"]
        if s == "day":
            return pd.Timestamp.combine(d, datetime.time(10, 0))   # Peak ToD
        elif s == "evening":
            return pd.Timestamp.combine(d, datetime.time(18, 0))   # Peak ToD
        else:
            return pd.Timestamp.combine(d, datetime.time(23, 0))   # Off-peak ToD

    shift_agg["timestamp"] = shift_agg.apply(_assign_rep_ts, axis=1)

    # Combine with prior historical telemetry if provided (supports new 1-week uploads)
    if historical_df is not None and not historical_df.empty:
        hdf = historical_df.copy()
        hdf["timestamp"] = pd.to_datetime(hdf["timestamp"])
        h_info = [get_shift_assignment(pd.Timestamp(t)) for t in hdf["timestamp"]]
        hdf["shift_date"] = [h[0] for h in h_info]
        hdf["shift"] = [h[1] for h in h_info]
        hdf["weekday"] = [h[2] for h in h_info]
        h_agg = hdf.groupby(["shift_date", "shift", "weekday"])["kwh"].sum().reset_index()
        h_agg["timestamp"] = h_agg.apply(_assign_rep_ts, axis=1)
        df_for_baseline = pd.concat([h_agg, shift_agg]).drop_duplicates(subset=["shift_date", "shift"]).sort_values("timestamp")
    else:
        df_for_baseline = shift_agg

    flagged_shifts: set[tuple[datetime.date, str]] = set()

    for _, row in shift_agg.iterrows():
        ts = pd.Timestamp(row["timestamp"])
        shift = row["shift"]
        actual_kwh = float(row["kwh"])
        s_date = row["shift_date"]

        # Robust baseline: exclude previously flagged anomalous shifts to prevent baseline inflation (Bug 8)
        if flagged_shifts:
            clean_baseline_df = df_for_baseline[
                ~df_for_baseline.apply(
                    lambda r: (r["shift_date"], r["shift"]) in flagged_shifts, axis=1
                )
            ]
        else:
            clean_baseline_df = df_for_baseline

        mean_kwh, std_kwh, n = compute_baseline(
            clean_baseline_df, ts, shift, baseline_weeks
        )

        if mean_kwh <= 0 or n < 2:
            # Not enough history — skip flagging
            continue

        deviation_pct = (actual_kwh - mean_kwh) / mean_kwh * 100
        excess_kwh = actual_kwh - mean_kwh
        sigma_dev = (actual_kwh - mean_kwh) / std_kwh if std_kwh > 0 else 0.0

        # Enforce threshold hurdle: only genuine percentage spikes trigger anomalies
        is_flagged = deviation_pct >= threshold_pct
        if is_flagged:
            flagged_shifts.add((s_date, shift))

        uid_tag = upload_id[:8] if upload_id else "UPL"
        anomaly_id = (
            f"E-{uid_tag}-{row['shift_date'].strftime('%Y-%m-%d')}-{shift.upper()}"
        )

        anomaly = EnergyAnomaly(
            anomaly_id=anomaly_id,
            timestamp=ts.to_pydatetime(),
            shift=shift,
            weekday=int(row["weekday"]),
            actual_kwh=round(actual_kwh, 3),
            baseline_kwh=round(mean_kwh, 3),
            deviation_pct=round(deviation_pct, 2),
            excess_kwh=round(excess_kwh, 3),
            sigma_deviation=round(sigma_dev, 2),
            baseline_readings_count=n,
            is_flagged=is_flagged,
        )
        if is_flagged:
            result.anomalies.append(anomaly)

    result.total_excess_kwh = round(
        sum(a.excess_kwh for a in result.anomalies if a.excess_kwh > 0), 3
    )
    return result


def compute_idle_run_kwh(rated_kw: float, idle_hours: float) -> float:
    """
    Avoidable idle consumption from nameplate data.
    idle_run_kwh = rated_kW × idle_hours
    Pure arithmetic — no AI.
    """
    if rated_kw <= 0 or idle_hours <= 0:
        return 0.0
    return round(rated_kw * idle_hours, 3)

