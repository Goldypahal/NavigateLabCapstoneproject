"""
calc/water.py — All water balance calculation logic. No AI involved.

Water balance equation:
    unaccounted = intake - process_use - discharge

Where:
    intake       = total water drawn into the factory (kL/day)
    process_use  = water consumed in production (kL/day)
    discharge    = water released/treated/disposed (kL/day)
    unaccounted  = suspected leak or metering error

Anomaly: unaccounted > threshold_kl/day for the period.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config import settings


@dataclass
class WaterAnomaly:
    anomaly_id: str
    date: datetime.date
    intake_kl: float
    process_kl: float
    discharge_kl: float
    unaccounted_kl: float           # intake - process - discharge (code)
    baseline_unaccounted_kl: float  # historical average unaccounted
    excess_kl: float                # unaccounted - baseline_unaccounted
    days_above_threshold: int
    total_loss_kl: float            # excess_kl × days_above_threshold (code)
    is_flagged: bool = True
    is_metering_conflict: bool = False   # flagged when values seem contradictory


@dataclass
class WaterAnalysisResult:
    upload_id: str
    track: str = "water"
    total_days: int = 0
    anomalies: list[WaterAnomaly] = field(default_factory=list)
    total_unaccounted_kl: float = 0.0
    errors: list[str] = field(default_factory=list)


def compute_water_balance(row: pd.Series) -> float:
    """
    Water balance for one day.
    unaccounted = intake - process - discharge
    Positive value = unaccounted loss (leak or unmeasured use).
    Negative value = metering discrepancy (more discharged/used than intake — flag as conflict).
    """
    return float(row["intake_kl"] - row["process_kl"] - row["discharge_kl"])


def run_water_analysis(
    df: pd.DataFrame,
    upload_id: str,
    threshold_kl: float = None,
    baseline_weeks: int = None,
    historical_df: Optional[pd.DataFrame] = None,
) -> WaterAnalysisResult:
    """
    Main entry point for water balance analysis.

    Expects df with columns: date (or timestamp), intake_kl, process_kl, discharge_kl.
    Flags anomalies where unaccounted water exceeds baseline by threshold_kl/day.
    """
    threshold_kl = threshold_kl or settings.WATER_UNACCOUNTED_THRESHOLD_KL
    baseline_weeks = baseline_weeks or settings.BASELINE_WEEKS

    result = WaterAnalysisResult(upload_id=upload_id)

    required_cols = {"intake_kl", "process_kl", "discharge_kl"}
    missing = required_cols - set(df.columns)
    if missing:
        result.errors.append(f"CSV missing required water columns: {missing}")
        return result

    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    elif "timestamp" in df.columns:
        df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    else:
        result.errors.append("CSV must have a 'date' or 'timestamp' column.")
        return result

    df = df.sort_values("date").reset_index(drop=True)
    result.total_days = len(df)

    # Compute unaccounted for every row
    df["unaccounted_kl"] = df.apply(compute_water_balance, axis=1)

    # Integrate cross-upload historical readings if provided (Bug 3)
    if historical_df is not None and not historical_df.empty:
        hdf = historical_df.copy()
        if "date" in hdf.columns:
            hdf["date"] = pd.to_datetime(hdf["date"]).dt.date
        elif "timestamp" in hdf.columns:
            hdf["date"] = pd.to_datetime(hdf["timestamp"]).dt.date
        hdf["unaccounted_kl"] = hdf.apply(compute_water_balance, axis=1)
        df_for_baseline = pd.concat([hdf, df]).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    else:
        df_for_baseline = df

    # Robust baseline: estimate normal unaccounted loss from clean/non-outlier days (Bug 4)
    clean_history = df_for_baseline[
        (df_for_baseline["unaccounted_kl"] >= -2.0) & 
        (df_for_baseline["unaccounted_kl"] < 10.0)
    ]
    if not clean_history.empty:
        normal_baseline = float(clean_history["unaccounted_kl"].median())
    else:
        normal_baseline = 4.0

    df["baseline_unaccounted"] = normal_baseline
    df["excess_kl"] = df["unaccounted_kl"] - df["baseline_unaccounted"]

    # Flag days where excess unaccounted water exceeds threshold
    df["is_above"] = df["excess_kl"] >= threshold_kl
    df["is_conflict"] = df["unaccounted_kl"] < -2.0  # more out than in

    # Group consecutive days above threshold into single anomaly events
    df["group"] = (df["is_above"] != df["is_above"].shift()).cumsum()
    flagged_groups = df[df["is_above"]].groupby("group")

    uid_tag = upload_id[:8] if upload_id else "UPL"

    for _, grp in flagged_groups:
        days = len(grp)
        first_date = grp["date"].iloc[0]
        avg_intake = float(grp["intake_kl"].mean())
        avg_process = float(grp["process_kl"].mean())
        avg_discharge = float(grp["discharge_kl"].mean())
        avg_unaccounted = float(grp["unaccounted_kl"].mean())
        baseline_val = float(grp["baseline_unaccounted"].mean())
        excess_kl = avg_unaccounted - max(baseline_val, 0.0)
        total_loss = round(excess_kl * days, 3)

        # Upload-scoped anomaly ID to prevent UNIQUE constraint collisions (Bug 2)
        anomaly_id = f"W-{uid_tag}-{first_date.strftime('%Y-%m-%d')}-D{days}"

        anomaly = WaterAnomaly(
            anomaly_id=anomaly_id,
            date=first_date,
            intake_kl=round(avg_intake, 3),
            process_kl=round(avg_process, 3),
            discharge_kl=round(avg_discharge, 3),
            unaccounted_kl=round(avg_unaccounted, 3),
            baseline_unaccounted_kl=round(baseline_val, 3),
            excess_kl=round(excess_kl, 3),
            days_above_threshold=days,
            total_loss_kl=total_loss,
        )
        result.anomalies.append(anomaly)

    # Also flag metering conflicts
    conflict_rows = df[df["is_conflict"]]
    for _, row in conflict_rows.iterrows():
        anomaly_id = f"W-{uid_tag}-CONFLICT-{row['date'].strftime('%Y-%m-%d')}"
        anomaly = WaterAnomaly(
            anomaly_id=anomaly_id,
            date=row["date"],
            intake_kl=round(float(row["intake_kl"]), 3),
            process_kl=round(float(row["process_kl"]), 3),
            discharge_kl=round(float(row["discharge_kl"]), 3),
            unaccounted_kl=round(float(row["unaccounted_kl"]), 3),
            baseline_unaccounted_kl=0.0,
            excess_kl=0.0,
            days_above_threshold=1,
            total_loss_kl=0.0,
            is_flagged=True,
            is_metering_conflict=True,
        )
        result.anomalies.append(anomaly)

    result.total_unaccounted_kl = round(
        sum(a.total_loss_kl for a in result.anomalies if not a.is_metering_conflict), 3
    )
    return result

