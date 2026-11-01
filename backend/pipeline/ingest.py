"""Live judgment ingestion and text extraction pipeline.

Role: Reads parquet metadata from S3, downloads judgment PDFs, extracts text with PyMuPDF,
      computes quality scores, flags unreadable documents, and persists records to SQLite.
Data flow: AWS S3 unsigned -> Parquet metadata -> PDF download -> PyMuPDF -> SQLite judgments.
"""

import io
import re
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import boto3
import botocore
from botocore import UNSIGNED
from botocore.config import Config
import pandas as pd
import pyarrow.fs as fs
import pyarrow.parquet as pq
import pymupdf
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database import SessionLocal, engine, Base
from backend.app.models import Judgment, IngestJob

logger = logging.getLogger("compliance_radar.ingest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

settings = get_settings()

# Known court alias mappings to S3 partition keys (court_code, bench_name)
COURT_ALIASES = {
    "calcutta": ("19_16", "calcutta_appellate_side"),
    "calcutta_appellate_side": ("19_16", "calcutta_appellate_side"),
    "calcutta_original_side": ("19_16", "calcutta_original_side"),
    "19_16": ("19_16", "calcutta_appellate_side"),
    "madras": ("33_10", "hc_cis_mas"),
    "madras_mas": ("33_10", "hc_cis_mas"),
    "madras_mdu": ("33_10", "mdubench"),
    "33_10": ("33_10", "hc_cis_mas"),
    "delhi": ("7_26", "dhcdb"),
    "7_26": ("7_26", "dhcdb"),
    "kerala": ("32_4", "highcourtofkerala"),
    "32_4": ("32_4", "highcourtofkerala"),
    "phhc": ("3_22", "phhc"),
    "3_22": ("3_22", "phhc"),
    "bombay": ("27_1", "newos"),
    "27_1": ("27_1", "newos"),
}


def resolve_court_and_bench(court_input: str) -> Tuple[str, str]:
    """Resolve user-supplied court name or code to (court_code, bench)."""
    norm = court_input.strip().lower().replace(" ", "_")
    if norm in COURT_ALIASES:
        return COURT_ALIASES[norm]
    # Check if format is already court_code/bench
    if "/" in norm:
        parts = norm.split("/")
        return parts[0], parts[1]
    # Default fallback to recommended Calcutta Appellate Side
    return ("19_16", "calcutta_appellate_side")


def get_s3_client(region: str = settings.AWS_DEFAULT_REGION) -> boto3.client:
    """Return an unsigned S3 client for public dataset access."""
    return boto3.client(
        "s3",
        region_name=region,
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=10,
            read_timeout=20,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def parse_case_title(title: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse case_number, petitioner, and respondent from title string.
    
    Example: 'WPA/14470/2023 of RAM SHARMA Vs STATE OF WEST BENGAL & ORS'
    Returns: ('WPA/14470/2023', 'RAM SHARMA', 'STATE OF WEST BENGAL & ORS')
    """
    if not title or not isinstance(title, str):
        return None, None, None

    case_num = None
    pet = None
    res = None

    # Extract case number prefix, e.g. WPA/123/2023 or CRL.M.C./5833/2022
    match_num = re.match(r"^([A-Za-z0-9\.\(\)\_\-\s]+/\d+/\d{4})", title.strip())
    if match_num:
        case_num = match_num.group(1).strip()
        rest = title[match_num.end():].strip()
    else:
        rest = title.strip()

    # Strip leading 'of'
    if rest.lower().startswith("of "):
        rest = rest[3:].strip()

    # Split by 'Vs' or 'V/S'
    parts = re.split(r"\s+(?:Vs\.?|V/S|vs\.?)\s+", rest, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        pet = parts[0].strip() or None
        res = parts[1].strip() or None
    elif len(parts) == 1 and parts[0]:
        pet = parts[0].strip()

    return case_num, pet, res


def compute_text_quality(text: str, pages: int) -> Tuple[float, str, Optional[str]]:
    """Compute text quality score and determine status.
    
    Returns:
        (text_quality: float, status: str, failure_reason: Optional[str])
    """
    if pages <= 0:
        return 0.0, "FAILED_UNREADABLE", "Empty document (0 pages)"

    clean_text = text.strip()
    char_count = len(clean_text)

    if char_count < 50:
        return 0.0, "FAILED_UNREADABLE", f"Insufficient text ({char_count} chars), likely scanned document"

    # Printable/valid character ratio
    printable_count = sum(1 for c in clean_text if c.isprintable() or c.isspace())
    valid_ratio = printable_count / max(char_count, 1)

    if valid_ratio < 0.70:
        return (
            round(valid_ratio, 3),
            "FAILED_UNREADABLE",
            f"High ratio of non-printable/corrupted characters ({1 - valid_ratio:.1%})",
        )

    # Compute normalized quality score [0.0, 1.0]
    chars_per_page = char_count / pages
    density_score = min(chars_per_page / 1500.0, 1.0)
    score = round(density_score * 0.4 + valid_ratio * 0.6, 3)

    return score, "INGESTED", None


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> Tuple[str, int, float, str, Optional[str]]:
    """Extract text from raw PDF bytes using PyMuPDF and evaluate quality.
    
    Returns:
        (extracted_text, page_count, text_quality, status, error_reason)
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = len(doc)
        full_text = "".join(page.get_text() for page in doc)
        quality, status, error = compute_text_quality(full_text, pages)
        return full_text, pages, quality, status, error
    except Exception as exc:
        return "", 0, 0.0, "FAILED_UNREADABLE", f"PyMuPDF parse error: {str(exc)}"


def download_pdf_from_s3(s3_client, bucket: str, s3_key: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Download PDF bytes from public S3 bucket without credentials."""
    try:
        buf = io.BytesIO()
        s3_client.download_fileobj(bucket, s3_key, buf)
        return buf.getvalue(), None
    except botocore.exceptions.ClientError as ce:
        code = ce.response.get("Error", {}).get("Code", "Unknown")
        return None, f"S3 {code}: {s3_key}"
    except Exception as exc:
        return None, f"Download error: {str(exc)}"


def prioritize_records(df: pd.DataFrame) -> pd.DataFrame:
    """Sort DataFrame preferring contempt petitions and writ petitions.
    
    Priority 1: Contempt petitions (CPAN, CONT) to ensure ground-truth compliance linkage data.
    Priority 2: Writ petitions (WPA, WP, CWP) directing state authorities.
    Priority 3: Other miscellaneous jurisdictions.
    """
    def get_priority(title: str) -> int:
        if not isinstance(title, str):
            return 3
        t = title.upper()
        if any(cp in t for cp in ["CPAN", "CONT", "CONTEMPT"]):
            return 1
        if any(wp in t for wp in ["WPA", "W.P", "WP", "CWP", "WRIT"]):
            return 2
        return 3

    df["__priority"] = df["title"].apply(get_priority)
    sorted_df = df.sort_values("__priority", ascending=True).drop(columns=["__priority"])
    return sorted_df


def ingest_single_record(
    db: Session,
    s3_client,
    bucket: str,
    row: Dict[str, Any],
    year: int,
    court_code: str,
    bench: str,
) -> Dict[str, Any]:
    """Ingest a single judgment record idempotently.
    
    Returns summary dict with status and execution latency.
    """
    start_t = time.perf_counter()
    pdf_link = row.get("pdf_link", "") or ""
    filename = Path(pdf_link).name
    s3_key = f"data/pdf/year={year}/court={court_code}/bench={bench}/{filename}"
    cnr = row.get("cnr") or None

    # Idempotency check: lookup by s3_key or CNR
    existing = None
    if s3_key:
        existing = db.query(Judgment).filter(Judgment.s3_key == s3_key).first()
    if not existing and cnr:
        existing = db.query(Judgment).filter(Judgment.cnr == cnr).first()

    if existing and existing.status == "INGESTED" and (existing.text and len(existing.text) > 50):
        duration = time.perf_counter() - start_t
        return {
            "id": existing.id,
            "status": "INGESTED",
            "reason": "Already exists (cached)",
            "duration": duration,
            "is_new": False,
        }

    # Parse metadata details
    case_num, pet, res = parse_case_title(row.get("title"))
    court_name = row.get("court") or "High Court"
    dec_date = row.get("decision_date")
    if pd.isna(dec_date):
        j_date = None
    elif hasattr(dec_date, "date"):
        j_date = dec_date.date()
    else:
        j_date = None

    # Download PDF
    pdf_bytes, download_err = download_pdf_from_s3(s3_client, bucket, s3_key)
    if download_err or not pdf_bytes:
        status = "FAILED_DOWNLOAD"
        error = download_err or "Empty download"
        text = None
        quality = 0.0
    else:
        # Extract text
        text, pages, quality, status, error = extract_text_from_pdf_bytes(pdf_bytes)

    # Persist or update record
    if existing:
        existing.case_number = case_num
        existing.petitioner = pet
        existing.respondent = res
        existing.judgment_date = j_date
        existing.text = text
        existing.text_quality = quality
        existing.status = status
        existing.error = error
        record = existing
    else:
        record = Judgment(
            court=court_name,
            year=year,
            case_number=case_num,
            cnr=cnr,
            judgment_date=j_date,
            petitioner=pet,
            respondent=res,
            s3_key=s3_key,
            text=text,
            text_quality=quality,
            status=status,
            error=error,
        )
        db.add(record)

    db.commit()
    db.refresh(record)
    duration = time.perf_counter() - start_t

    return {
        "id": record.id,
        "status": status,
        "reason": error,
        "duration": duration,
        "is_new": existing is None,
    }


def run_ingestion(
    court: str = "calcutta_appellate_side",
    year: int = 2023,
    limit: int = 100,
    job_id: Optional[str] = None,
    *args,
    **kwargs,
) -> Dict[str, Any]:
    """Execute live ingestion batch from S3 parquet metadata into SQLite."""
    court_code, bench = resolve_court_and_bench(court)
    bucket = settings.S3_BUCKET
    meta_key = f"metadata/parquet/year={year}/court={court_code}/bench={bench}/metadata.parquet"
    logger.info(f"Starting ingestion: court={court} ({court_code}/{bench}), year={year}, limit={limit}")

    s3_client = get_s3_client(settings.AWS_DEFAULT_REGION)
    s3fs_client = fs.S3FileSystem(anonymous=True, region=settings.AWS_DEFAULT_REGION)

    # Filter out already ingested records so we ingest NEW judgments
    with SessionLocal() as check_db:
        existing_cnrs = set(
            r[0] for r in check_db.query(Judgment.cnr).filter(
                Judgment.cnr.isnot(None),
                Judgment.status == "INGESTED"
            )
        )
        existing_keys = set(
            r[0] for r in check_db.query(Judgment.s3_key).filter(
                Judgment.s3_key.isnot(None),
                Judgment.status == "INGESTED"
            )
        )

    # Low-memory streaming extraction:
    # Read only essential columns in 10,000-row chunks.
    # Uses < 40MB RAM instead of > 500MB on whole-dataset parquet loading.
    target_records: List[Dict[str, Any]] = []
    columns_needed = ["title", "pdf_link", "cnr", "decision_date", "court"]

    try:
        parquet_path = f"{bucket}/{meta_key}"
        pf = pq.ParquetFile(parquet_path, filesystem=s3fs_client)

        def is_unprocessed_row(row_dict: Dict[str, Any]) -> bool:
            c = row_dict.get("cnr")
            if c and c in existing_cnrs:
                return False
            plink = row_dict.get("pdf_link", "") or ""
            fname = Path(plink).name
            skey = f"data/pdf/year={year}/court={court_code}/bench={bench}/{fname}"
            if skey in existing_keys:
                return False
            return True

        # Pass 1: Prioritize contempt petitions (CPAN, CONT)
        for batch in pf.iter_batches(batch_size=10000, columns=columns_needed):
            df_chunk = batch.to_pandas()
            for _, r in df_chunk.iterrows():
                row_dict = r.to_dict()
                if not is_unprocessed_row(row_dict):
                    continue
                t = str(row_dict.get("title", "")).upper()
                if any(cp in t for cp in ["CPAN", "CONT", "CONTEMPT"]):
                    target_records.append(row_dict)
                    if len(target_records) >= limit:
                        break
            del df_chunk
            if len(target_records) >= limit:
                break

        # Pass 2: If limit not reached, stream writ petitions (WPA, WP)
        if len(target_records) < limit:
            for batch in pf.iter_batches(batch_size=10000, columns=columns_needed):
                df_chunk = batch.to_pandas()
                for _, r in df_chunk.iterrows():
                    row_dict = r.to_dict()
                    if not is_unprocessed_row(row_dict):
                        continue
                    t = str(row_dict.get("title", "")).upper()
                    if any(wp in t for wp in ["WPA", "W.P", "WP", "CWP", "WRIT"]):
                        if not any(cp in t for cp in ["CPAN", "CONT", "CONTEMPT"]):
                            target_records.append(row_dict)
                            if len(target_records) >= limit:
                                break
                del df_chunk
                if len(target_records) >= limit:
                    break

        # Pass 3: If still not reached, fill with any unprocessed records
        if len(target_records) < limit:
            for batch in pf.iter_batches(batch_size=10000, columns=columns_needed):
                df_chunk = batch.to_pandas()
                for _, r in df_chunk.iterrows():
                    row_dict = r.to_dict()
                    if not is_unprocessed_row(row_dict):
                        continue
                    target_records.append(row_dict)
                    if len(target_records) >= limit:
                        break
                del df_chunk
                if len(target_records) >= limit:
                    break

    except Exception as exc:
        err_msg = f"Failed to stream parquet metadata at {meta_key}: {str(exc)}"
        logger.error(err_msg)
        if job_id:
            with SessionLocal() as db:
                job = db.query(IngestJob).filter(IngestJob.id == job_id).first()
                if job:
                    job.status = "FAILED"
                    job.error_summary = err_msg
                    job.completed_at = datetime.now(timezone.utc)
                    db.commit()
        return {"status": "FAILED", "error": err_msg, "total": 0, "succeeded": 0, "failed": 0}

    total_target = len(target_records)
    logger.info(f"Selected {total_target} new prioritized judgment records to ingest ({len(existing_keys)} already cached in database).")

    processed = 0
    succeeded = 0
    failed = 0
    failure_reasons: Dict[str, int] = {}
    total_time = 0.0

    # Initialize job in DB if requested
    if job_id:
        with SessionLocal() as db:
            job = db.query(IngestJob).filter(IngestJob.id == job_id).first()
            if job:
                job.status = "RUNNING"
                job.total = total_target
                db.commit()

    db = SessionLocal()
    try:
        for idx, row in enumerate(target_records):
            try:
                res = ingest_single_record(
                    db=db,
                    s3_client=s3_client,
                    bucket=bucket,
                    row=row,
                    year=year,
                    court_code=court_code,
                    bench=bench,
                )
                processed += 1
                total_time += res["duration"]

                if res["status"] == "INGESTED":
                    succeeded += 1
                else:
                    failed += 1
                    reason = res["reason"] or "Unknown error"
                    failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

                # Periodically update job record every 5 items
                if job_id and (processed % 5 == 0 or processed == total_target):
                    job = db.query(IngestJob).filter(IngestJob.id == job_id).first()
                    if job:
                        job.processed = processed
                        job.succeeded = succeeded
                        job.failed = failed
                        job.avg_seconds_per_doc = round(total_time / max(processed, 1), 3)
                        db.commit()

                if processed % 20 == 0 or processed == total_target:
                    avg_sec = total_time / max(processed, 1)
                    logger.info(f"Progress: {processed}/{total_target} | Succeeded: {succeeded} | Failed: {failed} | Avg: {avg_sec:.2f}s/doc")

            except Exception as item_exc:
                # Never crash the batch!
                processed += 1
                failed += 1
                err_str = f"Unhandled row exception: {str(item_exc)}"
                failure_reasons[err_str] = failure_reasons.get(err_str, 0) + 1
                logger.error(err_str)

    finally:
        db.close()

    avg_seconds = round(total_time / max(processed, 1), 3)

    # Mark job complete
    if job_id:
        with SessionLocal() as db:
            job = db.query(IngestJob).filter(IngestJob.id == job_id).first()
            if job:
                job.status = "COMPLETED"
                job.processed = processed
                job.succeeded = succeeded
                job.failed = failed
                job.avg_seconds_per_doc = avg_seconds
                job.error_summary = str(failure_reasons)
                job.completed_at = datetime.now(timezone.utc)
                db.commit()

    summary = {
        "status": "COMPLETED",
        "court": court,
        "year": year,
        "total": processed,
        "succeeded": succeeded,
        "failed": failed,
        "failure_reasons": failure_reasons,
        "avg_seconds_per_doc": avg_seconds,
        "total_seconds": round(total_time, 2),
    }
    return summary


def main():
    """CLI entrypoint for running ingestion."""
    import argparse
    parser = argparse.ArgumentParser(description="Ingest Indian High Court Judgments from public S3 bucket.")
    parser.add_argument("--court", default="calcutta_appellate_side", help="Court name or alias (e.g. calcutta_appellate_side, madras, delhi)")
    parser.add_argument("--year", type=int, default=2023, help="Year of judgments (e.g. 2023)")
    parser.add_argument("--limit", type=int, default=100, help="Number of judgments to ingest (default: 100)")
    args = parser.parse_args()

    print(f"\n=======================================================")
    print(f"Court-Order Compliance Radar: Ingestion Pipeline")
    print(f"Court: {args.court} | Year: {args.year} | Limit: {args.limit}")
    print(f"=======================================================\n")

    summary = run_ingestion(court=args.court, year=args.year, limit=args.limit)

    print("\n================ INGESTION SUMMARY ================")
    print(f"Status: {summary['status']}")
    print(f"Total processed: {summary['total']}")
    print(f"Succeeded (INGESTED): {summary['succeeded']}")
    print(f"Failed: {summary['failed']}")
    if summary["failure_reasons"]:
        print("Failure Reasons Breakdown:")
        for r, c in summary["failure_reasons"].items():
            print(f"  - [{c} docs]: {r}")
    print(f"Average seconds per document: {summary['avg_seconds_per_doc']:.3f}s")
    print(f"Total elapsed time: {summary['total_seconds']:.2f}s")
    print("====================================================\n")


if __name__ == "__main__":
    main()

