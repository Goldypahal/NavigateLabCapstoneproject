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
from db.models import Anomaly, Evidence, Explanation, Action, Reading, Approval
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

    # Clean up prior analysis results for this upload while preserving manager decisions (Bug 7)
    existing_anomalies = db.query(Anomaly).filter(Anomaly.upload_id == req.upload_id).all()
    preserved_action_keys = set()
    for ea in existing_anomalies:
        existing_actions = db.query(Action).filter(Action.anomaly_id == ea.anomaly_id).all()
        for act in existing_actions:
            if act.status in ("approved", "edited", "rejected"):
                # Preserve manager-reviewed actions, their approvals, and verification records!
                preserved_action_keys.add((act.anomaly_id, act.action_text))
            else:
                # Remove un-reviewed pending actions
                db.delete(act)
        # Remove old explanation to regenerate fresh AI explanation
        db.query(Explanation).filter(Explanation.anomaly_id == ea.anomaly_id).delete()
    db.flush()

    evidence_rows = db.query(Evidence).filter(Evidence.upload_id == req.upload_id).all()
    evidence_store = _build_evidence_store(evidence_rows)

    tracks = [req.track] if req.track != "both" else ["energy", "water"]
    total_anomalies = 0

    from ai.explain import (
        _sanitize_and_validate_llm_output,
        ExplainJSON,
        retrieve_relevant_evidence,
        _check_injection,
        _INJECTION_RE,
    )
    import nexus_client as nc

    for track in tracks:
        track_readings = [r for r in readings if r.track == track]
        if not track_readings:
            continue

        df = _readings_to_df(track_readings, track)

        # Baseline across uploads: fetch prior historical readings for baseline (Bug 6 & Bug 3)
        hist_readings = db.query(Reading).filter(
            Reading.track == track,
            Reading.upload_id != req.upload_id
        ).all()
        historical_df = _readings_to_df(hist_readings, track) if hist_readings else None

        if track == "energy":
            analysis = run_energy_analysis(
                df,
                upload_id=req.upload_id,
                threshold_pct=req.threshold_pct,
                sigma=req.sigma,
                baseline_weeks=req.baseline_weeks,
                historical_df=historical_df,
            )
            anomaly_list = analysis.anomalies
        else:
            analysis = run_water_analysis(
                df,
                upload_id=req.upload_id,
                baseline_weeks=req.baseline_weeks,
                historical_df=historical_df,
            )
            anomaly_list = analysis.anomalies

        if not anomaly_list:
            continue

        # Prepare anomaly summaries, per-anomaly filtered evidence, and persist DB anomalies
        anom_summaries = []
        anom_meta = {}
        anom_rel_evidence = {}

        for anom in anomaly_list:
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
                anom_date = ts.date()
                eq = getattr(anom, "equipment", None)
            else:
                cost_est = estimate_water_cost(anom.total_loss_kl)
                excess = anom.total_loss_kl
                actual = anom.unaccounted_kl
                baseline = anom.baseline_unaccounted_kl
                if anom.baseline_unaccounted_kl > 0.5:
                    deviation_pct = round((anom.unaccounted_kl - anom.baseline_unaccounted_kl) / anom.baseline_unaccounted_kl * 100, 2)
                else:
                    deviation_pct = 100.0 if anom.unaccounted_kl > 0 else 0.0
                sigma_dev = None
                ts = datetime.datetime.combine(anom.date, datetime.time())
                shift = None
                anom_date = anom.date
                eq = None

            # Code-side evidence filtering by date, shift, and equipment (Bug 1 fix)
            rel_ev = retrieve_relevant_evidence(
                evidence_store,
                anom_date,
                shift=shift,
                equipment=eq,
                duration_days=getattr(anom, "days_above_threshold", 1),
            )

            # Prompt injection security scanning & neutralization (Bug 1 fix)
            safe_rel_ev = []
            for ev in rel_ev:
                ev_copy = dict(ev)
                raw_text = ev_copy.get("text", "")
                if _check_injection(raw_text):
                    ev_copy["text"] = _INJECTION_RE.sub(
                        "[SECURITY_QUARANTINE: Injection payload intercepted and neutralized]",
                        raw_text,
                    )
                safe_rel_ev.append(ev_copy)

            anom_rel_evidence[anom.anomaly_id] = safe_rel_ev

            # Upsert anomaly record (Bug 2 fix: avoid UNIQUE constraint failures on re-analysis)
            existing_anom = db.query(Anomaly).filter(Anomaly.anomaly_id == anom.anomaly_id).first()
            if existing_anom:
                existing_anom.timestamp = ts
                existing_anom.shift = shift
                existing_anom.weekday = ts.weekday() if ts else None
                existing_anom.actual_value = actual
                existing_anom.baseline_value = baseline
                existing_anom.deviation_pct = deviation_pct
                existing_anom.excess_value = excess
                existing_anom.sigma_deviation = sigma_dev
                existing_anom.estimated_cost = cost_est.total_cost
                existing_anom.unaccounted_kl = anom.unaccounted_kl if track == "water" else None
            else:
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

            anom_summaries.append({
                "anomaly_id": anom.anomaly_id,
                "track": track,
                "timestamp": str(ts),
                "shift": shift,
                "deviation_pct": deviation_pct,
                "relevant_evidence": [
                    {"source_id": e["source_id"], "type": e["type"], "text": e["text"]}
                    for e in safe_rel_ev
                ]
            })
            anom_meta[anom.anomaly_id] = {
                "excess": excess,
                "cost": cost_est.total_cost,
                "track": track,
            }
            total_anomalies += 1

        # Batched LLM Explanation: 1 batched call with per-anomaly isolated relevant evidence
        llm_batch_res = nc.explain_anomalies_batch(
            anomalies_summary=anom_summaries,
            evidence_snippets=evidence_store,
            model=req.model,
            track=track,
        )

        source_id_to_text = {e["source_id"]: e["text"] for e in evidence_store}

        try:
            parsed_batch = json.loads(llm_batch_res.content)
            explanations_list = parsed_batch.get("explanations", [])
        except Exception:
            explanations_list = []

        expl_by_id = {item.get("anomaly_id"): item for item in explanations_list if isinstance(item, dict)}

        for anom in anomaly_list:
            raw_item = expl_by_id.get(anom.anomaly_id) or {
                "anomaly_id": anom.anomaly_id,
                "track": track,
                "likely_cause": "No conclusive worker log found for this period",
                "cause_status": "unknown",
                "evidence": [],
                "missing_information": ["No corroborating operator note or inspection sheet"],
                "conflicts": [],
                "uncertainty_note": "Cause unknown: no equipment logs match this shift",
                "recommended_actions": [],
            }

            try:
                raw_item["track"] = track
                raw_item["anomaly_id"] = anom.anomaly_id
                ej = ExplainJSON(**raw_item)
            except Exception:
                ej = ExplainJSON(
                    anomaly_id=anom.anomaly_id,
                    track=track,
                    likely_cause="Worker note verification pending",
                    cause_status="unknown",
                    evidence=[],
                    missing_information=[],
                    conflicts=[],
                    uncertainty_note="Cause unknown",
                    recommended_actions=[],
                )

            # Sanitize numbers and validate citations strictly against THIS anomaly's relevant evidence (Bug 1 fix)
            anom_evidence = anom_rel_evidence.get(anom.anomaly_id, [])
            cleaned_ej, is_valid, validation_errors = _sanitize_and_validate_llm_output(
                ej, anom_evidence, source_id_to_text
            )

            exp = Explanation(
                anomaly_id=anom.anomaly_id,
                model_used=llm_batch_res.model,
                raw_json=json.dumps(cleaned_ej.model_dump()),
                likely_cause=cleaned_ej.likely_cause,
                cause_status=cleaned_ej.cause_status,
                uncertainty_note=cleaned_ej.uncertainty_note,
                missing_information=json.dumps(cleaned_ej.missing_information),
                conflicts=json.dumps(cleaned_ej.conflicts),
                evidence_json=json.dumps([e.model_dump() for e in cleaned_ej.evidence]),
                is_valid=is_valid,
                validation_errors=json.dumps(validation_errors),
                input_tokens=llm_batch_res.input_tokens // max(1, len(anomaly_list)),
                output_tokens=llm_batch_res.output_tokens // max(1, len(anomaly_list)),
            )
            db.add(exp)
            db.flush()

            meta = anom_meta[anom.anomaly_id]
            action_dicts = []
            for ra in cleaned_ej.recommended_actions:
                # Skip duplicate creation if this action is already approved/edited/rejected (Bug 7 fix)
                if (anom.anomaly_id, ra.action) in preserved_action_keys:
                    continue
                action_dicts.append({
                    "anomaly_id": anom.anomaly_id,
                    "action_text": ra.action,
                    "equipment": ra.equipment,
                    "urgency": ra.urgency,
                    "estimated_loss": meta["excess"],
                    "estimated_cost": meta["cost"],
                    "evidence_source_ids": json.dumps([e.source_id for e in cleaned_ej.evidence]),
                })

            ranked = rank_actions_by_loss(action_dicts, track)
            for ad in ranked:
                db.add(Action(**ad))

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

