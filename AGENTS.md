PROJECT: Court-Order Compliance Radar

An AI agent reads Indian High Court judgments from official open data, extracts each operative direction as a structured record (responsible party, action, deadline phrase, exact source quote), resolves deadlines into date WINDOWS with deterministic code, builds a per-department ledger and calendar, and links later orders in the same case to mark each direction COMPLIED, PENDING, LAPSED\_NO\_RECORD or UNVERIFIED.



TIME BUDGET: the whole project must be finished in 20 hours. Prefer the simplest thing that works. No over-engineering.



HACKATHON HARD RULES (violation = disqualification):

1\. NO dummy, mock, hardcoded or placeholder data in the app. Everything shown in the UI comes from the live open dataset (AWS Open Data bucket "indian-high-court-judgments", CC-BY-4.0, public, unsigned S3 access, no AWS account) or from records the pipeline derived from it. Never write seed JSON of fake cases or numbers.

2\. Only static data files allowed: code, config, and a hand-labelled GOLD eval set from REAL judgments in /eval, used only to measure accuracy, never displayed as app data.

3\. The app must run live end to end: user can trigger ingestion of real judgments, analysis, ledger, calendar, linking.

4\. Never present pre-recorded output as live. Show real progress.

5\. All core logic is written in this repo. Open-source libraries are fine.

6\. Code must be simple enough that one person can explain every file. Put a short docstring at the top of each module (role + data flow).



STACK:

\- Backend: Python 3.11+, FastAPI, SQLite + SQLAlchemy, Pydantic.

\- Data: boto3 with unsigned config (botocore.UNSIGNED), pandas/pyarrow for parquet.

\- PDF text: PyMuPDF. If text is empty/garbage, mark the document FAILED\_UNREADABLE with a reason (no OCR). Never crash the batch.

\- LLM: Google Gemini via google-genai SDK, structured JSON output validated with Pydantic. Model name from env GEMINI\_MODEL. Cache every LLM response in a SQLite table keyed by hash(prompt+text) to save quota. Limit concurrency to 3 and retry with exponential backoff on 429/5xx.

\- Agent loop: explicit Python state machine (segment -> extract -> verify -> retry with feedback up to 2 times -> persist or LOW\_CONFIDENCE). Log each step with latency.

\- Deadline math: deterministic Python (dateutil). The LLM never computes dates. It may only classify phrases the regex rules don't recognise.

\- Frontend: React + Vite + TypeScript + Tailwind, minimal. Views: Ingest, Judgment view, Ledger, Calendar, Case timeline, Eval.



PIPELINE:

1 Ingest real judgments + metadata for one court/year.

2 Extract text, with a quality score.

3 Segment the operative part of the order.

4 LLM extracts directions: {responsible\_party, party\_type, action, deadline\_phrase|null, source\_quote, confidence}.

5 Verifier: source\_quote must be a verbatim substring of the source (after whitespace normalisation). Else reject and retry with feedback.

6 Deadline resolution (deterministic): receipt date is unknown, so return a WINDOW \[judgment\_date + N, judgment\_date + N + SERVICE\_LAG\_DAYS (default 30, configurable constant)] labelled "estimated window". Never invent a precise date.

7 Link later orders in the same case (CNR, case number, "in W.P. No. ..." citations, contempt petitions). The LLM may only classify what the later order says about compliance and must return a verified verbatim quote.

8 Status: COMPLIED only with a verified supporting quote from a later order. Contempt petition linked = evidence of non-compliance flag. PENDING if window not lapsed and no evidence. LAPSED\_NO\_RECORD if lapsed and no later order. Default UNVERIFIED. Never infer compliance from silence.



GUARDRAILS (scoring pillar):

\- Every direction stores exact quote, offsets, judgment ID, confidence.

\- Show UNVERIFIED honestly. Visible disclaimer: "Legal information, not legal advice."

\- Per-document failure reasons stored and visible in the UI.



QUALITY:

\- Type hints, small modules, functions under \~50 lines.

\- Each stage runnable from CLI, and each has at least one test using real text from real judgments.

\- Structured logging with timings. Timeouts + retries on every external call.

\- README with setup, mermaid architecture diagram, and commands to reproduce eval numbers.



WORKFLOW RULES FOR YOU (THE AGENT):

\- Before each phase, post a short plan and assumptions. Ask me only if blocked.

\- Never fabricate dataset structure. Inspect the real bucket first and adapt.

\- After each phase, run the acceptance check and report real results, including failures.

\- Do not start the next phase until I say so.

