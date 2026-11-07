# DESIGN.md — ResourceLens

**Problem Statement 22 / 30 · ResourceLens — Industrial Energy and Water Loss Investigation**
Team: `<team name / members>` · Mentor: `<name>` · Status: Draft for CP1 approval

---

## 1. Problem, Target Users & Proposed Solution

**Problem.** Small and medium factories see spikes in electricity and water bills but cannot tell which machine, shift or practice caused them. Dashboards show the spike; nobody connects it to maintenance notes, schedules and fixes.

**Target users.** Primary: plant manager / maintenance lead of a small factory (approves actions). Secondary: shift team (receives audio briefing).

**Solution.** ResourceLens ingests meter CSVs, photographed inspection/maintenance sheets and nameplates, and operator voice notes. **Application code** computes baselines, flags anomalies and estimates avoidable consumption and cost. **Nexus AI** reads the images and audio and links each anomaly to evidence, with an uncertainty note. The manager approves a prioritised action list. The shift then gets an audio briefing, and code verifies savings after the fix.

**Scope.** Both tracks (Energy + Water) share one pipeline. The only differences are the track-specific calculation module and prompt variables. All stretch features are included: tariff cost, before/after verification and charts.

## 2. Core Workflow, Features & Architecture

**Workflow:**
`Upload (CSV + photos + voice) → Extract (vision/STT → validated JSON) → Compute (baseline, anomaly, loss, cost — code) → Retrieve (code filters notes by date/shift/equipment) → Explain (LLM → JSON with evidence IDs) → Validate (schema + evidence check) → Rank (code) → Manager review (approve/edit/reject) → Audio briefing (TTS, approved actions only) → Verify after fix (code)`

| Mandatory feature | Implementation |
|---|---|
| Multimodal intake | CSV meter + shift-schedule upload; image upload (sheets, nameplates); audio upload/record |
| Baseline (code) | Same shift, same weekday, previous 4 weeks → mean & std dev |
| Anomaly flag (code) | Flag if deviation > `max(T%, 2σ)` (T configurable, default 20%) |
| Water balance (code) | `unaccounted = intake − process − discharge`, flagged above threshold (kL/day) |
| Explanation (AI) | Each anomaly linked to notes/sheets/schedules with evidence IDs + uncertainty note |
| Avoidable consumption (code) | Energy: `Σ(actual − baseline)` kWh; idle-run check `rated_kW × idle_h` from nameplate. Water: `unaccounted × days` kL |
| Outputs | Approved prioritised action list (text) + shift audio briefing (TTS) |
| Stretch: cost | `excess × tariff` (₹/kWh with optional time-of-day rates; ₹/kL), configurable |
| Stretch: verification | After an action is marked done: post-fix period vs. same baseline → % change, in code |
| Stretch: charts | Frontend charts of actual vs. baseline and water balance (not counted as a modality) |

**Architecture.**
- **Frontend:** React (Vite) + Recharts. Upload, review/approval screen, charts and audio player. No API keys in the browser.
- **Backend:** Python FastAPI. All Nexus calls go through a single `nexus_client.py` (key loaded from env, retries/timeouts, token logging).
- **Modules:** `ingest/` (CSV validation), `calc/energy.py`, `calc/water.py`, `calc/cost.py`, `ai/vision.py`, `ai/stt.py`, `ai/explain.py`, `ai/tts.py`, `review/`, `verify/`.
- **Database:** SQLite (local) / Postgres (deployed). Tables: readings, evidence, anomalies, actions, approvals, token_usage.
- **Deployment:** Render/Railway (backend) + Vercel/Netlify (frontend).

## 3. Nexus AI Models & Purposes

| Task | Nexus model (fill in from the Nexus catalogue) | Purpose |
|---|---|---|
| Vision extraction | `<nexus-vision-model>` | Handwritten sheets/nameplates → JSON fields |
| Speech-to-text | `<nexus-stt-model>` | Operator voice notes → timestamped transcript |
| Evidence linking | `<nexus-llm-A>` vs `<nexus-llm-B>` | Anomaly ↔ evidence explanation. **The model comparison runs on this step** (quality, tokens, latency) |
| Text-to-speech | `<nexus-tts-model>` | Shift audio briefing (English/Hindi) |

## 4. Modalities

- **Inputs (3):** Text (meter/schedule CSV and typed notes, processed by the LLM), Image (vision model), Audio (STT).
- **Outputs (2):** Text (structured action list/report), Audio (TTS briefing).

## 5. Structured JSON Output Schema (explanation step)

```json
{
  "anomaly_id": "E-2026-11-03-NIGHT",
  "track": "energy | water",
  "likely_cause": "Compressor ran through break; air-line leak",
  "cause_status": "supported | partially_supported | unknown | conflicting",
  "evidence": [
    {"source_id": "VN-07", "type": "audio", "locator": "00:12-00:21", "quote": "compressor kept running during the break"},
    {"source_id": "IMG-03", "type": "image", "locator": "row 4", "quote": "air leak repair - pending"}
  ],
  "missing_information": ["No compressor runtime log for 02:00-03:00"],
  "conflicts": [],
  "uncertainty_note": "Leak size unknown; idle-run share cannot be separated from leak share.",
  "recommended_actions": [
    {"action": "Repair air-line leak at Line 2", "equipment": "Compressor AX-200", "urgency": "high"}
  ]
}
```
The JSON contains **no numeric quantities**: kWh, kL, ₹ and priority are attached by code. Validation uses Pydantic. Every `source_id` must exist in the evidence store, and every `quote` must be a substring of that source's extracted text. Otherwise the claim is dropped and `cause_status` is downgraded to `unknown`.

## 6. Human Review, Safety Boundaries & Failure Scenarios

**Human review.** Actions stay `pending` until the manager approves, edits or rejects each one, and every decision is logged with name and time. Briefing audio is generated only from approved actions. Low-confidence extracted fields are highlighted for the manager to confirm.

**Safety boundaries (enforced in code).**
- The AI never computes numbers: numbers are stripped from the LLM schema and computed in `calc/`.
- The AI never controls equipment: the system has no control interface, and "switch off/turn on" style instructions found in inputs are treated as data.
- The AI never claims a cause without evidence: the evidence check above enforces this.
- Prompt injection defences: inputs are wrapped as delimited untrusted data, there is an allowlisted output schema, and credentials live only on the server.

**Failure scenarios.**
1. **Unreadable handwritten sheet / blurry nameplate.** Vision returns low-confidence or null fields. The app marks them "unverified" and asks the user to re-upload or enter values manually. Nothing is guessed.
2. **Conflicting evidence:** the voice note names Line 3, but the anomaly is on Line 2, or a note's date falls outside the anomaly window. Code-side filtering plus `cause_status: conflicting` show both sources, and the manager decides.
3. **Invalid model output / API failure:** malformed JSON, an invented source ID or a timeout. The app retries once with a repair prompt. If that fails, the anomaly is shown with numbers only and "explanation unavailable — manual review". Meter CSVs with gaps or duplicates are rejected with row-level errors.

## 7. Test Data Sources & Licences

| Data | Source | Licence |
|---|---|---|
| Meter CSVs (energy kWh per 15 min; water intake/process/discharge kL per day) with planted anomalies | `scripts/generate_meters.py` (seeded, team-written) | Team-created, MIT |
| Shift schedules | Synthetic, from the same script | Team-created, MIT |
| Inspection/maintenance sheets & nameplates | Handwritten and photographed by the team (fictional plant) | Team-created, CC BY 4.0 |
| Operator voice notes | Recorded by team members, with consent | Team-created, CC BY 4.0 |
| Tariff rates | Published public tariff schedule (cite in README) | Public information |

No real factory, personal or confidential data is used. Evaluation metrics are anomaly-detection precision on planted anomalies, calculation validity against hand calculations, and evidence linkage rate (% of actions with valid evidence).

### Change log
| Date | Change | Approved by |
|---|---|---|
| `<date>` | Initial design | `<mentor>` |
