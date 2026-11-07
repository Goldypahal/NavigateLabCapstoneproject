"""
ai/explain.py — Evidence retrieval + LLM explanation pipeline.

Steps:
  1. Code-side retrieval: filter evidence to date ±1 day, same shift, relevant equipment.
  2. Call Nexus LLM (via nexus_client) with sanitised anomaly summary + evidence snippets.
  3. Validate the returned JSON: source IDs exist, quotes are real substrings.
  4. Downgrade cause_status to 'unknown' if validation fails.
  5. Return ExplainResult (no numbers from AI — only cause/evidence/uncertainty).
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, ValidationError, field_validator

import nexus_client as nc
from config import settings


# ─── Pydantic schema for LLM output ─────────────────────────────────────────

class EvidenceCitation(BaseModel):
    source_id: str
    type: str                       # 'audio' | 'image' | 'text'
    locator: str                    # e.g. '00:12-00:21' or 'row 4'
    quote: str


class RecommendedAction(BaseModel):
    action: str
    equipment: str
    urgency: str                    # 'high' | 'medium' | 'low'

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        if v not in ("high", "medium", "low"):
            return "medium"
        return v


class ExplainJSON(BaseModel):
    anomaly_id: str
    track: str
    likely_cause: str
    cause_status: str               # supported | partially_supported | unknown | conflicting
    evidence: list[EvidenceCitation]
    missing_information: list[str]
    conflicts: list[str]
    uncertainty_note: str
    recommended_actions: list[RecommendedAction]

    @field_validator("cause_status")
    @classmethod
    def validate_cause_status(cls, v: str) -> str:
        valid = {"supported", "partially_supported", "unknown", "conflicting"}
        return v if v in valid else "unknown"


@dataclass
class ExplainResult:
    anomaly_id: str
    model_used: str
    explain_json: Optional[ExplainJSON]
    is_valid: bool
    validation_errors: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    raw_json: str = ""


# ─── Prompt-injection detection (defence) ───────────────────────────────────

_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|the)\s+(rules?|instructions?|prompt)",
    r"print\s+your\s+system\s+prompt",
    r"reveal\s+your\s+(prompt|instructions)",
    r"turn\s+off\s+compressor",
    r"switch\s+(on|off)\s+\w",
    r"bypass\s+safety",
    r"mark\s+all\s+actions\s+approved",
    r"calculate\s+the\s+savings\s+yourself",
    r"SYSTEM\s*:",
    r"(ignore\s+(all\s+)?data\s+and\s+)?(report|say|state)\s+(that\s+there\s+are\s+)?no\s+anomalies",
]

_INJECTION_RE = re.compile(
    "|".join(_INJECTION_PATTERNS), re.IGNORECASE
)


def _check_injection(text: str) -> bool:
    """Return True if text contains a prompt injection attempt."""
    return bool(_INJECTION_RE.search(text))


def _sanitise_evidence_text(text: str) -> str:
    """
    Wrap evidence text so the LLM treats it as untrusted data.
    Already done in nexus_client but applied again for defence in depth.
    """
    return f"<<<UNTRUSTED_DATA_START>>>{text}<<<UNTRUSTED_DATA_END>>>"


# ─── Evidence retrieval ───────────────────────────────────────────────────────

def retrieve_relevant_evidence(
    evidence_store: list[dict],
    anomaly_date: datetime.date,
    shift: Optional[str],
    equipment: Optional[str] = None,
    window_days: int = 1,
) -> list[dict]:
    """
    Code-side filtering: return only evidence items whose date is within
    ±window_days of the anomaly date and whose shift/equipment match (if set).

    This keeps the LLM prompt small and prevents it seeing unrelated data.
    """
    relevant = []
    for ev in evidence_store:
        ev_date_raw = ev.get("date")
        if ev_date_raw:
            try:
                ev_date = (
                    ev_date_raw
                    if isinstance(ev_date_raw, datetime.date)
                    else datetime.date.fromisoformat(str(ev_date_raw))
                )
                if abs((ev_date - anomaly_date).days) > window_days:
                    continue
            except Exception:
                pass  # if date unparseable, include it (safe to over-include)

        # Shift filter (soft — include if no shift info)
        ev_shift = ev.get("shift", "")
        if shift and ev_shift and ev_shift != shift:
            continue

        # Equipment filter (soft match — ignore if either side doesn't specify equipment)
        ev_equipment = ev.get("equipment", "")
        if equipment and ev_equipment:
            eq_clean = equipment.lower().replace("-", "").replace(" ", "")
            ev_clean = ev_equipment.lower().replace("-", "").replace(" ", "")
            if eq_clean not in ev_clean and ev_clean not in eq_clean:
                continue

        relevant.append(ev)

    return relevant


# ─── Validation & Sanitisation ──────────────────────────────────────────────

NUMBER_REGEX = re.compile(
    r"(₹\s*\d+(?:\.\d+)?|\b\d+(?:\.\d+)?\s*(?:%|₹|kwh|kw|kl|litre|liter|rupees?|inr)(?!\w))",
    re.IGNORECASE,
)


def _sanitize_and_validate_llm_output(
    explain: ExplainJSON,
    evidence_store: list[dict],
    source_id_to_text: dict[str, str],
) -> tuple[ExplainJSON, bool, list[str]]:
    """
    1. Detect and strip numeric quantities from LLM text (Hard Rule 1).
    2. Validate that every source_id exists in the evidence store.
    3. Validate that every quote is a verbatim substring of that source text.
    4. Downgrade cause_status ONLY if evidence citations are invalid.
    """
    errors = []
    valid_ids = set(source_id_to_text.keys())

    # Check and actively strip numbers from AI text (rule: AI does no math)
    num_matches = NUMBER_REGEX.findall(explain.likely_cause + " " + explain.uncertainty_note)
    cleaned_cause = NUMBER_REGEX.sub("[NUMBER_REMOVED_BY_CODE]", explain.likely_cause)
    cleaned_note = NUMBER_REGEX.sub("[NUMBER_REMOVED_BY_CODE]", explain.uncertainty_note)
    if num_matches:
        errors.append(f"AI generated {len(num_matches)} numeric quantities — stripped by code.")

    # Validate citations
    citations_valid = True
    valid_citations = []
    for citation in explain.evidence:
        if citation.source_id not in valid_ids:
            errors.append(f"Citation source_id '{citation.source_id}' not found in evidence store.")
            citations_valid = False
            continue

        source_text = source_id_to_text[citation.source_id]
        if citation.quote and citation.quote.lower() not in source_text.lower():
            errors.append(f"Quote from '{citation.source_id}' is not a verbatim substring of source text.")
            citations_valid = False
            continue

        valid_citations.append(citation)

    # Determine cause status based strictly on evidence validity
    new_cause_status = explain.cause_status
    if not citations_valid or len(valid_citations) < len(explain.evidence):
        if not valid_citations:
            new_cause_status = "unknown"
        else:
            new_cause_status = "partially_supported"

    cleaned_explain = explain.model_copy(update={
        "likely_cause": cleaned_cause,
        "uncertainty_note": cleaned_note,
        "evidence": valid_citations,
        "cause_status": new_cause_status,
    })

    return cleaned_explain, citations_valid, errors


# ─── Main explain pipeline ────────────────────────────────────────────────────

def explain_anomaly_with_evidence(
    anomaly: dict,
    evidence_store: list[dict],
    track: str = "energy",
    model: Optional[str] = None,
) -> ExplainResult:
    """
    Full pipeline:
    1. Filter evidence.
    2. Check for injection in evidence texts.
    3. Call Nexus LLM.
    4. Parse + validate JSON.
    5. Downgrade cause_status if validation fails.
    """
    anomaly_id = anomaly.get("anomaly_id", "unknown")

    # Step 1: Code-side evidence retrieval
    anomaly_date_raw = anomaly.get("timestamp") or anomaly.get("date")
    if anomaly_date_raw:
        if isinstance(anomaly_date_raw, datetime.datetime):
            anomaly_date = anomaly_date_raw.date()
        elif isinstance(anomaly_date_raw, datetime.date):
            anomaly_date = anomaly_date_raw
        else:
            try:
                anomaly_date = datetime.date.fromisoformat(str(anomaly_date_raw)[:10])
            except Exception:
                anomaly_date = datetime.date.today()
    else:
        anomaly_date = datetime.date.today()

    relevant_evidence = retrieve_relevant_evidence(
        evidence_store,
        anomaly_date,
        shift=anomaly.get("shift"),
        equipment=anomaly.get("equipment"),
    )

    # Step 2: Injection scan
    for ev in relevant_evidence:
        text = ev.get("text", "")
        if _check_injection(text):
            ev["injection_detected"] = True
            ev["text"] = "[INJECTION ATTEMPT DETECTED AND REMOVED]"

    # Step 3: Build source_id → text map for validation
    source_id_to_text: dict[str, str] = {}
    snippets_for_llm = []
    for ev in relevant_evidence:
        sid = ev.get("source_id", "")
        text = ev.get("text", "")
        source_id_to_text[sid] = text
        snippets_for_llm.append({
            "source_id": sid,
            "type": ev.get("type", "text"),
            "date": str(ev.get("date", "")),
            "shift": ev.get("shift", ""),
            "text": text,
        })

    # Step 4: Call LLM
    llm_result = nc.explain_anomaly(
        anomaly_summary={
            "anomaly_id": anomaly_id,
            "track": track,
            "timestamp": str(anomaly.get("timestamp") or anomaly.get("date", "")),
            "shift": anomaly.get("shift", ""),
            "description": (
                f"Anomaly detected on {track} track. "
                f"Deviation: {anomaly.get('deviation_pct', 'N/A')}% above baseline."
                if track == "energy"
                else f"Unaccounted water detected. Period: {anomaly.get('days_above_threshold', 1)} days."
            ),
            "equipment_hint": anomaly.get("equipment", ""),
        },
        evidence_snippets=snippets_for_llm,
        model=model,
        track=track,
    )

    # Step 5: Parse JSON
    validation_errors: list[str] = []
    try:
        raw_dict = json.loads(llm_result.content)
        explain_obj = ExplainJSON(**raw_dict)
    except (json.JSONDecodeError, ValidationError) as e:
        # Retry once with a repair prompt if JSON is malformed
        repair_result = _repair_explain(llm_result.content, anomaly_id, track, model)
        if repair_result:
            explain_obj = repair_result
        else:
            return ExplainResult(
                anomaly_id=anomaly_id,
                model_used=llm_result.model,
                explain_json=None,
                is_valid=False,
                validation_errors=[f"JSON parse failure: {e}"],
                raw_json=llm_result.content,
            )

    # Step 6: Sanitize numbers and validate citations
    explain_obj, citations_valid, validation_errors = _sanitize_and_validate_llm_output(
        explain_obj, relevant_evidence, source_id_to_text
    )

    return ExplainResult(
        anomaly_id=anomaly_id,
        model_used=llm_result.model,
        explain_json=explain_obj,
        is_valid=citations_valid,
        validation_errors=validation_errors,
        input_tokens=llm_result.input_tokens,
        output_tokens=llm_result.output_tokens,
        raw_json=llm_result.content,
    )


def _repair_explain(
    bad_json: str,
    anomaly_id: str,
    track: str,
    model: Optional[str],
) -> Optional[ExplainJSON]:
    """One-shot repair attempt using the LLM."""
    repair_prompt = (
        "The following text should be valid JSON matching the ResourceLens explanation schema. "
        "Fix any syntax errors and return ONLY the corrected JSON:\n\n"
        f"{bad_json}"
    )
    try:
        result = nc.explain_anomaly(
            anomaly_summary={"anomaly_id": anomaly_id, "track": track, "description": "repair"},
            evidence_snippets=[{"source_id": "REPAIR", "type": "text", "text": repair_prompt}],
            model=model,
            track=track,
        )
        raw_dict = json.loads(result.content)
        return ExplainJSON(**raw_dict)
    except Exception:
        return None

