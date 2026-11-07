"""
tests/test_verify_postfix.py — Unit tests for post-fix verification logic.
Tests energy and water post-fix comparison, percentage changes, savings, and verdicts.
"""

import pandas as pd
import pytest

from verify.postfix import verify_energy_fix, verify_water_fix


def _make_energy_df(dates, shift_kwh: float, base_date: str = "2026-10-01"):
    """Generate 15-minute intervals for test dates."""
    records = []
    # 96 intervals per day
    for d in dates:
        for hour in range(24):
            for minute in (0, 15, 30, 45):
                ts = pd.Timestamp(f"{d} {hour:02d}:{minute:02d}:00")
                # Allocate kwh per interval so that morning shift (06:00-14:00, 32 intervals) sums to shift_kwh
                # and other shifts sum to shift_kwh
                records.append({
                    "timestamp": ts,
                    "kwh": shift_kwh / 32.0,
                    "equipment": "MAIN-FEED",
                })
    return pd.DataFrame(records)


def test_verify_energy_fix_improved():
    """Verify that a drop in shift consumption is correctly flagged as 'improved'."""
    # 4 weeks of baseline dates for Morning shift
    baseline_dates = [f"2026-09-{i:02d}" for i in range(1, 29)]
    postfix_dates = [f"2026-10-{i:02d}" for i in range(1, 8)]

    # Baseline Morning shift had high consumption (e.g. 500 kWh) due to anomaly
    baseline_df = _make_energy_df(baseline_dates, shift_kwh=500.0)
    # Post-fix Morning shift had lower consumption (e.g. 350 kWh)
    postfix_df = _make_energy_df(postfix_dates, shift_kwh=350.0)

    result = verify_energy_fix(
        action_id=1,
        baseline_df=baseline_df,
        postfix_df=postfix_df,
        shift="Morning",
        baseline_weeks=4,
    )

    assert result.track == "energy"
    assert result.verdict == "improved"
    assert result.baseline_avg == pytest.approx(500.0, rel=1e-2)
    assert result.postfix_avg == pytest.approx(350.0, rel=1e-2)
    assert result.pct_change < -20.0
    assert result.value_saved == pytest.approx(150.0, rel=1e-2)
    assert result.cost_saved > 0.0  # ₹ saved calculated in code


def test_verify_energy_fix_worsened():
    """Verify that an increase in post-fix consumption is flagged as 'worsened'."""
    baseline_dates = [f"2026-09-{i:02d}" for i in range(1, 29)]
    postfix_dates = [f"2026-10-{i:02d}" for i in range(1, 8)]

    baseline_df = _make_energy_df(baseline_dates, shift_kwh=300.0)
    postfix_df = _make_energy_df(postfix_dates, shift_kwh=400.0)

    result = verify_energy_fix(
        action_id=2,
        baseline_df=baseline_df,
        postfix_df=postfix_df,
        shift="Morning",
        baseline_weeks=4,
    )

    assert result.verdict == "worsened"
    assert result.pct_change > 5.0
    assert result.value_saved == 0.0
    assert result.cost_saved == 0.0


def test_verify_energy_fix_no_readings_for_shift():
    """Verify graceful handling when post-fix has no data for the requested shift."""
    baseline_dates = ["2026-09-01", "2026-09-02"]
    baseline_df = _make_energy_df(baseline_dates, shift_kwh=300.0)
    
    # Empty post-fix dataframe
    postfix_df = pd.DataFrame(columns=["timestamp", "kwh", "equipment"])

    result = verify_energy_fix(
        action_id=3,
        baseline_df=baseline_df,
        postfix_df=postfix_df,
        shift="Night",
    )

    assert result.verdict == "no_change"
    assert "No post-fix readings found" in result.note


def test_verify_water_fix_improved():
    """Verify that resolving a water leak shows 'improved' verdict and calculates savings."""
    baseline_df = pd.DataFrame([
        {"date": f"2026-09-{i:02d}", "intake_kl": 100.0, "process_kl": 70.0, "discharge_kl": 10.0}
        for i in range(1, 15)
    ])  # unaccounted = 100 - 70 - 10 = 20 kL/day

    postfix_df = pd.DataFrame([
        {"date": f"2026-10-{i:02d}", "intake_kl": 82.0, "process_kl": 70.0, "discharge_kl": 10.0}
        for i in range(1, 8)
    ])  # unaccounted = 82 - 70 - 10 = 2 kL/day

    result = verify_water_fix(
        action_id=10,
        baseline_df=baseline_df,
        postfix_df=postfix_df,
    )

    assert result.track == "water"
    assert result.verdict == "improved"
    assert result.baseline_avg == pytest.approx(20.0, rel=1e-2)
    assert result.postfix_avg == pytest.approx(2.0, rel=1e-2)
    assert result.value_saved == pytest.approx(18.0, rel=1e-2)
    assert result.pct_change == pytest.approx(-90.0, rel=1e-2)
    assert result.cost_saved == pytest.approx(18.0 * 45.0, rel=1e-2)  # ₹45/kL


def test_verify_water_fix_worsened():
    """Verify water verification detects increased unaccounted loss."""
    baseline_df = pd.DataFrame([
        {"date": f"2026-09-{i:02d}", "intake_kl": 82.0, "process_kl": 70.0, "discharge_kl": 10.0}
        for i in range(1, 15)
    ])  # unaccounted = 2 kL/day

    postfix_df = pd.DataFrame([
        {"date": f"2026-10-{i:02d}", "intake_kl": 110.0, "process_kl": 70.0, "discharge_kl": 10.0}
        for i in range(1, 8)
    ])  # unaccounted = 30 kL/day

    result = verify_water_fix(
        action_id=11,
        baseline_df=baseline_df,
        postfix_df=postfix_df,
    )

    assert result.verdict == "worsened"
    assert result.pct_change > 10.0
    assert result.value_saved == 0.0
    assert result.cost_saved == 0.0

