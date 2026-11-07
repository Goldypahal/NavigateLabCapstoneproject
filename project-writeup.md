# ResourceLens — Industrial Energy and Water Loss Investigation
### Capstone Executive Summary · Problem Statement 22

**Team:** ResourceLens Engineering Team  
**Domain:** Industrial IoT, Multimodal AI, Resource Conservation, Factory Operations  

---

### 1. Executive Summary & Problem Formulation
Small and medium industrial manufacturing plants frequently encounter sudden 15% to 35% spikes in utility bills. While smart sub-meters capture continuous consumption, facilities lack the engineering bandwidth to correlate electrical spikes or water imbalances with physical reality: maintenance sheets, pending repair orders, shift transitions, or machine operating habits.

ResourceLens solves this problem by acting as an autonomous industrial investigator. It ingests 15-minute electrical telemetry or daily water balance records, photographs of handwritten inspection logs and equipment nameplates, and operator voice notes recorded on the shop floor. It correlates meter anomalies with human observations to diagnose root causes and recommend actionable, human-reviewed maintenance tasks.

---

### 2. Architecture & Design Principles
ResourceLens is governed by three strict architectural mandates:
1. **Separation of Determinism and Heuristics:** The AI never performs arithmetic. Baseline calculation (same-shift, same-weekday rolling 4-week mean $\mu$ and standard deviation $\sigma$), anomaly thresholding ($\max(T\%, 2\sigma)$), volumetric water balance ($\text{Intake} - \text{Process} - \text{Discharge}$), and financial tariffs are executed purely in Python.
2. **Multimodal Evidence Grounding:** Nexus Vision digitizes inspection logs with per-field confidence scoring; Nexus STT transcribes operator audio into timestamped segments. Nexus LLM links anomalies to cited evidence (`VN-xx`, `IMG-xx`). Every citation is verified via substring matching in application code before presentation. If evidence is lacking, the system strictly reports `"cause unknown"`.
3. **Mandatory Human-in-the-Loop Review:** The AI never controls physical equipment. Recommended work orders remain in a `pending` state until the plant manager approves, edits, or rejects them. The secondary output—a synthesized audio briefing for the incoming shift team generated via Nexus TTS—is produced exclusively from manager-approved actions.

---

### 3. Comprehensive Feature Scope (Energy + Water Tracks)
- **Both Tracks Fully Realized:**
  - *Energy Track:* Ingests 15-minute interval kWh readings, maps to 3 daily shifts (Day, Evening, Night), flags compressor overruns, weekend idle runs, and equipment degradation drift.
  - *Water Track:* Solves daily water balances, detects cooling tower leaks ($+18\text{ kL/day}$), and flags impossible metering discrepancies ($\text{Discharge} > \text{Intake}$).
- **Stretch Capabilities Delivered:**
  - *Time-of-Day (ToD) Tariff Engine:* Applies differential peak (₹9.0/kWh) and off-peak (₹7.5/kWh) rates for energy, and ₹45.0/kL for water.
  - *Post-Fix Verification Engine:* Ingests post-repair meter files to measure actual percentage drop against baseline and compute verified cost savings.
  - *Rich Analytics UI:* Recharts time-series bands with anomaly highlights and water volume bar graphs.

---

### 4. Verification, Testing & Robustness
- **Unit & Hand-Calculation Verification:** 52 comprehensive unit tests (`backend/tests/`) confirm 100% mathematical validity of energy baselines, water equations, tariff calculations, validation logic, review state machine, and post-fix verification against manual hand-calculations.
- **Evaluation Benchmark:** 15 test cases spanning normal runs, missing evidence, conflicting reports, degraded captures, and adversarial prompt injections (Categories A–F) achieving 15/15 PASS (100.0%).
- **Engineering Transparency:** 5 documented development mistakes logged in `AI_USAGE.md` detailing root cause discovery, code fixes, and regression prevention.

