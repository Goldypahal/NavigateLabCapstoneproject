"""
tests/test_calc_water.py — Unit tests for water balance calculation.
All formulas verified by hand.
"""

import datetime
import pytest
import pandas as pd

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from calc.water import compute_water_balance, run_water_analysis


# ─── compute_water_balance ────────────────────────────────────────────────────

def test_water_balance_normal():
    """unaccounted = intake - process - discharge"""
    row = pd.Series({"intake_kl": 85.0, "process_kl": 60.0, "discharge_kl": 22.0})
    result = compute_water_balance(row)
    # 85 - 60 - 22 = 3.0
    assert abs(result - 3.0) < 0.001


def test_water_balance_negative_conflict():
    """Negative unaccounted = metering conflict."""
    row = pd.Series({"intake_kl": 50.0, "process_kl": 60.0, "discharge_kl": 22.0})
    result = compute_water_balance(row)
    # 50 - 60 - 22 = -32 → conflict
    assert result < 0


def test_water_balance_zero():
    row = pd.Series({"intake_kl": 100.0, "process_kl": 70.0, "discharge_kl": 30.0})
    result = compute_water_balance(row)
    assert abs(result) < 0.001


# ─── run_water_analysis ───────────────────────────────────────────────────────

def _make_water_df(n_days: int = 56, anomaly_start: int = 42, anomaly_kl: float = 18.0) -> pd.DataFrame:
    rows = []
    base_date = datetime.date(2026, 1, 1)
    for i in range(n_days):
        date = base_date + datetime.timedelta(days=i)
        intake   = 85.0
        process  = 60.0
        discharge = 22.0
        if anomaly_start <= i < n_days:
            intake += anomaly_kl  # unaccounted increases by anomaly_kl
        rows.append({"date": date, "intake_kl": intake, "process_kl": process, "discharge_kl": discharge})
    return pd.DataFrame(rows)


def test_run_water_analysis_flags_anomaly():
    df = _make_water_df(n_days=56, anomaly_start=42, anomaly_kl=18.0)
    result = run_water_analysis(df, upload_id="water-001", threshold_kl=5.0)
    assert len(result.anomalies) >= 1
    # The flagged anomaly should show unaccounted close to 18+3=21 kL/day
    for a in result.anomalies:
        if not a.is_metering_conflict:
            assert a.unaccounted_kl > 5.0  # above threshold


def test_run_water_analysis_no_anomaly_on_clean_data():
    df = _make_water_df(n_days=56, anomaly_start=999, anomaly_kl=0.0)  # no anomaly
    result = run_water_analysis(df, upload_id="water-002", threshold_kl=5.0)
    real_anomalies = [a for a in result.anomalies if not a.is_metering_conflict]
    assert len(real_anomalies) == 0


def test_water_conflict_flagged():
    """Metering conflict: discharge > intake."""
    rows = []
    base = datetime.date(2026, 1, 1)
    for i in range(30):
        intake = 85.0
        process = 60.0
        discharge = 22.0
        if i == 14:
            discharge = 110.0  # impossible — more out than in
        rows.append({"date": base + datetime.timedelta(days=i), "intake_kl": intake,
                     "process_kl": process, "discharge_kl": discharge})
    df = pd.DataFrame(rows)
    result = run_water_analysis(df, upload_id="water-003", threshold_kl=5.0)
    conflict = [a for a in result.anomalies if a.is_metering_conflict]
    assert len(conflict) == 1


def test_total_loss_calculation():
    """total_loss_kl = excess_kl × days (hand-verified)."""
    df = _make_water_df(n_days=56, anomaly_start=42, anomaly_kl=18.0)
    result = run_water_analysis(df, upload_id="water-004", threshold_kl=5.0)
    for a in result.anomalies:
        if not a.is_metering_conflict:
            expected = round(a.excess_kl * a.days_above_threshold, 3)
            assert abs(a.total_loss_kl - expected) < 0.1


def test_missing_column_error():
    df = pd.DataFrame({"date": [datetime.date(2026, 1, 1)], "intake_kl": [85.0]})
    result = run_water_analysis(df, upload_id="bad-001")
    assert len(result.errors) > 0
    assert len(result.anomalies) == 0


# ─── Cost hand-check ─────────────────────────────────────────────────────────

def test_water_cost_formula():
    from calc.cost import estimate_water_cost
    result = estimate_water_cost(excess_kl=18.0)
    # 18 × 45.0 = 810.0 ₹
    assert abs(result.total_cost - 810.0) < 0.01
    assert result.unit == "kL"


def test_energy_cost_formula():
    from calc.cost import estimate_energy_cost
    import datetime
    result = estimate_energy_cost(excess_kwh=42.5, timestamp=None, use_tod=False)
    # 42.5 × 7.5 = 318.75 ₹
    assert abs(result.total_cost - 318.75) < 0.01
    assert result.unit == "kWh"

