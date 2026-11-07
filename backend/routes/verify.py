"""
routes/verify.py — Post-fix verification endpoints (stretch feature).

POST /api/verify/energy — upload post-fix energy CSV and compare vs. baseline
POST /api/verify/water  — upload post-fix water CSV and compare vs. baseline
GET  /api/verify/{action_id} — get verification result for an action
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Action, Anomaly, Reading, VerificationRecord
from ingest.csv_validator import validate_energy_csv, validate_water_csv
from verify.postfix import verify_energy_fix, verify_water_fix
import datetime
import pandas as pd

router = APIRouter(prefix="/api/verify", tags=["verify"])


class VerifyResponse(BaseModel):
    action_id: int
    track: str
    baseline_avg: float
    postfix_avg: float
    pct_change: float
    value_saved: float
    cost_saved: float
    verdict: str
    note: str


@router.post("/energy", response_model=VerifyResponse)
async def verify_energy(
    action_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Compare post-fix energy readings against the action's baseline."""
    action = db.get(Action, action_id)
    if not action:
        raise HTTPException(404, f"Action {action_id} not found.")
    if action.status not in ("approved", "edited"):
        raise HTTPException(400, "Action must be approved before verification.")

    content = await file.read()
    val = validate_energy_csv(content)
    if not val.is_valid:
        raise HTTPException(400, f"Invalid CSV: {val.errors}")

    # Fetch baseline readings for the same anomaly's upload
    anomaly = db.query(Anomaly).filter(Anomaly.anomaly_id == action.anomaly_id).first()
    baseline_readings = db.query(Reading).filter(
        Reading.upload_id == anomaly.upload_id,
        Reading.track == "energy"
    ).all()
    baseline_df = pd.DataFrame([{"timestamp": r.timestamp, "kwh": r.kwh} for r in baseline_readings])

    result = verify_energy_fix(
        action_id=action_id,
        baseline_df=baseline_df,
        postfix_df=val.df,
        shift=anomaly.shift or "day",
    )

    # Persist
    record = VerificationRecord(
        action_id=action_id,
        upload_id_post="postfix",
        baseline_avg=result.baseline_avg,
        postfix_avg=result.postfix_avg,
        pct_change=result.pct_change,
        value_saved=result.value_saved,
        cost_saved=result.cost_saved,
    )
    db.add(record)
    db.commit()

    return VerifyResponse(**result.__dict__)


@router.post("/water", response_model=VerifyResponse)
async def verify_water(
    action_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Compare post-fix water readings against the action's baseline."""
    action = db.get(Action, action_id)
    if not action:
        raise HTTPException(404, f"Action {action_id} not found.")
    if action.status not in ("approved", "edited"):
        raise HTTPException(400, "Action must be approved before verification.")

    content = await file.read()
    val = validate_water_csv(content)
    if not val.is_valid:
        raise HTTPException(400, f"Invalid CSV: {val.errors}")

    anomaly = db.query(Anomaly).filter(Anomaly.anomaly_id == action.anomaly_id).first()
    baseline_readings = db.query(Reading).filter(
        Reading.upload_id == anomaly.upload_id,
        Reading.track == "water"
    ).all()
    baseline_df = pd.DataFrame([{
        "intake_kl": r.intake_kl,
        "process_kl": r.process_kl,
        "discharge_kl": r.discharge_kl,
    } for r in baseline_readings])

    result = verify_water_fix(action_id=action_id, baseline_df=baseline_df, postfix_df=val.df)

    record = VerificationRecord(
        action_id=action_id,
        upload_id_post="postfix",
        baseline_avg=result.baseline_avg,
        postfix_avg=result.postfix_avg,
        pct_change=result.pct_change,
        value_saved=result.value_saved,
        cost_saved=result.cost_saved,
    )
    db.add(record)
    db.commit()

    return VerifyResponse(**result.__dict__)

