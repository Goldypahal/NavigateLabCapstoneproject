"""
db/models.py — SQLAlchemy ORM models for ResourceLens.

Tables:
  readings      — raw meter readings (energy kWh or water kL)
  evidence      — extracted evidence (from vision, STT, or typed notes)
  anomalies     — detected anomalies with computed numbers
  explanations  — LLM-generated explanation JSON for each anomaly
  actions       — recommended actions (pending → approved/rejected)
  approvals     — audit log of manager decisions
  token_usage   — every Nexus API call logged
"""

from __future__ import annotations

import datetime
import json
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, Enum as SAEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    track = Column(String(10), nullable=False)              # 'energy' | 'water'
    upload_id = Column(String(64), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    shift = Column(String(20), nullable=True)               # 'day' | 'evening' | 'night'
    weekday = Column(Integer, nullable=True)                 # 0=Mon … 6=Sun

    # Energy fields (kWh per 15-min interval)
    kwh = Column(Float, nullable=True)

    # Water fields (kL per day)
    intake_kl = Column(Float, nullable=True)
    process_kl = Column(Float, nullable=True)
    discharge_kl = Column(Float, nullable=True)
    unaccounted_kl = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(20), unique=True, nullable=False, index=True)
    upload_id = Column(String(64), nullable=False, index=True)
    evidence_type = Column(String(10), nullable=False)      # 'audio' | 'image' | 'text'
    filename = Column(String(256), nullable=True)
    date = Column(DateTime, nullable=True)
    shift = Column(String(20), nullable=True)
    equipment = Column(String(128), nullable=True)

    # For audio: full transcript and segments JSON
    transcript = Column(Text, nullable=True)
    segments_json = Column(Text, nullable=True)             # JSON list of {start,end,text}

    # For image: extracted fields JSON and confidence JSON
    fields_json = Column(Text, nullable=True)
    confidence_json = Column(Text, nullable=True)
    low_confidence_fields = Column(Text, nullable=True)     # JSON list

    # Combined plain text (used for retrieval and quote validation)
    text_content = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    @property
    def fields(self) -> dict:
        return json.loads(self.fields_json) if self.fields_json else {}

    @property
    def segments(self) -> list:
        return json.loads(self.segments_json) if self.segments_json else []


class Anomaly(Base):
    __tablename__ = "anomalies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    anomaly_id = Column(String(64), unique=True, nullable=False, index=True)
    upload_id = Column(String(64), nullable=False, index=True)
    track = Column(String(10), nullable=False)              # 'energy' | 'water'

    timestamp = Column(DateTime, nullable=False)
    shift = Column(String(20), nullable=True)
    weekday = Column(Integer, nullable=True)

    # Computed by code — NEVER by AI
    actual_value = Column(Float, nullable=False)            # kWh or kL
    baseline_value = Column(Float, nullable=False)
    deviation_pct = Column(Float, nullable=False)           # (actual-baseline)/baseline*100
    excess_value = Column(Float, nullable=False)            # actual - baseline
    sigma_deviation = Column(Float, nullable=True)          # how many σ above baseline
    estimated_cost = Column(Float, nullable=True)           # ₹ (stretch)

    # Water-specific
    unaccounted_kl = Column(Float, nullable=True)

    is_flagged = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    explanation = relationship("Explanation", back_populates="anomaly", uselist=False)
    actions = relationship("Action", back_populates="anomaly")


class Explanation(Base):
    __tablename__ = "explanations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    anomaly_id = Column(String(64), ForeignKey("anomalies.anomaly_id"), nullable=False, index=True)
    model_used = Column(String(64), nullable=False)

    # Raw JSON from LLM (validated)
    raw_json = Column(Text, nullable=False)

    likely_cause = Column(Text, nullable=True)
    cause_status = Column(
        SAEnum("supported", "partially_supported", "unknown", "conflicting", name="cause_status_enum"),
        nullable=False,
        default="unknown",
    )
    uncertainty_note = Column(Text, nullable=True)
    missing_information = Column(Text, nullable=True)       # JSON list
    conflicts = Column(Text, nullable=True)                 # JSON list

    # Evidence citations (JSON list of {source_id, type, locator, quote})
    evidence_json = Column(Text, nullable=True)

    # Validation result
    is_valid = Column(Boolean, default=False)
    validation_errors = Column(Text, nullable=True)         # JSON list

    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    anomaly = relationship("Anomaly", back_populates="explanation")


class Action(Base):
    __tablename__ = "actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    anomaly_id = Column(String(64), ForeignKey("anomalies.anomaly_id"), nullable=False, index=True)
    action_text = Column(Text, nullable=False)
    equipment = Column(String(128), nullable=True)
    urgency = Column(String(10), nullable=False, default="medium")  # high | medium | low
    priority_rank = Column(Integer, nullable=True)                   # computed by code
    estimated_loss = Column(Float, nullable=True)                    # kWh or kL (code)
    estimated_cost = Column(Float, nullable=True)                    # ₹ (code, stretch)

    # Evidence backing
    evidence_source_ids = Column(Text, nullable=True)       # JSON list of source_ids

    # Manager review
    status = Column(
        SAEnum("pending", "approved", "rejected", "edited", name="action_status_enum"),
        nullable=False,
        default="pending",
    )
    edited_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    anomaly = relationship("Anomaly", back_populates="actions")
    approval = relationship("Approval", back_populates="action", uselist=False)


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(Integer, ForeignKey("actions.id"), nullable=False, index=True)
    manager_name = Column(String(128), nullable=False)
    decision = Column(String(10), nullable=False)           # 'approved' | 'rejected' | 'edited'
    edited_text = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    decided_at = Column(DateTime, default=datetime.datetime.utcnow)

    action = relationship("Action", back_populates="approval")


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task = Column(String(32), nullable=False)               # 'vision'|'stt'|'explain'|'tts'
    model = Column(String(64), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(Integer, ForeignKey("actions.id"), nullable=False, index=True)
    upload_id_post = Column(String(64), nullable=False)     # post-fix upload
    baseline_avg = Column(Float, nullable=False)
    postfix_avg = Column(Float, nullable=False)
    pct_change = Column(Float, nullable=False)              # (post-baseline)/baseline*100
    value_saved = Column(Float, nullable=True)              # kWh or kL (code)
    cost_saved = Column(Float, nullable=True)               # ₹ (code)
    verified_at = Column(DateTime, default=datetime.datetime.utcnow)

