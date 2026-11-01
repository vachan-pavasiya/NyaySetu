# NyaySetu: Court-Order Compliance Radar

An automated compliance monitoring platform that ingests real Indian High Court judgments from official open data (AWS Open Data public S3 bucket `indian-high-court-judgments`), extracts operative directions against government departments with verifiable source quotes, computes deterministic compliance deadline windows, and links subsequent orders and contempt proceedings to track compliance status.

```mermaid
graph TD
    subgraph Data Layer
        S3[AWS Open Data S3<br/>indian-high-court-judgments]
        META[Parquet Metadata<br/>year/court/bench]
        PDF[Raw Judgment PDFs]
        S3 --> META
        S3 --> PDF
    end

    subgraph Backend Pipeline
        ING[1. Ingestion Engine<br/>boto3 unsigned]
        EXT[2. Text Extraction & Scoring<br/>PyMuPDF]
        SEG[3. Operative Segmentation<br/>Regex & Heuristics]
        LLM[4. Direction Extraction Engine<br/>Gemini 2.5 Flash]
        VER[5. Verifier & Guardrail<br/>Verbatim substring verification]
        DATE[6. Deadline Math Engine<br/>Deterministic dateutil windows]
        LINK[7. Case & Contempt Linker<br/>CNR, WP, CPAN cross-ref]
    end

    subgraph Storage & UI
        DB[(SQLite / SQLAlchemy<br/>compliance_radar.db)]
        CACHE[(LLM Response Cache<br/>hash keyed)]
        API[FastAPI REST API<br/>/health, /ledger, /calendar]
        FE[React + Vite + Tailwind UI<br/>Ingest, Ledger, Calendar, Cases]
    end

    META --> ING
    PDF --> EXT
    ING --> DB
    EXT --> SEG
    SEG --> LLM
    LLM <--> CACHE
    LLM --> VER
    VER --> DATE
    DATE --> DB
    LINK --> DB
    DB --> API
    API --> FE
```

---

## Key Features

1. **Zero Mock Data Hard Rule**: Every record shown is ingested live from the public AWS Open Data bucket `indian-high-court-judgments` (`CC-BY-4.0`, public unsigned S3 access).
2. **Operative Direction Extraction**: Automatically extracts `{responsible_party, party_type, action, deadline_phrase, source_quote, confidence}`.
3. **Verbatim Quote Guardrail**: Rejects hallucinations by enforcing that `source_quote` is a strict verbatim substring of the underlying judgment text.
4. **Deterministic Deadline Windows**: Receipt dates for government departments are unknown; the engine calculates an estimated delivery window `[judgment_date + N, judgment_date + N + SERVICE_LAG_DAYS]` where `SERVICE_LAG_DAYS` defaults to 30 days.
5. **Case Linking & Follow-Up**: Links later orders in the same matter (CNR, case number, contempt citations `CPAN` in `WPA`) to classify status into `COMPLIED`, `PENDING`, `LAPSED_NO_RECORD`, or `UNVERIFIED`.
6. **LLM Cost & Concurrency Protection**: Caches LLM requests keyed by `sha256(prompt + text)` in SQLite and limits concurrency with exponential backoff.

---

## Project Structure

```text
├── backend/
│   ├── app/
│   │   ├── config.py         # Pydantic Settings (.env loader)
│   │   ├── database.py       # SQLite engine and session factory
│   │   ├── models.py         # SQLAlchemy ORM models
│   │   └── main.py           # FastAPI entry point & GET /health
│   ├── pipeline/             # Ingestion, segmentation, extraction, linker
│   ├── tests/                # Pytest test suite
│   │   └── test_health.py    # Health endpoint & DB test
│   └── requirements.txt      # Python dependencies
├── frontend/                 # Vite + React (TypeScript) + Tailwind CSS
├── docs/
│   └── dataset_notes.md      # Live S3 discovery notes & court evaluation
├── eval/                     # Hand-labelled gold evaluation set
├── scripts/
│   └── explore_bucket.py     # Live S3 exploration script (unsigned botocore)
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore patterns
└── README.md
```

---

## Quickstart

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 2. Backend Setup
```bash
# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Configure environment
cp .env.example .env

# Run tests
pytest
```

### 3. Run FastAPI Backend
```bash
uvicorn backend.app.main:app --reload --port 8000
```
Visit http://127.0.0.1:8000/docs for Swagger UI and http://127.0.0.1:8000/health for health check.

### 4. Explore S3 Dataset Live
```bash
python scripts/explore_bucket.py
```
This connects unsigned to `indian-high-court-judgments`, inspects metadata parquet files, verifies PDF linkage, and updates `docs/dataset_notes.md`.

### 5. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:3000 in your browser.

---

## Evaluation & Benchmarking Harness

NyaySetu includes an empirical evaluation harness with hand-labelled gold ground truth from real Calcutta High Court judgments in `eval/gold/*.json` and hand-calculated date cases in `eval/deadline_cases.json`.

### 1. Label Helper CLI Tool
To view operative judgment excerpts and annotate new gold direction records:
```bash
# List available judgments and annotation status
python eval/label_cli.py --list

# Interactively annotate directions for a specific judgment
python eval/label_cli.py --judgment-id 4
```

### 2. Standalone Evaluation Commands

To run any evaluation suite independently:

```bash
# 1. Extraction Evaluation (Precision, Recall, F1 & Hallucination Rate)
python eval/run_extraction_eval.py

# 2. Deterministic Deadline Math Evaluation (vs 25 hand-calculated cases)
python eval/run_deadline_eval.py

# 3. Citation-Resolution Rate (Rule Adherence)
python eval/run_linking_eval.py

# 4. Master Full Suite Run (Consolidates and writes eval/results/latest.json)
python eval/run_all_evals.py
```

### 3. Latest Benchmark Results (Real Open Data)

| Evaluation Harness | Metric / Component | Score | Benchmark Dataset |
| :--- | :--- | :---: | :--- |
| **Extraction Precision** | Responsible Party | **95.7%** | 11 Hand-labelled Gold Orders (`eval/gold/`) |
| **Extraction Recall** | Responsible Party | **100.0%** | 22 Real Ground-Truth Directions |
| **Extraction F1** | Operative Action | **97.8%** | Fuzzy Token & Sequence Overlap (>= 0.60) |
| **Extraction F1** | Deadline Phrase | **100.0%** | Exact Whitespace-Normalized Match |
| **Hallucination Rate** | Verbatim Quote Verifier | **4.35%** | Only 1 of 23 quotes differed from source |
| **Deadline Math** | Exact All-Field Accuracy | **100.0%** | 25 Hand-Calculated Cases (`eval/deadline_cases.json`) |
| **Citation Resolution** | Contempts with Header Citations | **30.5%** | 18 of 59 Contempt Orders contain header citation |
| **Citation Resolution** | Cited Writs in Database | **66.7%** | 12 of 18 cited writs exist in DB |
| **Citation Resolution** | Rule Adherence | **100.0%** | 12 of 12 linkable pairs resolved *(Note: Linkable pairs were ingested by targeted search, so this is not an accuracy estimate)* |
| **Temporal Sanity** | Date Inversion Violations | **0** | Strict Rule: Writ $\le$ Contempt Date Enforced |

---

## Evaluation Integrity & Benchmark Scope

- `eval/agent_generated holds auto-generated drafts, excluded from all metrics`.
- Per **EVAL INTEGRITY** rule: Gold benchmark data comes strictly from human ground-truth annotations in `eval/gold/` and `eval/deadline_cases.json`. The pipeline never creates, fills, or infers gold labels.

---

## Known Limitations & Legal Disclaimers

1. **UNVERIFIED is Common**: High Court registries do not maintain an automatic feedback loop reporting department compliance back into the original writ case file. Therefore, `UNVERIFIED` indicates the absence of subsequent public proceedings in the open dataset—not disobedience or non-compliance.
2. **Dataset Time Horizon**: The public AWS Open Data repository currently covers historical judgment batches spanning **2019 to 2023**.
3. **Legal Information, Not Legal Advice**: NyaySetu is an analytical compliance research tool. Output records and deadline estimates represent structured information from public dockets, not legal opinions or advisory services.
4. **Scanned Image PDFs**: PyMuPDF extracts digital vector text. Historical orders uploaded as image-only scans without an embedded text layer are detected and gracefully marked `FAILED_UNREADABLE` with explicit failure logs without interrupting batch ingestion.

---

## Dataset Recommendation
- **Recommended Court:** Calcutta High Court (Appellate Side) (`court=19_16`, `bench=calcutta_appellate_side`)
- **Recommended Year:** 2023
- **Primary Reasons:**
  - 50.5% (36,355 orders) are Writ Petitions (`WPA`) against government departments.
  - 6,134 Contempt Petitions (`CPAN`) explicitly linked to original WPAs for follow-up verification.
  - 100% digital vector text readable by PyMuPDF without OCR.
  - Complete calendar progression allowing mature compliance window resolution (`COMPLIED`, `LAPSED_NO_RECORD`).

