"""
review/approval.py — Human review and action approval logic.

Actions stay 'pending' until the manager explicitly approves, edits or rejects.
Every decision is written to the approvals audit log with manager name and timestamp.
TTS briefing is only generated from approved actions.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from db.models import Action, Approval


@dataclass
class ReviewDecision:
    action_id: int
    decision: str                   # 'approved' | 'rejected' | 'edited'
    manager_name: str
    edited_text: Optional[str] = None
    notes: Optional[str] = None


def apply_review_decision(db: Session, decision: ReviewDecision) -> Action:
    """
    Apply a manager's decision to an action.
    Logs the decision in the approvals table.
    Returns the updated Action.
    """
    action = db.get(Action, decision.action_id)
    if not action:
        raise ValueError(f"Action {decision.action_id} not found.")

    if decision.decision not in ("approved", "rejected", "edited"):
        raise ValueError(f"Invalid decision: {decision.decision}")

    action.status = decision.decision
    if decision.decision == "edited" and decision.edited_text:
        action.edited_text = decision.edited_text
        action.status = "edited"

    approval = Approval(
        action_id=action.id,
        manager_name=decision.manager_name,
        decision=decision.decision,
        edited_text=decision.edited_text,
        notes=decision.notes,
        decided_at=datetime.datetime.utcnow(),
    )
    db.add(approval)
    db.commit()
    db.refresh(action)
    return action


def get_approved_actions_text(db: Session, upload_id: str) -> str:
    """
    Build the briefing text from approved/edited actions only.
    Used as input to TTS. Never includes pending or rejected actions.
    """
    actions = (
        db.query(Action)
        .join(Action.anomaly)
        .filter(
            Action.status.in_(["approved", "edited"]),
        )
        .order_by(Action.priority_rank)
        .all()
    )

    if not actions:
        return "No actions have been approved for this upload."

    lines = ["ResourceLens Shift Briefing. The following actions have been approved by the plant manager.", ""]
    for i, action in enumerate(actions, start=1):
        text = action.edited_text if action.status == "edited" else action.action_text
        urgency = action.urgency.upper()
        lines.append(f"Action {i} — Priority {urgency}: {text}")
        if action.equipment:
            lines.append(f"  Equipment: {action.equipment}.")
        lines.append("")

    lines.append("Please complete all HIGH priority actions before the end of this shift. Stay safe.")
    return "\n".join(lines)

