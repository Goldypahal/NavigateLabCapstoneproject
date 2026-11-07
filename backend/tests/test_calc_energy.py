"""
tests/test_calc_energy.py — Unit tests for energy calculation module.
All numbers verified by hand calculation.
"""

import datetime
import pytest
import pandas as pd
import numpy as np

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from calc.energy import (
    assign_shift,
    compute_baseline,
    run_energy_analysis,
    compute_idle_run_kwh,
)


# ─── assign_shift ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hour,expected", [
    (0,  "night"),
    (5,  "night"),
    (6,  "day"),
    (13, "day"),
    (14, "evening"),
    (21, "evening"),
    (22, "night"),
    (23, "night"),
])
def test_assign_shift(hour, expected):
    assert assign_shift(hour) == expected


# ─── compute_baseline ────────────────────────────────────────────────────────

def _make_df(n_days: int = 28, base_kwh: float = 100.0, shift: str = "night") -> pd.DataFrame:
    """Helper: n_days of uniform kWh at the given shift."""
    rows = []
    start = datetime.datetime(2026, 1, 1, 22, 0)   # always a night shift hour
    for i in range(n_days):
        ts = start + datetime.timedelta(days=i)
        rows.append({"timestamp": ts, "kwh": base_kwh, "shift": shift, "weekday": ts.weekday()})
    return pd.DataFrame(rows)


def test_compute_baseline_mean():
    df = _make_df(28, base_kwh=100.0)
    # Ask for baseline at day 29
    target = pd.Timestamp("2026-01-29 22:00:00")
    mean, std, n = compute_baseline(df, target, "night", baseline_weeks=4)
    # All 28 readings are 100.0 → mean should be exactly 100.0
    assert abs(mean - 100.0) < 0.001, f"Expected mean=100.0, got {mean}"
    assert n > 0


def test_compute_baseline_std_zero_for_constant():
    df = _make_df(28, base_kwh=50.0)
    target = pd.Timestamp("2026-01-29 22:00:00")
    _, std, _ = compute_baseline(df, target, "night", baseline_weeks=4)
    assert std < 0.001  # constant data → std ≈ 0


def test_compute_baseline_no_data_returns_zeros():
    df = _make_df(5)   # too few days
    target = pd.Timestamp("2026-01-29 22:00:00")
    mean, std, n = compute_baseline(df, target, "day", baseline_weeks=4)
    # No day-shift data → returns 0,0,0
    assert mean == 0.0
    assert n == 0


# ─── run_energy_analysis ─────────────────────────────────────────────────────

def _make_analysis_df(n_days: int = 56, anomaly_day: int = 50, anomaly_mult: float = 1.3) -> pd.DataFrame:
    """
    n_days of 15-min readings.
    On anomaly_day, the night shift kWh is multiplied by anomaly_mult.
    """
    rows = []
    start = datetime.datetime(2026, 1, 1, 0, 0)
    base = {"day": 18.5, "evening": 15.2, "night": 10.8}
    for day in range(n_days):
        for interval in range(96):  # 96 × 15min = 1 day
            ts = start + datetime.timedelta(days=day, minutes=interval * 15)
            hour = ts.hour
            shift = assign_shift(hour)
            kwh = base[shift]
            if day == anomaly_day and shift == "night":
                kwh *= anomaly_mult
            rows.append({"timestamp": ts, "kwh": kwh})
    return pd.DataFrame(rows)


def test_run_energy_analysis_flags_anomaly():
    df = _make_analysis_df(n_days=56, anomaly_day=50, anomaly_mult=1.35)
    result = run_energy_analysis(df, upload_id="test-001", threshold_pct=20.0, baseline_weeks=4)
    assert len(result.anomalies) >= 1
    assert result.total_excess_kwh > 0


def test_run_energy_analysis_no_false_positives_on_clean_data():
    df = _make_analysis_df(n_days=56, anomaly_day=-1, anomaly_mult=1.0)   # no anomaly
    result = run_energy_analysis(df, upload_id="test-002", threshold_pct=20.0, baseline_weeks=4)
    # With perfectly uniform data and threshold=20%, nothing should flag
    assert len(result.anomalies) == 0


def test_excess_kwh_calculation():
    """Hand-verify: excess = actual - baseline."""
    df = _make_analysis_df(n_days=56, anomaly_day=50, anomaly_mult=1.30)
    result = run_energy_analysis(df, upload_id="test-003", threshold_pct=20.0, baseline_weeks=4)
    for a in result.anomalies:
        # excess should equal actual - baseline (within floating point)
        expected_excess = a.actual_kwh - a.baseline_kwh
        assert abs(a.excess_kwh - expected_excess) < 0.01, \
            f"excess mismatch: {a.excess_kwh} vs {expected_excess}"


def test_missing_kwh_column():
    df = pd.DataFrame({"timestamp": [datetime.datetime.now()], "watts": [100.0]})
    result = run_energy_analysis(df, upload_id="test-bad")
    assert not result.anomalies
    assert len(result.errors) > 0


# ─── compute_idle_run_kwh ────────────────────────────────────────────────────

def test_idle_run_kwh():
    # 10 kW motor, idle for 3 hours → 30 kWh
    result = compute_idle_run_kwh(rated_kw=10.0, idle_hours=3.0)
    assert result == 30.0


def test_idle_run_kwh_zero_hours():
    assert compute_idle_run_kwh(rated_kw=50.0, idle_hours=0.0) == 0.0


def test_idle_run_kwh_zero_kw():
    assert compute_idle_run_kwh(rated_kw=0.0, idle_hours=5.0) == 0.0

