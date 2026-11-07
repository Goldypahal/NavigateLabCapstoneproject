"""
tests/test_csv_validator.py — Tests for the CSV ingest validator.
"""

import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from ingest.csv_validator import validate_energy_csv, validate_water_csv

# ─── Energy CSV ───────────────────────────────────────────────────────────────

GOOD_ENERGY_CSV = b"""timestamp,kwh
2026-01-01 00:00:00,10.5
2026-01-01 00:15:00,11.2
2026-01-01 00:30:00,9.8
"""

MISSING_KWH_CSV = b"""timestamp,watts
2026-01-01 00:00:00,10.5
"""

NEGATIVE_KWH_CSV = b"""timestamp,kwh
2026-01-01 00:00:00,-5.0
"""

DUPLICATE_TS_CSV = b"""timestamp,kwh
2026-01-01 00:00:00,10.0
2026-01-01 00:00:00,10.0
"""

NON_NUMERIC_KWH = b"""timestamp,kwh
2026-01-01 00:00:00,abc
"""

def test_valid_energy_csv():
    r = validate_energy_csv(GOOD_ENERGY_CSV)
    assert r.is_valid
    assert r.row_count == 3
    assert len(r.errors) == 0

def test_missing_column_energy():
    r = validate_energy_csv(MISSING_KWH_CSV)
    assert not r.is_valid
    assert any("kwh" in e.lower() for e in r.errors)

def test_negative_kwh_rejected():
    r = validate_energy_csv(NEGATIVE_KWH_CSV)
    assert not r.is_valid
    assert any("negative" in e.lower() for e in r.errors)

def test_duplicate_timestamps_rejected():
    r = validate_energy_csv(DUPLICATE_TS_CSV)
    assert not r.is_valid
    assert any("duplicate" in e.lower() for e in r.errors)

def test_non_numeric_kwh_rejected():
    r = validate_energy_csv(NON_NUMERIC_KWH)
    assert not r.is_valid

# ─── Water CSV ────────────────────────────────────────────────────────────────

GOOD_WATER_CSV = b"""date,intake_kl,process_kl,discharge_kl
2026-01-01,85.0,60.0,22.0
2026-01-02,86.0,61.0,22.5
"""

MISSING_COL_WATER = b"""date,intake_kl,process_kl
2026-01-01,85.0,60.0
"""

def test_valid_water_csv():
    r = validate_water_csv(GOOD_WATER_CSV)
    assert r.is_valid
    assert r.row_count == 2

def test_missing_discharge_col():
    r = validate_water_csv(MISSING_COL_WATER)
    assert not r.is_valid
    assert any("discharge" in e.lower() for e in r.errors)

def test_timestamp_alias_accepted():
    csv = b"timestamp,intake_kl,process_kl,discharge_kl\n2026-01-01,85,60,22\n"
    r = validate_water_csv(csv)
    assert r.is_valid

