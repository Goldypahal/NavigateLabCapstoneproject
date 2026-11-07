"""
tests/test_review_approval.py — Unit tests for human review and action approval.
Verifies the approval state machine, audit log recording, fallback on edit,
and upload_id filtering for TTS briefing generation.
"""

import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Anomaly, Action, Approval
from review.approval import apply_review_decision, get_approved_actions_text, ReviewDecision


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_upload_with_actions(session, upload_id: str):
    """Seed sample anomaly and actions for an upload_id."""
    anomaly_id = f"A-{upload_id}-1"
    anomaly = Anomaly(
        anomaly_id=anomaly_id,
        upload_id=upload_id,
        track="energy",
        timestamp=datetime.datetime(2026, 10, 15, 22, 0),
        shift="night",
        actual_value=450.0,
        baseline_value=300.0,
        excess_value=150.0,
        deviation_pct=50.0,
        estimated_cost=1350.0,
        is_flagged=True,
    )
    session.add(anomaly)
    session.flush()

    a1 = Action(
        anomaly_id=anomaly.anomaly_id,
        action_text="Inspect air line joints on Compressor 2 for leaks",
        equipment="Compressor 2",
        urgency="high",
        priority_rank=1,
        status="pending",
    )
    a2 = Action(
        anomaly_id=anomaly.anomaly_id,
        action_text="Verify chiller temperature setpoint",
        equipment="Chiller 1",
        urgency="medium",
        priority_rank=2,
        status="pending",
    )
    session.add_all([a1, a2])
    session.commit()
    return anomaly, [a1, a2]


def test_approve_action(db_session):
    """Test approving an action updates status and writes an audit log record."""
    _, actions = _seed_upload_with_actions(db_session, "up-01")
    action_id = actions[0].id

    decision = ReviewDecision(
        action_id=action_id,
        decision="approved",
        manager_name="Jane Doe",
        notes="Confirmed with maintenance lead",
    )

    updated = apply_review_decision(db_session, decision)
    assert updated.status == "approved"

    # Verify audit log in approvals table
    approvals = db_session.query(Approval).filter_by(action_id=action_id).all()
    assert len(approvals) == 1
    assert approvals[0].manager_name == "Jane Doe"
    assert approvals[0].decision == "approved"
    assert approvals[0].notes == "Confirmed with maintenance lead"


def test_reject_action(db_session):
    """Test rejecting an action updates status to rejected."""
    _, actions = _seed_upload_with_actions(db_session, "up-02")
    action_id = actions[1].id

    decision = ReviewDecision(
        action_id=action_id,
        decision="rejected",
        manager_name="John Smith",
        notes="False alarm, scheduled maintenance was running",
    )

    updated = apply_review_decision(db_session, decision)
    assert updated.status == "rejected"

    approvals = db_session.query(Approval).filter_by(action_id=action_id).all()
    assert len(approvals) == 1
    assert approvals[0].decision == "rejected"


def test_edit_action(db_session):
    """Test editing action text updates edited_text and status to edited."""
    _, actions = _seed_upload_with_actions(db_session, "up-03")
    action_id = actions[0].id

    decision = ReviewDecision(
        action_id=action_id,
        decision="edited",
        manager_name="Supervisor Dave",
        edited_text="Replace O-ring seal on Compressor 2 discharge valve immediately",
    )

    updated = apply_review_decision(db_session, decision)
    assert updated.status == "edited"
    assert updated.edited_text == "Replace O-ring seal on Compressor 2 discharge valve immediately"


def test_edit_action_empty_fallback(db_session):
    """Test editing with empty text falls back to original text instead of None."""
    _, actions = _seed_upload_with_actions(db_session, "up-04")
    action_id = actions[0].id
    orig_text = actions[0].action_text

    decision = ReviewDecision(
        action_id=action_id,
        decision="edited",
        manager_name="Supervisor Dave",
        edited_text="   ",  # whitespace only
    )

    updated = apply_review_decision(db_session, decision)
    assert updated.status == "edited"
    assert updated.edited_text == orig_text


def test_invalid_decision_raises(db_session):
    """Invalid decision keyword raises ValueError."""
    _, actions = _seed_upload_with_actions(db_session, "up-05")
    decision = ReviewDecision(
        action_id=actions[0].id,
        decision="delegated",  # invalid
        manager_name="Manager",
    )
    with pytest.raises(ValueError, match="Invalid decision"):
        apply_review_decision(db_session, decision)


def test_approved_actions_text_filtering_and_upload_isolation(db_session):
    """
    Test that briefing text:
    1. Contains ONLY approved and edited actions (no pending or rejected).
    2. Strictly filters by upload_id so actions from other uploads are isolated.
    """
    _, actions_1 = _seed_upload_with_actions(db_session, "upload-AAA")
    _, actions_2 = _seed_upload_with_actions(db_session, "upload-BBB")

    # In upload-AAA: approve action 1, reject action 2
    apply_review_decision(db_session, ReviewDecision(
        action_id=actions_1[0].id,
        decision="approved",
        manager_name="Manager A",
    ))
    apply_review_decision(db_session, ReviewDecision(
        action_id=actions_1[1].id,
        decision="rejected",
        manager_name="Manager A",
    ))

    # In upload-BBB: approve action 1
    apply_review_decision(db_session, ReviewDecision(
        action_id=actions_2[0].id,
        decision="approved",
        manager_name="Manager B",
    ))

    # Briefing for upload-AAA should ONLY contain upload-AAA's approved action
    briefing_aaa = get_approved_actions_text(db_session, "upload-AAA")
    assert "Inspect air line joints on Compressor 2" in briefing_aaa
    assert "Verify chiller" not in briefing_aaa  # rejected

    # Briefing for non-existent or unapproved upload
    briefing_empty = get_approved_actions_text(db_session, "upload-NONEXISTENT")
    assert briefing_empty == "No actions have been approved for this upload."
