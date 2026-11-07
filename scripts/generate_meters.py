"""
scripts/generate_meters.py — Synthetic meter data generator with planted anomalies.

Usage:
    python generate_meters.py --seed 42 --weeks 8 --out-dir data/

Outputs:
    energy_readings.csv       — 15-min kWh for 3 shifts × N weeks
    water_readings.csv        — daily intake/process/discharge kL
    planted_anomalies.json    — answer key with exact anomaly IDs and expected values

Planted anomalies (energy):
    1. Night shift +30% excess — Tuesday nights, weeks 5-6
       Cause: compressor running during break, air-line leak
    2. Weekend idle run — Sunday day shift, week 7
       Cause: machine left on after production ended
    3. Gradual drift — evening shift, weeks 6-8 (creeping +15%)
       Cause: aging motor drawing more current

Planted anomalies (water):
    1. +18 kL/day unaccounted — days 42-56
       Cause: dripping valve at cooling tower
    2. Metering conflict — day 30 (discharge > intake, impossible)
       Cause: meter misread (conflict case)
    3. Gradual leak drift — days 20-40 (slowly increasing unaccounted)
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
import datetime

import numpy as np
import pandas as pd

SHIFTS = {
    "day":     (6, 14),
    "evening": (14, 22),
    "night":   (22, 30),   # 22 to 06 next day, represented as +24h then mod 24
}

# Base kWh per 15-min interval per shift (realistic factory values)
BASE_KWH = {
    "day":     18.5,    # 74 kWh/h average — heavy production
    "evening": 15.2,    # lighter load
    "night":   10.8,    # minimal — only compressors and lights
}

# Base water values (kL/day)
BASE_WATER = {
    "intake_kl":    85.0,
    "process_kl":   60.0,
    "discharge_kl": 22.0,
    # unaccounted baseline ≈ 3 kL/day (normal losses)
}


def get_shift_assignment(ts: datetime.datetime) -> tuple[datetime.date, str, int]:
    """
    Industrial shift accounting: night shift runs 22:00 to 06:00 next day.
    Hours 00:00–05:59 belong to the previous calendar day's night shift.
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
        shift_date = (ts - datetime.timedelta(days=1)).date()
    return shift_date, shift, shift_date.weekday()


def generate_energy_csv(
    start_date: datetime.date,
    n_weeks: int,
    seed: int,
) -> tuple[pd.DataFrame, list[dict]]:
    rng = np.random.default_rng(seed)
    planted = []
    rows = []

    total_days = n_weeks * 7
    end_date = start_date + datetime.timedelta(days=total_days)
    current = datetime.datetime.combine(start_date, datetime.time(0, 0))

    # Pre-compute anomaly windows
    # Anomaly 1: Tuesday night shift, weeks 5-6 (days 28-41)
    anom1_start = start_date + datetime.timedelta(weeks=4)
    anom1_end   = start_date + datetime.timedelta(weeks=6)

    # Anomaly 2: Sunday day shift, week 7 (day 42-48)
    anom2_start = start_date + datetime.timedelta(weeks=6)
    anom2_end   = start_date + datetime.timedelta(weeks=7)

    # Anomaly 3: Evening shift gradual drift, weeks 6-8
    anom3_start = start_date + datetime.timedelta(weeks=5)
    anom3_end   = end_date

    while current.date() < end_date:
        hour = current.hour
        minute = current.minute

        # Determine shift using industrial shift assignment
        shift_date, shift, shift_weekday = get_shift_assignment(current)

        base = BASE_KWH[shift]
        noise = float(rng.normal(0, base * 0.05))  # 5% noise
        kwh = max(0.1, base + noise)

        # Apply anomalies strictly to the unified shift window:
        # Anomaly 1: Tuesday nights +30% (entire 22:00 Tue to 06:00 Wed shift)
        if anom1_start <= shift_date < anom1_end and shift_weekday == 1 and shift == "night":
            kwh *= 1.30 + float(rng.uniform(0, 0.05))

        # Anomaly 2: Sunday day idle run (+60% — machine left on)
        elif anom2_start <= shift_date < anom2_end and shift_weekday == 6 and shift == "day":
            kwh *= 1.60 + float(rng.uniform(0, 0.1))

        # Anomaly 3: Gradual evening drift
        elif anom3_start <= shift_date < anom3_end and shift == "evening":
            days_into = (shift_date - anom3_start).days
            drift = 1.0 + 0.005 * days_into   # 0.5% per day, up to ~15%
            kwh *= min(drift, 1.18)

        rows.append({
            "timestamp": current.strftime("%Y-%m-%d %H:%M:%S"),
            "kwh": round(kwh, 4),
            "shift": shift,
            "equipment": "Line-1" if shift == "day" else ("Line-2" if shift == "evening" else "Compressor-AX200"),
        })
        current += datetime.timedelta(minutes=15)

    df = pd.DataFrame(rows)

    # Build planted anomalies answer key
    planted = [
        {
            "anomaly_id_prefix": "E-",
            "type": "energy",
            "description": "Night shift compressor overrun + air-line leak",
            "affected_dates": [
                str(anom1_start + datetime.timedelta(days=i))
                for i in range((anom1_end - anom1_start).days)
                if (anom1_start + datetime.timedelta(days=i)).weekday() == 1
            ],
            "shift": "night",
            "expected_deviation_pct": 30,
            "equipment": "Compressor-AX200",
            "note": "Tuesday nights in weeks 5-6"
        },
        {
            "anomaly_id_prefix": "E-",
            "type": "energy",
            "description": "Weekend idle machine run",
            "affected_dates": [
                str(anom2_start + datetime.timedelta(days=i))
                for i in range((anom2_end - anom2_start).days)
                if (anom2_start + datetime.timedelta(days=i)).weekday() == 6
            ],
            "shift": "day",
            "expected_deviation_pct": 60,
            "equipment": "Line-1",
            "note": "Sunday day shift in week 7 — machine not shut down"
        },
        {
            "anomaly_id_prefix": "E-",
            "type": "energy",
            "description": "Gradual motor aging drift on evening shift",
            "affected_dates": "weeks 6-8 evening",
            "shift": "evening",
            "expected_deviation_pct": "5-15 (gradual)",
            "equipment": "Line-2",
            "note": "Creeping increase — aging motor"
        },
    ]

    return df, planted


def generate_water_csv(
    start_date: datetime.date,
    n_weeks: int,
    seed: int,
) -> tuple[pd.DataFrame, list[dict]]:
    rng = np.random.default_rng(seed + 100)
    rows = []

    total_days = n_weeks * 7

    # Anomaly windows
    # Anomaly 1: +18 kL/day unaccounted, days 42-56
    anom1_start_day = 41
    anom1_end_day   = 56

    # Anomaly 2: Metering conflict day 30
    conflict_day = 29

    # Anomaly 3: Gradual leak drift days 20-40
    anom3_start_day = 19
    anom3_end_day   = 41

    planted = []

    for day_idx in range(total_days):
        date = start_date + datetime.timedelta(days=day_idx)
        intake   = BASE_WATER["intake_kl"]   + float(rng.normal(0, 2.0))
        process  = BASE_WATER["process_kl"]  + float(rng.normal(0, 1.5))
        discharge = BASE_WATER["discharge_kl"] + float(rng.normal(0, 1.0))

        # Anomaly 2: metering conflict
        if day_idx == conflict_day:
            discharge = intake + 10.0   # impossible: more out than in

        # Anomaly 3: gradual leak drift (+0.5 kL/day)
        elif anom3_start_day <= day_idx < anom3_end_day:
            days_in = day_idx - anom3_start_day
            intake += 0.5 * days_in   # unaccounted grows

        # Anomaly 1: large unaccounted loss
        elif anom1_start_day <= day_idx < anom1_end_day:
            intake += 18.0 + float(rng.uniform(-1, 1))

        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "intake_kl":    round(max(0, intake), 3),
            "process_kl":   round(max(0, process), 3),
            "discharge_kl": round(max(0, discharge), 3),
            "notes": "",
        })

    df = pd.DataFrame(rows)

    planted = [
        {
            "type": "water",
            "description": "Cooling tower dripping valve — +18 kL/day unaccounted",
            "affected_dates": f"days {anom1_start_day+1}–{anom1_end_day}",
            "expected_unaccounted_kl_per_day": 18,
            "note": "14-day event"
        },
        {
            "type": "water",
            "description": "Metering conflict — discharge > intake (physically impossible)",
            "affected_dates": f"day {conflict_day+1}",
            "expected_unaccounted_kl_per_day": "negative (conflict)",
            "note": "Should be flagged as W-CONFLICT"
        },
        {
            "type": "water",
            "description": "Gradual unaccounted water drift (slow leak)",
            "affected_dates": f"days {anom3_start_day+1}–{anom3_end_day}",
            "expected_unaccounted_kl_per_day": "0.5 × days_in (gradual)",
            "note": "Increasing pattern — may cross threshold mid-window"
        },
    ]

    return df, planted


def main():
    parser = argparse.ArgumentParser(description="ResourceLens synthetic meter generator")
    parser.add_argument("--seed",    type=int,   default=42,     help="RNG seed for reproducibility")
    parser.add_argument("--weeks",   type=int,   default=8,      help="Number of weeks to generate")
    parser.add_argument("--out-dir", type=str,   default="data", help="Output directory")
    parser.add_argument(
        "--start-date",
        type=str,
        default=str(datetime.date.today() - datetime.timedelta(weeks=8)),
        help="Start date (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_date = datetime.date.fromisoformat(args.start_date)

    print(f"Generating {args.weeks} weeks of data starting {start_date} (seed={args.seed})…")

    energy_df, energy_planted = generate_energy_csv(start_date, args.weeks, args.seed)
    water_df, water_planted   = generate_water_csv(start_date, args.weeks, args.seed)

    energy_path = out_dir / "energy_readings.csv"
    water_path  = out_dir / "water_readings.csv"
    key_path    = out_dir / "planted_anomalies.json"

    energy_df.to_csv(energy_path, index=False)
    water_df.to_csv(water_path, index=False)

    answer_key = {
        "seed": args.seed,
        "weeks": args.weeks,
        "start_date": str(start_date),
        "energy_anomalies": energy_planted,
        "water_anomalies": water_planted,
    }
    key_path.write_text(json.dumps(answer_key, indent=2))

    print(f"  Energy CSV  : {energy_path}  ({len(energy_df)} rows)")
    print(f"  Water CSV   : {water_path}  ({len(water_df)} rows)")
    print(f"  Answer key  : {key_path}")
    print("\nPlanted anomalies:")
    for a in energy_planted + water_planted:
        print(f"  [{a['type']}] {a['description']}")


if __name__ == "__main__":
    main()

