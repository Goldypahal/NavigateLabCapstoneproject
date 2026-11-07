# ResourceLens — Industrial Energy & Water Loss Investigator

**Problem Statement 22** · Navigate Labs Capstone · Team: `<team name>`

> ResourceLens helps plant managers find unusual electricity or water use and explains the likely cause by linking meter data to what workers saw and wrote down.

---

## Live Demo

| Component | URL |
|---|---|
| Frontend | `<Vercel/Netlify URL>` |
| Backend API | `<Render/Railway URL>` |
| API Docs | `<backend URL>/docs` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Inputs (3 modalities)                                       │
│  ┌──────────┐  ┌─────────────┐  ┌──────────────────────┐  │
│  │ CSV      │  │ Image       │  │ Audio (voice note)   │  │
│  │ (meter   │  │ (sheets,    │  │ → Nexus STT          │  │
│  │  data)   │  │  nameplates)│  │   → transcript+ts    │  │
│  └────┬─────┘  │ → Nexus     │  └──────────┬───────────┘  │
│       │        │   Vision    │             │               │
│       │        │   → JSON    │             │               │
│       └────────┴─────────────┴─────────────┘               │
│                        │                                     │
│         [Code] Validate · Baseline · Anomaly · Cost         │
│                        │                                     │
│         [Code] Filter evidence by date/shift/equipment      │
│                        │                                     │
│         [Nexus LLM] Link anomaly ↔ evidence → JSON          │
│         (cause, source citations, uncertainty note)         │
│                        │                                     │
│         [Code] Validate citations · Rank actions            │
│                        │                                     │
│         Manager reviews / approves / edits / rejects        │
│                        │                                     │
│  Outputs (2 modalities)                                     │
│  ┌──────────────────────┐  ┌──────────────────────────────┐ │
│  │ Prioritised action   │  │ Audio briefing               │ │
│  │ list (text)          │  │ → Nexus TTS → MP3            │ │
│  └──────────────────────┘  └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Module → Concept Mapping

| Module | Concept | Key file |
|---|---|---|
| `ingest/csv_validator.py` | Input validation, error messages | [csv_validator.py](backend/ingest/csv_validator.py) |
| `calc/energy.py` | Baseline (4-week same-shift avg), anomaly flag (>20% or >2σ) | [energy.py](backend/calc/energy.py) |
| `calc/water.py` | Water balance = intake − process − discharge | [water.py](backend/calc/water.py) |
| `calc/cost.py` | Cost = excess × tariff (ToD-aware); action ranking | [cost.py](backend/calc/cost.py) |
| `nexus_client.py` | All Nexus API calls; token logging; file-hash cache | [nexus_client.py](backend/nexus_client.py) |
| `ai/explain.py` | Evidence retrieval, injection scan, LLM call, citation validation | [explain.py](backend/ai/explain.py) |
| `review/approval.py` | Human review; audit log; approved-only TTS input | [approval.py](backend/review/approval.py) |
| `verify/postfix.py` | Before/after comparison; % change; ₹ saved | [postfix.py](backend/verify/postfix.py) |
| `scripts/generate_meters.py` | Synthetic data with planted anomalies + answer key | [generate_meters.py](scripts/generate_meters.py) |
| `eval/run_eval.py` | 15-case evaluation; precision, recall, linkage metrics | [run_eval.py](eval/run_eval.py) |

---

## Nexus Models Used

| Task | Model | Modality |
|---|---|---|
| Vision extraction | `nexus-vision-latest` | Image → Text |
| Speech-to-text | `nexus-stt-latest` | Audio → Text |
| Anomaly explanation (A/B) | `nexus-llm-pro` / `nexus-llm-fast` | Text → Structured JSON |
| Text-to-speech | `nexus-tts-latest` | Text → Audio |

---

## Setup

### Backend

```bash
cd backend
cp ../.env.example .env
# Edit .env — set NEXUS_API_KEY, NEXUS_BASE_URL, model names
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

### Generate Test Data

```bash
cd scripts
python generate_meters.py --seed 42 --weeks 8 --out-dir ../data
```

### Run Evaluation

```bash
# Start the backend first (uvicorn main:app)
python eval/run_eval.py --api http://localhost:8000
```

---

## Safety Boundaries (Hard Rules)

| Rule | Enforcement |
|---|---|
| AI never computes numbers | Numbers stripped from LLM schema; `number_pattern` regex validator |
| AI never controls equipment | No control interface exists; equipment commands in input ignored |
| AI never claims without evidence | Citation validator; `cause_status=unknown` if no valid citations |
| Prompt injection defence | Inputs wrapped as `<<<UNTRUSTED_DATA>>>`, allowlisted JSON output schema |
| Actions require human approval | All actions start `pending`; audio generated only from approved actions |

---

## Evaluation Metrics

| Metric | Formula | Target |
|---|---|---|
| Anomaly precision | planted found / total flagged | ≥ 80% |
| Anomaly recall | planted found / planted total | ≥ 80% |
| Evidence-linkage rate | actions with valid citation / total actions | ≥ 70% |
| Calculation validity | manual check vs code output | 100% |

---

## Screenshots

`<add screenshots here>`

---

## Limitations

- Baseline requires at least 2 weeks of historical data for the same shift + weekday.
- Vision model accuracy depends on image quality; blurry photos trigger manual review.
- TTS available in English and Hindi (via `language` param); other languages untested.
- Water balance assumes no internal recycling loops (extend `calc/water.py` for those).

---

## Licences

- Application code: MIT
- Synthetic data: MIT
- Handwritten sheets / voice notes: CC BY 4.0 (team-created)
- Tariff rates: public domain (source: `<cite your state tariff schedule>`)

---

## Links

- LinkedIn post: `<URL>`
- Demo video: `<URL>`
- Deployed app: `<URL>`

