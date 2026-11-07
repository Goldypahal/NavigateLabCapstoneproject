"""
routes/upload.py — Upload endpoints for CSV, images and audio.

POST /api/upload/csv      — meter readings CSV (energy or water)
POST /api/upload/evidence — image (sheet/nameplate) or audio (voice note)
GET  /api/upload/{upload_id}/status — check processing status
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
import datetime
from pathlib import Path
from typing import Annotated, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import Evidence, Reading
from ingest.csv_validator import validate_energy_csv, validate_water_csv
import nexus_client as nc
from config import settings

router = APIRouter(prefix="/api/upload", tags=["upload"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/mpeg", "audio/mp4", "audio/ogg", "audio/webm"}
MAX_FILE_SIZE = 50 * 1024 * 1024   # 50 MB


class UploadCSVResponse(BaseModel):
    upload_id: str
    track: str
    rows_accepted: int
    warnings: list[str]
    errors: list[str]
    message: str


class UploadEvidenceResponse(BaseModel):
    source_id: str
    upload_id: str
    evidence_type: str
    filename: str
    low_confidence_fields: list[str]
    message: str


def _make_upload_id() -> str:
    return str(uuid.uuid4())


def _next_source_id(db: Session, evidence_type: str) -> str:
    """Generate next VN-xx (audio) or IMG-xx (image) or TXT-xx (text) ID."""
    prefix = {"audio": "VN", "image": "IMG", "text": "TXT"}.get(evidence_type, "EV")
    count = db.query(Evidence).filter(Evidence.evidence_type == evidence_type).count()
    return f"{prefix}-{count + 1:02d}"


@router.post("/csv", response_model=UploadCSVResponse)
async def upload_csv(
    file: UploadFile = File(...),
    track: str = Form(...),     # 'energy' or 'water'
    upload_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload and validate a meter readings CSV."""
    if track not in ("energy", "water"):
        raise HTTPException(400, "track must be 'energy' or 'water'")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 50 MB)")

    # Validate
    if track == "energy":
        result = validate_energy_csv(content)
    else:
        result = validate_water_csv(content)

    if not result.is_valid:
        return UploadCSVResponse(
            upload_id="",
            track=track,
            rows_accepted=0,
            warnings=[],
            errors=result.errors,
            message="CSV rejected due to validation errors.",
        )

    upload_id = upload_id or _make_upload_id()

    # Persist readings to DB
    df = result.df
    for _, row in df.iterrows():
        if track == "energy":
            ts = row["timestamp"]
            reading = Reading(
                track=track,
                upload_id=upload_id,
                timestamp=ts,
                shift=row.get("shift", None),
                weekday=ts.weekday() if hasattr(ts, "weekday") else None,
                kwh=float(row["kwh"]),
            )
        else:
            reading = Reading(
                track=track,
                upload_id=upload_id,
                timestamp=datetime.datetime.combine(row["date"], datetime.time()),
                intake_kl=float(row["intake_kl"]),
                process_kl=float(row["process_kl"]),
                discharge_kl=float(row["discharge_kl"]),
            )
        db.add(reading)

    db.commit()

    return UploadCSVResponse(
        upload_id=upload_id,
        track=track,
        rows_accepted=result.row_count,
        warnings=result.warnings,
        errors=[],
        message=f"CSV accepted: {result.row_count} rows ingested for {track} track.",
    )


@router.post("/evidence", response_model=UploadEvidenceResponse)
async def upload_evidence(
    file: UploadFile = File(...),
    upload_id: str = Form(...),
    date: Optional[str] = Form(None),
    shift: Optional[str] = Form(None),
    equipment: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload an image (inspection sheet/nameplate) or audio (voice note)."""
    content_type = file.content_type or ""
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 50 MB)")

    if content_type in ALLOWED_IMAGE_TYPES:
        evidence_type = "image"
    elif content_type in ALLOWED_AUDIO_TYPES:
        evidence_type = "audio"
    else:
        raise HTTPException(
            400,
            f"Unsupported file type: {content_type}. Upload JPEG/PNG/WebP for images or WAV/MP3/M4A for audio.",
        )

    source_id = _next_source_id(db, evidence_type)

    # Sanitize filename against path traversal attacks (e.g. ../../etc/passwd)
    clean_filename = Path(file.filename or f"evidence_{source_id}").name
    clean_filename = "".join(c for c in clean_filename if c.isalnum() or c in "._- ")
    safe_name = f"{source_id}_{clean_filename}"
    save_path = (UPLOAD_DIR / safe_name).resolve()
    if not str(save_path).startswith(str(UPLOAD_DIR.resolve())):
        raise HTTPException(400, "Invalid filename: path traversal attempt blocked")

    async with aiofiles.open(save_path, "wb") as f:
        await f.write(content)

    # Call Nexus AI
    low_conf_fields: list[str] = []
    transcript = None
    segments_json = None
    fields_json = None
    confidence_json = None
    text_content = ""

    if evidence_type == "image":
        vision_result = nc.extract_sheet_vision(content, task_hint="inspection_sheet")
        fields_json = json.dumps(vision_result.fields)
        confidence_json = json.dumps(vision_result.confidence)
        low_conf_fields = vision_result.low_confidence_fields
        text_content = " ".join(str(v) for v in vision_result.fields.values())

    elif evidence_type == "audio":
        stt_result = nc.transcribe_audio(content)
        transcript = stt_result.transcript
        segments_json = json.dumps(stt_result.segments)
        text_content = stt_result.transcript

    # Parse date
    parsed_date = None
    if date:
        try:
            parsed_date = datetime.datetime.fromisoformat(date)
        except Exception:
            pass

    evidence = Evidence(
        source_id=source_id,
        upload_id=upload_id,
        evidence_type=evidence_type,
        filename=file.filename,
        date=parsed_date,
        shift=shift,
        equipment=equipment,
        transcript=transcript,
        segments_json=segments_json,
        fields_json=fields_json,
        confidence_json=confidence_json,
        low_confidence_fields=json.dumps(low_conf_fields),
        text_content=text_content,
    )
    db.add(evidence)
    db.commit()

    return UploadEvidenceResponse(
        source_id=source_id,
        upload_id=upload_id,
        evidence_type=evidence_type,
        filename=file.filename or "",
        low_confidence_fields=low_conf_fields,
        message=(
            f"{'Image' if evidence_type == 'image' else 'Voice note'} processed as {source_id}."
            + (f" {len(low_conf_fields)} fields need manual review." if low_conf_fields else "")
        ),
    )

