"""
routes/review.py — Manager review endpoints.

GET  /api/review/{upload_id}/actions   — list all pending actions
POST /api/review/decide                — approve / reject / edit an action
POST /api/review/{upload_id}/briefing  — generate TTS audio for approved actions
GET  /api/review/{upload_id}/briefing  — download the generated briefing audio
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Action, Anomaly
from review.approval import apply_review_decision, get_approved_actions_text, ReviewDecision
import nexus_client as nc
from config import settings

router = APIRouter(prefix="/api/review", tags=["review"])

AUDIO_DIR = Path("audio_output")
AUDIO_DIR.mkdir(exist_ok=True)


class ActionDetail(BaseModel):
    id: int
    anomaly_id: str
    track: str
    action_text: str
    equipment: Optional[str]
    urgency: str
    priority_rank: Optional[int]
    estimated_loss: Optional[float]
    estimated_cost: Optional[float]
    evidence_source_ids: list[str]
    status: str
    cause_status: Optional[str]
    uncertainty_note: Optional[str]


class DecideRequest(BaseModel):
    action_id: int
    decision: str                   # 'approved' | 'rejected' | 'edited'
    manager_name: str
    edited_text: Optional[str] = None
    notes: Optional[str] = None


class DecideResponse(BaseModel):
    action_id: int
    new_status: str
    message: str


@router.get("/{upload_id}/actions", response_model=list[ActionDetail])
def list_actions(upload_id: str, db: Session = Depends(get_db)):
    """List all actions for the given upload, ordered by priority."""
    actions = (
        db.query(Action)
        .join(Action.anomaly)
        .filter(Anomaly.upload_id == upload_id)
        .order_by(Action.priority_rank)
        .all()
    )
    if not actions:
        raise HTTPException(404, f"No actions found for upload_id={upload_id}")

    result = []
    for a in actions:
        import json
        exp = a.anomaly.explanation
        result.append(ActionDetail(
            id=a.id,
            anomaly_id=a.anomaly_id,
            track=a.anomaly.track,
            action_text=a.action_text,
            equipment=a.equipment,
            urgency=a.urgency,
            priority_rank=a.priority_rank,
            estimated_loss=a.estimated_loss,
            estimated_cost=a.estimated_cost,
            evidence_source_ids=json.loads(a.evidence_source_ids) if a.evidence_source_ids else [],
            status=a.status,
            cause_status=exp.cause_status if exp else None,
            uncertainty_note=exp.uncertainty_note if exp else None,
        ))
    return result


@router.post("/decide", response_model=DecideResponse)
def decide_action(req: DecideRequest, db: Session = Depends(get_db)):
    """Manager approves, rejects or edits a recommended action."""
    decision = ReviewDecision(
        action_id=req.action_id,
        decision=req.decision,
        manager_name=req.manager_name,
        edited_text=req.edited_text,
        notes=req.notes,
    )
    try:
        action = apply_review_decision(db, decision)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return DecideResponse(
        action_id=action.id,
        new_status=action.status,
        message=f"Action {action.id} has been {action.status} by {req.manager_name}.",
    )


@router.post("/{upload_id}/briefing")
def generate_briefing(upload_id: str, language: str = "en", db: Session = Depends(get_db)):
    """Generate TTS audio briefing from approved actions only."""
    text = get_approved_actions_text(db, upload_id)

    if "No actions have been approved" in text:
        raise HTTPException(400, "No approved actions to generate briefing from. Approve at least one action first.")

    try:
        tts_result = nc.synthesise_briefing(text, language=language)
    except RuntimeError as e:
        raise HTTPException(502, f"TTS service error: {e}")

    audio_path = AUDIO_DIR / f"{upload_id}_briefing.mp3"
    audio_path.write_bytes(tts_result.audio_bytes)

    return {"message": "Briefing generated.", "audio_url": f"/api/review/{upload_id}/briefing/audio"}


@router.get("/{upload_id}/briefing/audio")
def download_briefing(upload_id: str):
    """Download the generated briefing MP3."""
    audio_path = AUDIO_DIR / f"{upload_id}_briefing.mp3"
    if not audio_path.exists():
        raise HTTPException(404, "Briefing not generated yet. POST to /briefing first.")
    return FileResponse(str(audio_path), media_type="audio/mpeg", filename="shift_briefing.mp3")


@router.get("/{upload_id}/briefing/text")
def get_briefing_text(upload_id: str, db: Session = Depends(get_db)):
    """Get the approved briefing text without generating audio."""
    text = get_approved_actions_text(db, upload_id)
    return {"text": text}

