"""
ingest/csv_validator.py — Validates and parses meter CSV uploads.

Rejects CSVs with:
  - Missing required columns
  - Non-numeric values in numeric columns
  - Duplicate timestamps
  - Negative kWh or kL readings (physical impossibility)
  - Gaps larger than expected interval (warning, not rejection)

Returns a parsed DataFrame or a list of row-level errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import numpy as np


ENERGY_REQUIRED = {"timestamp", "kwh"}
WATER_REQUIRED  = {"date", "intake_kl", "process_kl", "discharge_kl"}
ENERGY_OPTIONAL = {"equipment", "shift", "notes"}
WATER_OPTIONAL  = {"notes", "meter_id"}

MAX_CSV_ROWS = 50_000   # safety limit


@dataclass
class CSVValidationResult:
    track: str
    df: Optional[pd.DataFrame] = None
    is_valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_count: int = 0


def validate_energy_csv(raw: str | bytes) -> CSVValidationResult:
    """Parse and validate an energy meter CSV."""
    result = CSVValidationResult(track="energy")

    try:
        df = pd.read_csv(
            pd.io.common.StringIO(raw.decode() if isinstance(raw, bytes) else raw),
            nrows=MAX_CSV_ROWS,
        )
    except Exception as e:
        result.errors.append(f"Cannot parse CSV: {e}")
        return result

    df.columns = [c.strip().lower() for c in df.columns]

    missing = ENERGY_REQUIRED - set(df.columns)
    if missing:
        result.errors.append(f"Missing required columns: {sorted(missing)}")
        return result

    # Parse timestamp
    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    except Exception as e:
        result.errors.append(f"Cannot parse 'timestamp' column: {e}")
        return result

    # Parse kwh
    df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce")
    bad_kwh = df["kwh"].isna()
    if bad_kwh.any():
        bad_rows = df.index[bad_kwh].tolist()[:5]
        result.errors.append(f"Non-numeric 'kwh' at rows: {bad_rows}")

    # Negative values
    neg_kwh = df["kwh"] < 0
    if neg_kwh.any():
        result.errors.append(f"Negative kWh values found at {neg_kwh.sum()} rows — physically impossible.")

    # Duplicates
    dupes = df.duplicated(subset=["timestamp"])
    if dupes.any():
        result.errors.append(f"Duplicate timestamps found ({dupes.sum()} rows). Remove duplicates before uploading.")

    # Gap detection (warn only)
    df_sorted = df.sort_values("timestamp")
    diffs = df_sorted["timestamp"].diff().dropna()
    expected_interval = diffs.mode()[0] if not diffs.empty else pd.Timedelta(minutes=15)
    large_gaps = diffs[diffs > expected_interval * 3]
    if not large_gaps.empty:
        result.warnings.append(
            f"{len(large_gaps)} time gaps larger than 3× the expected interval "
            f"({expected_interval}). Baseline may be less accurate around these gaps."
        )

    if not result.errors:
        result.df = df.sort_values("timestamp").reset_index(drop=True)
        result.is_valid = True
        result.row_count = len(result.df)

    return result


def validate_water_csv(raw: str | bytes) -> CSVValidationResult:
    """Parse and validate a water balance CSV."""
    result = CSVValidationResult(track="water")

    try:
        df = pd.read_csv(
            pd.io.common.StringIO(raw.decode() if isinstance(raw, bytes) else raw),
            nrows=MAX_CSV_ROWS,
        )
    except Exception as e:
        result.errors.append(f"Cannot parse CSV: {e}")
        return result

    df.columns = [c.strip().lower() for c in df.columns]

    # Allow 'timestamp' as alias for 'date'
    if "timestamp" in df.columns and "date" not in df.columns:
        df.rename(columns={"timestamp": "date"}, inplace=True)

    missing = WATER_REQUIRED - set(df.columns)
    if missing:
        result.errors.append(f"Missing required columns: {sorted(missing)}")
        return result

    # Parse date
    try:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    except Exception as e:
        result.errors.append(f"Cannot parse 'date' column: {e}")
        return result

    # Parse numeric columns
    numeric_cols = ["intake_kl", "process_kl", "discharge_kl"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        bad = df[col].isna()
        if bad.any():
            result.errors.append(f"Non-numeric '{col}' at {bad.sum()} rows.")
        neg = df[col] < 0
        if neg.any():
            result.errors.append(f"Negative '{col}' values at {neg.sum()} rows.")

    # Duplicates
    dupes = df.duplicated(subset=["date"])
    if dupes.any():
        result.errors.append(f"Duplicate dates: {dupes.sum()} rows.")

    if not result.errors:
        result.df = df.sort_values("date").reset_index(drop=True)
        result.is_valid = True
        result.row_count = len(result.df)

    return result

