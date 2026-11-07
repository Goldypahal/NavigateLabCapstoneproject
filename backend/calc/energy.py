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
) -> EnergyAnalysisResult:
    """
    Main entry point for energy analysis.

    Expects df with columns: timestamp (datetime), kwh (float).
    Adds shift and weekday columns in-place.
    Flags anomalies where:
      deviation > threshold_pct  AND/OR  deviation > sigma * std
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
    df["shift"] = df["timestamp"].dt.hour.apply(assign_shift)
    df["weekday"] = df["timestamp"].dt.weekday

    # Aggregate to shift-level totals (sum kWh per shift per day)
    df["shift_date"] = df["timestamp"].dt.date
    shift_agg = (
        df.groupby(["shift_date", "shift", "weekday"])["kwh"]
        .sum()
        .reset_index()
    )
    shift_agg["timestamp"] = pd.to_datetime(shift_agg["shift_date"])

    # Baseline lookups must compare shift totals to historical shift totals
    df_for_baseline = shift_agg

    for _, row in shift_agg.iterrows():
        ts = pd.Timestamp(row["timestamp"])
        shift = row["shift"]
        actual_kwh = float(row["kwh"])

        mean_kwh, std_kwh, n = compute_baseline(
            df_for_baseline, ts, shift, baseline_weeks
        )

        if mean_kwh <= 0 or n < 2:
            # Not enough history — skip flagging
            continue

        deviation_pct = (actual_kwh - mean_kwh) / mean_kwh * 100
        excess_kwh = actual_kwh - mean_kwh
        sigma_dev = (actual_kwh - mean_kwh) / std_kwh if std_kwh > 0 else 0.0

        # Flag if above threshold% OR above sigma·std
        is_flagged = (
            deviation_pct > threshold_pct
            or (std_kwh > 0 and sigma_dev > sigma)
        )

        anomaly_id = (
            f"E-{ts.strftime('%Y-%m-%d')}-{shift.upper()}"
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

