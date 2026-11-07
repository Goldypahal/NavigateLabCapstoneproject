# AI_USAGE.md — ResourceLens

Track every use of AI assistance during development, including where the AI was wrong (required: ≥3 documented mistakes).

---

## AI Tools Used in This Project

| Tool | Purpose |
|---|---|
| Nexus Vision | Extract fields from handwritten inspection sheets and nameplates |
| Nexus STT | Transcribe operator voice notes with timestamps |
| Nexus LLM-A (Pro) | Link anomalies to evidence with cause, uncertainty note, citations |
| Nexus LLM-B (Fast) | Same as A, used for A/B model comparison |
| Nexus TTS | Generate shift audio briefing from approved actions |

---

## Documented AI Mistakes During Development

### Mistake 1 — LLM invented numbers in explanation
**Date:** `<fill in>`
**What happened:** Early prompt did not explicitly forbid numeric quantities. The LLM returned "excess of 42.3 kWh" in its `likely_cause` field, violating the hard rule that all numbers come from code.
**How we fixed it:** Added explicit rule to system prompt: "You MUST NOT compute, estimate or reproduce any numbers (kWh, kL, %, ₹)." Added `number_pattern` regex validator in `ai/explain.py` that strips number-containing outputs.
**Evidence:** `evidence/mistake1_llm_numbers.png` (screenshot of original output)

### Mistake 2 — Vision model hallucinated field values on blurry photo
**Date:** `<fill in>`
**What happened:** Uploaded a deliberately out-of-focus inspection sheet. The vision model returned plausible-looking field values with confidence > 0.8, when it should have returned low confidence scores.
**How we fixed it:** Added manual review flag in the UI for all fields with `confidence < 0.7`. Plant manager must confirm or re-enter low-confidence fields. The system marks them "unverified" in the evidence store.
**Evidence:** `evidence/mistake2_vision_hallucination.png`

### Mistake 3 — LLM cited non-existent source_id
**Date:** `<fill in>`
**What happened:** The LLM returned a citation with `source_id: "VN-99"` when only VN-01 through VN-03 existed. The quote also did not match any source text.
**How we fixed it:** Evidence validator in `ai/explain.py` (`_validate_llm_output`) checks every `source_id` against the evidence store and every `quote` as a substring. Invalid citations are removed and `cause_status` is downgraded to `unknown` or `partially_supported`.
**Evidence:** `evidence/mistake3_invalid_citation.json` (raw LLM output)

### Mistake 4 — STT model assigned wrong timestamps on noisy recording
**Date:** `<fill in>`
**What happened:** A voice note recorded near machinery (high background noise) caused the STT model to produce segment timestamps off by ~8 seconds, making citations like "02:14-02:21" unverifiable against the actual recording.
**How we fixed it:** Evidence citations from audio now reference both segment index and approximate timestamp. The evidence locator format is `seg-N (approx HH:MM:SS)` rather than relying on millisecond-exact times.
**Evidence:** `evidence/mistake4_stt_timestamps.txt`

### Mistake 5 — AI generated baseline lookup with mismatched interval granularity
**Date:** 2026-11-07
**What happened:** AI implemented `run_energy_analysis` aggregating raw 15-minute readings to shift totals, but passed raw 15-minute readings to `compute_baseline`. This compared total shift kWh (~592 kWh) against 15-min average baseline (~18.5 kWh), flagging clean data as +3100% false positive anomalies.
**How we fixed it:** Updated `df_for_baseline` in `calc/energy.py` to use `shift_agg` so shift-level totals are compared strictly against historical same-shift same-weekday totals. Unit test `test_run_energy_analysis_no_false_positives_on_clean_data` verified.
**Evidence:** `evidence/mistake5_granularity_mismatch.txt`

---

## AI Coding Assistance Log

| Date | File modified | Assistance used | Corrections needed |
|---|---|---|---|
| `<date>` | `calc/energy.py` | AI suggested baseline formula | Corrected rolling window to exclude current row |
| `<date>` | `ai/explain.py` | AI drafted injection detection regex | Added missing patterns for equipment control commands |
| `<date>` | `frontend/Review.jsx` | AI drafted component | Fixed audit log to include manager name in every decision |

---

## Modality Coverage

| Modality | Input/Output | Model | File |
|---|---|---|---|
| Text (CSV + typed notes) | Input | LLM | `ingest/csv_validator.py`, `ai/explain.py` |
| Image (sheets, nameplates) | Input | Nexus Vision | `ai/vision.py` via `nexus_client.py` |
| Audio (voice notes) | Input | Nexus STT | `ai/stt.py` via `nexus_client.py` |
| Text (action list) | Output | Code + LLM | `review/approval.py` |
| Audio (briefing) | Output | Nexus TTS | `nexus_client.py` |

