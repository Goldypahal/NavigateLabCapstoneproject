"""
routes/analysis.py — Analysis endpoints.

POST /api/analysis/run          — trigger baseline + anomaly + explain pipeline
GET  /api/analysis/{upload_id}  — fetch analysis results
GET  /api/analysis/{upload_id}/anomalies — list anomalies with computed numbers
"""

from __future__ import annotations

import json
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Anomaly, Evidence, Explanation, Action, Reading
from calc.energy import run_energy_analysis
from calc.water import run_water_analysis
from calc.cost import estimate_energy_cost, estimate_water_cost, rank_actions_by_loss
from ai.explain import explain_anomaly_with_evidence
from config import settings
import pandas as pd

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class RunAnalysisRequest(BaseModel):
    upload_id: str
    track: str                          # 'energy' | 'water' | 'both'
    model: Optional[str] = None         # LLM model override for A/B testing
    threshold_pct: Optional[float] = None
    sigma: Optional[float] = None
    baseline_weeks: Optional[int] = None


class AnomalySummary(BaseModel):
    anomaly_id: str
    track: str
    timestamp: str
    shift: Optional[str]
    actual_value: float
    baseline_value: float
    deviation_pct: float
    excess_value: float
    estimated_cost: Optional[float]
    cause_status: Optional[str]
    likely_cause: Optional[str]
    uncertainty_note: Optional[str]
    action_count: int


@router.post("/run")
async def run_analysis(req: RunAnalysisRequest, db: Session = Depends(get_db)):
    """Run the full analysis pipeline for an upload."""
    readings = db.query(Reading).filter(Reading.upload_id == req.upload_id).all()
    if not readings:
        raise HTTPException(404, f"No readings found for upload_id={req.upload_id}")

    evidence_rows = db.query(Evidence).filter(Evidence.upload_id == req.upload_id).all()
    evidence_store = _build_evidence_store(evidence_rows)

    tracks = [req.track] if req.track != "both" else ["energy", "water"]
    total_anomalies = 0

    for track in tracks:
        track_readings = [r for r in readings if r.track == track]
        if not track_readings:
            continue

        df = _readings_to_df(track_readings, track)

        if track == "energy":
            analysis = run_energy_analysis(
                df,
                upload_id=req.upload_id,
                threshold_pct=req.threshold_pct,
                sigma=req.sigma,
                baseline_weeks=req.baseline_weeks,
            )
            anomaly_list = analysis.anomalies
        else:
            analysis = run_water_analysis(
                df,
                upload_id=req.upload_id,
                baseline_weeks=req.baseline_weeks,
            )
            anomaly_list = analysis.anomalies

        for anom in anomaly_list:
            # Compute cost
            if track == "energy":
                cost_est = estimate_energy_cost(
                    anom.excess_kwh,
                    timestamp=anom.timestamp,
                )
                excess = anom.excess_kwh
                actual = anom.actual_kwh
                baseline = anom.baseline_kwh
                deviation_pct = anom.deviation_pct
                sigma_dev = anom.sigma_deviation
                ts = anom.timestamp
                shift = anom.shift
            else:
                cost_est = estimate_water_cost(anom.excess_kl)
                excess = anom.excess_kl
                actual = anom.unaccounted_kl
                baseline = anom.baseline_unaccounted_kl
                deviation_pct = round((anom.unaccounted_kl - anom.baseline_unaccounted_kl) / max(anom.baseline_unaccounted_kl, 0.01) * 100, 2)
                sigma_dev = None
                ts = datetime.datetime.combine(anom.date, datetime.time())
                shift = None

            # Persist anomaly
            existing = db.query(Anomaly).filter(Anomaly.anomaly_id == anom.anomaly_id).first()
            if not existing:
                db_anomaly = Anomaly(
                    anomaly_id=anom.anomaly_id,
                    upload_id=req.upload_id,
                    track=track,
                    timestamp=ts,
                    shift=shift,
                    weekday=ts.weekday() if ts else None,
                    actual_value=actual,
                    baseline_value=baseline,
                    deviation_pct=deviation_pct,
                    excess_value=excess,
                    sigma_deviation=sigma_dev,
                    estimated_cost=cost_est.total_cost,
                    unaccounted_kl=anom.unaccounted_kl if track == "water" else None,
                )
                db.add(db_anomaly)
                db.flush()

            # LLM explain
            anom_dict = {
                "anomaly_id": anom.anomaly_id,
                "track": track,
                "timestamp": ts,
                "shift": shift,
                "deviation_pct": deviation_pct,
            }
            explain_result = explain_anomaly_with_evidence(
                anomaly=anom_dict,
                evidence_store=evidence_store,
                track=track,
                model=req.model,
            )

            # Persist explanation
            if explain_result.explain_json:
                ej = explain_result.explain_json
                exp = Explanation(
                    anomaly_id=anom.anomaly_id,
                    model_used=explain_result.model_used,
                    raw_json=explain_result.raw_json,
                    likely_cause=ej.likely_cause,
                    cause_status=ej.cause_status,
                    uncertainty_note=ej.uncertainty_note,
                    missing_information=json.dumps(ej.missing_information),
                    conflicts=json.dumps(ej.conflicts),
                    evidence_json=json.dumps([e.model_dump() for e in ej.evidence]),
                    is_valid=explain_result.is_valid,
                    validation_errors=json.dumps(explain_result.validation_errors),
                    input_tokens=explain_result.input_tokens,
                    output_tokens=explain_result.output_tokens,
                )
                db.add(exp)
                db.flush()

                # Create actions (code ranks them)
                action_dicts = []
                for ra in ej.recommended_actions:
                    action_dicts.append({
                        "anomaly_id": anom.anomaly_id,
                        "action_text": ra.action,
                        "equipment": ra.equipment,
                        "urgency": ra.urgency,
                        "estimated_loss": excess,
                        "estimated_cost": cost_est.total_cost,
                        "evidence_source_ids": json.dumps([e.source_id for e in ej.evidence]),
                    })

                action_dicts = rank_actions_by_loss(action_dicts, track)
                for ad in action_dicts:
                    db.add(Action(**{k: v for k, v in ad.items() if k != "anomaly_id"},
                                 anomaly_id=ad["anomaly_id"]))

            total_anomalies += 1

    db.commit()
    return {"message": f"Analysis complete. {total_anomalies} anomalies found.", "upload_id": req.upload_id}


@router.get("/{upload_id}/anomalies", response_model=list[AnomalySummary])
def get_anomalies(upload_id: str, db: Session = Depends(get_db)):
    """Return all anomalies for an upload with computed numbers and explanation status."""
    anomalies = db.query(Anomaly).filter(Anomaly.upload_id == upload_id).all()
    result = []
    for a in anomalies:
        exp = a.explanation
        result.append(AnomalySummary(
            anomaly_id=a.anomaly_id,
            track=a.track,
            timestamp=a.timestamp.isoformat(),
            shift=a.shift,
            actual_value=a.actual_value,
            baseline_value=a.baseline_value,
            deviation_pct=a.deviation_pct,
            excess_value=a.excess_value,
            estimated_cost=a.estimated_cost,
            cause_status=exp.cause_status if exp else None,
            likely_cause=exp.likely_cause if exp else None,
            uncertainty_note=exp.uncertainty_note if exp else None,
            action_count=len(a.actions),
        ))
    return sorted(result, key=lambda x: abs(x.deviation_pct), reverse=True)


def _build_evidence_store(evidence_rows) -> list[dict]:
    store = []
    for ev in evidence_rows:
        store.append({
            "source_id": ev.source_id,
            "type": ev.evidence_type,
            "date": ev.date.date() if ev.date else None,
            "shift": ev.shift,
            "equipment": ev.equipment,
            "text": ev.text_content or "",
        })
    return store


def _readings_to_df(readings, track: str) -> pd.DataFrame:
    rows = []
    for r in readings:
        if track == "energy":
            rows.append({"timestamp": r.timestamp, "kwh": r.kwh})
        else:
            rows.append({
                "date": r.timestamp.date(),
                "intake_kl": r.intake_kl,
                "process_kl": r.process_kl,
                "discharge_kl": r.discharge_kl,
            })
    return pd.DataFrame(rows)

