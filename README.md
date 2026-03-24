# Propy Bad Deed Validator
### Hybrid AI + Deterministic Real Estate Deed Validation

<p align="center">
  <img src="https://img.shields.io/badge/LLM-Groq_Llama_3.3_70B-red?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Fuzzy_Match-RapidFuzz-blue?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Validation-Deterministic_Code-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/API-FastAPI-teal?style=for-the-badge&logo=fastapi" />
  <img src="https://img.shields.io/badge/Schema-Pydantic_v2-purple?style=for-the-badge" />
</p>

---

> **The core principle: AI extracts. Code validates. Never the other way around.**

---

## The Problem

At Propy, deeds are scanned via OCR and recorded on blockchain. One undetected error — a wrong date, a mismatched dollar amount — means a fraudulent transaction is permanently recorded. There is no undo.

The challenge: OCR output is messy. Dates can be out of order. Dollar amounts in digits can contradict the written-out words. County names can be abbreviated or misspelled. A naive LLM-only approach will silently accept these errors or hallucinate corrections. Neither is acceptable.

---

## The Solution: Paranoid Engineering

```
┌─────────────────────────────────────────────────────────────┐
│                    Raw OCR Deed Text                        │
│  (messy, abbreviated, potentially fraudulent)               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1 — LLM EXTRACTION (Groq Llama 3.3 70B)               │
│                                                             │
│  Job: read messy text → fill structured form                │
│  Does NOT validate. Does NOT fix errors.                    │
│  Extracts exactly what is written, nothing more.            │
│                                                             │
│  Output: ExtractedDeed (Pydantic validated)                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2 — FUZZY COUNTY MATCHING (RapidFuzz)                 │
│                                                             │
│  "S. Clara" → "Santa Clara" (85.7% confidence)             │
│  "SAN MATEO" → "San Mateo"  (100% confidence)              │
│  "Transylvania" → REJECTED  (52% < 60% threshold)          │
│                                                             │
│  Deterministic. Reproducible. Zero API cost.                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3 — DETERMINISTIC VALIDATION (Pure Python)            │
│                                                             │
│  Date check  : recorded >= signed? (simple inequality)      │
│  Money check : digits == words? (custom number parser)      │
│                                                             │
│  100% reliable. 100% auditable. Zero nondeterminism.        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4 — CLOSING COSTS (only if no CRITICAL errors)        │
│                                                             │
│  closing_costs = sale_amount × county_tax_rate              │
│  Skipped entirely if deed has unresolved errors.            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  DeedValidationResult                                       │
│  {is_valid, errors[], warnings[], closing_costs, summary}   │
└─────────────────────────────────────────────────────────────┘
```

---

## Why This Architecture?

### Why Not Just Use the LLM for Everything?

This is the trap. Here's what happens when you ask an LLM to validate:

```
Prompt: "Is this deed valid? Date Signed: Jan 15, Date Recorded: Jan 10"

GPT-4: "Yes, the deed appears to be in order. The recording date
        of January 10th precedes the signing date of January 15th,
        which may indicate pre-recording for expedited processing..."
```

The LLM rationalizes the error instead of catching it. It's probabilistic — on a good day it catches the issue, on a bad day it doesn't. For a blockchain transaction, "usually catches it" is not good enough.

**Our approach:** the date check is 3 lines of Python. It is always right.

```python
if date_recorded < date_signed:
    raise ValidationError("RECORDING_BEFORE_SIGNING", severity="CRITICAL")
```

### Why RapidFuzz for County Matching?

County names in OCR documents come in every possible form:

| OCR Output | Database Name | Challenge |
|---|---|---|
| `S. Clara` | `Santa Clara` | Abbreviation |
| `SAN MATEO` | `San Mateo` | Case difference |
| `Santa Cruz Cty` | `Santa Cruz` | Extra word |
| `santa clara` | `Santa Clara` | Lowercase |

Exact string matching fails all four. An LLM would work but costs tokens and introduces nondeterminism. RapidFuzz handles all four cases with a confidence score — and we reject anything below 60% rather than guessing.

### Why a Custom Number Parser Instead of word2number?

The `word2number` library has a known bug with compound numbers:

```
word2number("Two Hundred Thousand") = 201,000  ← WRONG
our parser("Two Hundred Thousand")  = 200,000  ← CORRECT
```

In a deed validator where we're catching $50K discrepancies, a buggy number parser is unacceptable. We wrote a custom recursive parser that correctly handles all real estate amount patterns.

---

## File Structure & Logic

```
propy-deed-validator/
├── models.py          # Pydantic schemas — typed contracts between all layers
├── llm_extractor.py   # LLM extraction ONLY — reads messy text, fills form
├── county_matcher.py  # RapidFuzz matching — "S. Clara" → "Santa Clara"
├── validators.py      # Deterministic checks — date logic + money check
├── deed_processor.py  # Orchestrator — calls all 4 steps in order
├── api.py             # FastAPI — exposes /validate and /validate/demo
├── main.py            # CLI runner — python main.py or python main.py --api
├── counties.json      # Reference data — county names + tax rates
├── requirements.txt
└── .env.example
```

### `models.py` — The Typed Contract
Pydantic schemas for every data structure in the pipeline. `ExtractedDeed` defines what the LLM must return. `DeedValidationResult` defines what the API returns. If the LLM produces a malformed response — wrong type, missing field — Pydantic catches it immediately before bad data propagates.

### `llm_extractor.py` — AI Layer (Read Only)
Calls Groq (Llama 3.3 70B, free) with `temperature=0.0` for deterministic extraction. The system prompt explicitly instructs the model: "Do NOT fix errors — if dates look wrong, extract them anyway." This is critical — we want the raw data, not an LLM-corrected version. Uses structured JSON output validated immediately by Pydantic.

### `county_matcher.py` — Fuzzy Matching
Two-method approach: `token_sort_ratio` handles word order differences, `partial_ratio` handles abbreviations. Both sides normalized to lowercase before comparison — eliminates all case-sensitivity failures. Takes the higher-scoring method. Rejects below 60% confidence. Returns matched county name with tax rate.

### `validators.py` — The Core Logic
Two deterministic checks:

**Date validator:** Parses both dates with `datetime.strptime`, compares directly. If `date_recorded < date_signed` → CRITICAL error. Also checks for future dates.

**Money validator:** Custom word-to-number parser converts "One Million Two Hundred Thousand" → 1,200,000. Compares against numeric field with 0.1% tolerance for rounding. Discrepancy → WARNING (not CRITICAL, because we don't know which value is authoritative).

### `deed_processor.py` — The Orchestrator
Calls each step in sequence. Closing costs are deliberately skipped if any CRITICAL error exists — you don't calculate financial obligations on a legally invalid document.

### `api.py` — FastAPI Endpoint
Two routes: `POST /validate` accepts any deed text, `GET /validate/demo` runs the exact task input. Full Swagger docs at `/docs`. Returns structured JSON with all fields, errors, warnings, and summary.

---

## Live Demo — Task Input

**Input (exact OCR text from the task):**
```
*** RECORDING REQ ***
Doc: DEED-TRUST-0042
County: S. Clara | State: CA
Date Signed: 2024-01-15
Date Recorded: 2024-01-10
Grantor: T.E.S.L.A. Holdings LLC
Grantee: John & Sarah Connor
Amount: $1,250,000.00 (One Million Two Hundred Thousand Dollars)
APN: 992-001-XA
Status: PRELIMINARY
*** END ***
```

**Output:**
```json
{
  "doc_id": "DEED-TRUST-0042",
  "is_valid": false,
  "grantor": "T.E.S.L.A. Holdings LLC",
  "grantee": "John & Sarah Connor",
  "amount_numeric": 1250000.0,
  "county_raw": "S. Clara",
  "county_matched": "Santa Clara",
  "county_confidence": 85.7,
  "tax_rate": 0.012,
  "closing_costs": null,
  "errors": [
    {
      "error_code": "RECORDING_BEFORE_SIGNING",
      "field": "date_recorded",
      "message": "Document recorded (2024-01-10) before it was signed (2024-01-15). Recording is 5 day(s) before signing. A document cannot be legally recorded before it exists.",
      "severity": "CRITICAL"
    }
  ],
  "warnings": [
    {
      "error_code": "AMOUNT_MISMATCH",
      "field": "amount_numeric / amount_words",
      "message": "Numeric amount ($1,250,000.00) does not match written amount ($1,200,000.00). Discrepancy: $50,000.00 (4.0%). Cannot determine which value is correct — human review required before recording.",
      "severity": "WARNING"
    }
  ]
}
```

**What was caught:**
- `S. Clara` → `Santa Clara` via fuzzy match (85.7% confidence) ✅
- Recorded Jan 10 before signed Jan 15 → CRITICAL error ✅
- $1,250,000 digits vs $1,200,000 words → $50,000 discrepancy ✅
- Closing costs skipped because CRITICAL error exists ✅

---

## Additional Test Cases

**Case 1 — Valid deed (passes all checks):**
```
County: San Mateo | Date Signed: 2024-03-01 | Date Recorded: 2024-03-05
Amount: $850,000.00 (Eight Hundred Fifty Thousand Dollars)
```
```
✅ VALID — Closing costs: $9,350.00 (1.1% × $850,000)
```

**Case 2 — Multiple errors:**
```
County: S. Mateo | Date Signed: 2024-06-20 | Date Recorded: 2024-06-10
Amount: $500,000.00 (Four Hundred Thousand Dollars)
```
```
❌ INVALID
   ❌ [RECORDING_BEFORE_SIGNING] Recorded 10 days before signing
   ⚠️  [AMOUNT_MISMATCH] $100,000 discrepancy (20%)
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- [Groq API key](https://console.groq.com) (free)

### Setup

```bash
git clone https://github.com/djism/propy-deed-validator.git
cd propy-deed-validator

python3 -m venv deed-env
source deed-env/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Add your GROQ_API_KEY to .env
```

### Run CLI

```bash
python main.py
```

### Run API

```bash
python main.py --api
```

| Endpoint | Description |
|---|---|
| `GET /health` | Service health check |
| `GET /validate/demo` | Run against task input deed |
| `POST /validate` | Validate any deed text |
| `GET /docs` | Full Swagger UI |

### Quick API test

```bash
# Health check
curl http://localhost:8000/health

# Run demo deed
curl http://localhost:8000/validate/demo | python -m json.tool

# Validate custom deed
curl -X POST http://localhost:8000/validate \
  -H "Content-Type: application/json" \
  -d '{"raw_text": "your deed text here"}'
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **LLM** | Groq Llama 3.3 70B | Free, fast, production-quality extraction |
| **Fuzzy Matching** | RapidFuzz | Deterministic, no API cost, confidence scores |
| **Number Parsing** | Custom parser | word2number has known bugs on compound numbers |
| **Schema Validation** | Pydantic v2 | Typed contracts catch LLM output errors immediately |
| **API** | FastAPI | Auto-documented, typed, async |

**Total cost to run: $0** — Groq free tier, open source everything.

---

## Answering the Review Criteria

> *What did you use to catch the date error — code or AI?*

**Code.** `datetime.strptime` parses both dates, a single inequality catches the error. This runs in microseconds and is always correct. An LLM might rationalize the invalid dates as intentional.

> *How did you handle the "S. Clara" lookup?*

**RapidFuzz fuzzy matching** with two scoring methods (token_sort_ratio + partial_ratio), both sides normalized to lowercase, minimum 60% confidence threshold. The system correctly matches S. Clara → Santa Clara at 85.7% confidence, SAN MATEO → San Mateo at 100%, and rejects completely unknown counties.

> *Is your code structured well?*

Each concern is isolated: LLM extraction in `llm_extractor.py`, fuzzy matching in `county_matcher.py`, validation logic in `validators.py`, orchestration in `deed_processor.py`. None of these files know about each other's internals. Swapping Groq for GPT-4o requires changing one line. Adding a new validation check requires adding one function to `validators.py` and one call in `run_all_validations`.

---

## Author

**Dhananjay Sharma**
M.S. Data Science, SUNY Stony Brook (May 2026)

<p>
  <a href="https://www.linkedin.com/in/dsharma2496/">LinkedIn</a> ·
  <a href="https://djism.github.io/">Portfolio</a> ·
  <a href="https://github.com/djism">GitHub</a>
</p>