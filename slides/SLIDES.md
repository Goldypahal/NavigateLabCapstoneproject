# ResourceLens — 7-Slide Capstone Presentation Deck
**Problem Statement 22: ResourceLens — Industrial Energy and Water Loss Investigation**

---

## Slide 1: Problem & Target Users
### The Industrial Blind Spot in SME Factories
- **The Challenge:** Small and medium factories suffer unexpected 15%–35% surges in electricity and water bills. Existing dashboards show a spike, but cannot answer *why* it happened or *who* noticed it.
- **The Disconnect:** Shift logbooks, handwritten inspection sheets, and operator voice notes remain unlinked from smart meter data.
- **Target Users:**
  - *Primary:* Plant Manager / Maintenance Lead (reviews anomalies, approves actionable work orders).
  - *Secondary:* Shift Team / Floor Technicians (receives synthesized audio briefing before each shift).
- **Core Value Proposition:** ResourceLens bridges raw telemetry and worker observations into verified, prioritized loss investigations with human-in-the-loop sign-off.

---

## Slide 2: End-to-End System Architecture
### Strict Separation: Deterministic Code vs. Probabilistic AI
- **Multimodal Inputs (3 Modalities):**
  1. *Meter Telemetry (Text/CSV):* 15-min kWh intervals or daily water balance (intake, process, discharge).
  2. *Inspection Sheets & Nameplates (Image):* Nexus Vision OCR with per-field confidence scoring.
  3. *Operator Voice Notes (Audio):* Nexus Speech-to-Text producing timestamped transcript segments.
- **Multimodal Outputs (2 Modalities):**
  1. *Prioritized Action List (Text):* Ranked strictly by code-computed financial and volumetric loss.
  2. *Shift Audio Briefing (Audio):* Nexus Text-to-Speech synthesized **only** from manager-approved actions.
- **Architectural Flow:**
  `CSV/Images/Audio -> Code Validation -> Pure-Code Baseline Engine -> Nexus Evidence Retrieval & Linkage -> LLM Structured Schema (No Numbers) -> Human Approval -> Nexus TTS -> Verification Engine`

---

## Slide 3: Deterministic Baseline & Anomaly Math
### "The AI Does None of This Math"
- **Energy Track Formulation:**
  - *Baseline:* Historical mean $\mu$ and standard deviation $\sigma$ across the same shift and same weekday over the prior 4 weeks ($N=4$).
  - *Anomaly Trigger:* $\text{Deviation} > \max(T\%, 2\sigma)$ (configurable threshold $T$, default 20%).
  - *Avoidable Consumption:* $\text{Excess kWh} = \sum (\text{Actual} - \text{Baseline})$.
  - *Idle Run Detection:* Nameplate rated $\text{kW} \times \text{idle hours}$ (pure code).
- **Water Balance Track Formulation:**
  - *Balance Equation:* $\text{Unaccounted} = \text{Intake} - \text{Process Use} - \text{Discharge}$.
  - *Threshold Trigger:* Flagged if $\text{Unaccounted} > 5.0\text{ kL/day}$.
  - *Total Loss Volume:* $\text{Excess kL} = (\text{Unaccounted} - \text{Baseline Loss}) \times \text{Days}$.
  - *Metering Conflict Detection:* Automatically flags physically impossible discrepancies ($\text{Discharge} > \text{Intake}$).

---

## Slide 4: Multimodal Evidence Linkage & Safety Guardrails
### Grounded Attribution with Zero Hallucinated Numbers
- **Code-Side Retrieval:**
  - LLM only receives evidence filtered by date ($\pm 1$ day), matching shift, and target equipment.
- **Strict Evidence Citation Validation:**
  - Every `source_id` (e.g., `VN-01`, `IMG-03`) is validated against the active evidence store.
  - Every citation quote must be a verbatim substring in the source transcript or OCR text.
  - Failure downgrades the cause to `"unknown"`.
- **Hard Safety Guardrails (Enforced in Code):**
  - *No Number Hallucination:* LLM schema omits all numbers; regex validation strips any generated digits.
  - *Zero Equipment Control:* The system has no machine execution interface; equipment shutdown commands found in inputs are quarantined as untrusted data.
  - *No Speculation:* If no evidence exists, the system strictly outputs `"cause unknown"`.

---

## Slide 5: Human Review & Audio Briefing
### Closing the Human-in-the-Loop Loop
- **Manager Approval Dashboard:**
  - All recommendations default to `pending`.
  - Plant manager can **Approve**, **Edit** action text, or **Reject** with rationale.
  - Full audit logging: manager identity, timestamp, decision, and edits committed to DB.
- **Shift Audio Briefing (Nexus TTS):**
  - **Constraint:** TTS briefing cannot be generated until at least one action is approved.
  - Synthesizes clear, equipment-specific guidance directly for floor workers.
  - Available in English and Hindi for multilingual shop floors.

---

## Slide 6: Verification, Financial Impact & Visual Analytics
### Stretch Goals Delivered
- **Tariff & Cost Estimation (Code-Calculated):**
  - Time-of-Day (ToD) tariff aware: Peak rate (₹9.0/kWh, 09:00–23:00) vs. Off-peak (₹7.5/kWh).
  - Water tariff: ₹45.0/kL.
- **Post-Fix Verification Engine:**
  - Manager marks an action completed $\to$ uploads new post-fix meter CSV.
  - Compares post-fix performance against original 4-week baseline.
  - Reports verified percentage reduction and total financial savings realized.
- **Interactive Visualizations:**
  - Recharts actual vs. baseline band with color-coded anomaly markers.
  - Water balance breakdown charts illustrating unaccounted volume vs. threshold.

---

## Slide 7: Evaluation, Prompt Injection & AI Learning Log
### Rigorous Testing & Continuous Improvement
- **Evaluation Suite (15 Test Cases across 7 Categories):**
  - Normal (Energy & Water), Missing Evidence, Conflicting Notes, Blurry Image, Noisy Audio, Malformed CSV, Adversarial Injections.
  - *Results:* 100% calculation validity, $\ge 85\%$ anomaly precision on planted datasets.
- **Prompt Injection Defense Matrix (Categories A–F):**
  - Tested 10 injection vectors (jailbreak, system prompt extraction, CSV payload, equipment shutdown commands).
  - Sanitization with `<<<UNTRUSTED_DATA>>>` delimiters and strict Pydantic parsing prevented all circumventions.
- **Documented AI Mistakes (5 Logged in `AI_USAGE.md`):**
  - Numeric hallucinations in early prompts $\to$ Regex validator & schema lockdown.
  - Blurry OCR hallucinations $\to$ Confidence thresholding & manager confirmation.
  - Timestamp drift on noisy audio $\to$ Segment index relative locators.
  - Interval granularity mismatch $\to$ Shift aggregation alignment in baseline lookups.

