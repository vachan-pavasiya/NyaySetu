"""Targeted ingestion script for matched cited writs.
Downloads real PDFs from S3, extracts text with PyMuPDF, evaluates text quality,
and persists records into compliance_radar.db.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import pyarrow.parquet as pq
import pyarrow.fs as fs
import pymupdf

from backend.app.database import SessionLocal
from backend.app.models import Judgment
from backend.pipeline.ingest import parse_case_title, compute_text_quality

# The 11 found records from our metadata search
# We'll re-query their exact rows to ensure all fields are captured
MATCH_SPECS = [
    {"year": 2019, "bench": "calcutta_appellate_side", "pat": "FMA/1879/2019", "target": "FMA 1879 of 2019"},
    {"year": 2021, "bench": "calcutta_appellate_side", "pat": "WPA/4835/2021", "target": "WPA 4835 of 2021"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "WPA/2222/2022", "target": "WPA 2222 of 2022"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "WPA/7971/2021", "target": "WPA 7971 of 2021"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "WPA/17378/2022", "target": "WPA 17378 of 2022"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "WPA/18860/2021", "target": "WPA 18860 of 2021"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "WPA/13757/2004", "target": "WPA 13757 of 2004"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "WPA/5477/2022", "target": "WPA 5477 of 2022"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "WPA/4409/2022", "target": "WPA 4409 of 2022"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "WPA/4466/2022", "target": "WPA 4466 of 2022"},
    {"year": 2022, "bench": "calcutta_appellate_side", "pat": "MAT/408/2022", "target": "MAT 408 of 2022"},
]

s3 = boto3.client("s3", region_name="ap-south-1", config=Config(signature_version=UNSIGNED))
s3fs = fs.S3FileSystem(anonymous=True, region="ap-south-1")
db = SessionLocal()

results = []

for spec in MATCH_SPECS:
    yr = spec["year"]
    bench = spec["bench"]
    pat = spec["pat"]
    target = spec["target"]
    
    meta_path = f"indian-high-court-judgments/metadata/parquet/year={yr}/court=19_16/bench={bench}/metadata.parquet"
    pf = pq.ParquetFile(meta_path, filesystem=s3fs)
    df = pf.read(columns=["title", "pdf_link", "cnr", "decision_date", "court"]).to_pandas()
    
    match = df[df["title"].str.contains(pat, na=False, regex=False)]
    if match.empty:
        results.append({
            "target": target,
            "status": "NOT_FOUND_IN_PARQUET",
            "details": f"Pattern {pat} not matched in {meta_path}"
        })
        continue
        
    row = match.iloc[0]
    title = str(row["title"])
    pdf_link = str(row.get("pdf_link") or "")
    filename = Path(pdf_link).name if pdf_link else ""
    cnr = row.get("cnr")
    dec_date = row.get("decision_date")
    court_name = row.get("court") or "Calcutta High Court"
    
    if not filename:
        results.append({
            "target": target,
            "title": title,
            "status": "NO_PDF_LINK",
            "details": "Metadata has empty pdf_link"
        })
        continue
        
    s3_key = f"data/pdf/year={yr}/court=19_16/bench={bench}/{filename}"
    
    # Try downloading PDF
    try:
        buf = io.BytesIO()
        s3.download_fileobj("indian-high-court-judgments", s3_key, buf)
        pdf_bytes = buf.getvalue()
        download_size = len(pdf_bytes)
    except Exception as exc:
        results.append({
            "target": target,
            "title": title,
            "s3_key": s3_key,
            "status": "FAILED_DOWNLOAD",
            "details": str(exc)
        })
        continue
        
    # Extract text with PyMuPDF
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pages = len(doc)
        text = "".join(page.get_text() for page in doc)
        quality, text_status, error = compute_text_quality(text, pages)
    except Exception as exc:
        results.append({
            "target": target,
            "title": title,
            "s3_key": s3_key,
            "size": download_size,
            "status": "FAILED_UNREADABLE",
            "details": f"PyMuPDF error: {str(exc)}"
        })
        continue

    # Parse metadata details
    case_num, pet, res = parse_case_title(title)
    if hasattr(dec_date, "date"):
        j_date = dec_date.date()
    else:
        j_date = None

    # Check if already in DB
    existing = db.query(Judgment).filter(Judgment.s3_key == s3_key).first()
    if not existing and cnr:
        existing = db.query(Judgment).filter(Judgment.cnr == cnr).first()

    if existing:
        existing.case_number = case_num or pat
        existing.petitioner = pet
        existing.respondent = res
        existing.judgment_date = j_date
        existing.text = text
        existing.text_quality = quality
        existing.status = text_status
        existing.error = error
        record_id = existing.id
        action = "updated"
    else:
        rec = Judgment(
            court=court_name,
            year=yr,
            case_number=case_num or pat,
            cnr=cnr,
            judgment_date=j_date,
            petitioner=pet,
            respondent=res,
            s3_key=s3_key,
            text=text,
            text_quality=quality,
            status=text_status,
            error=error,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        record_id = rec.id
        action = "inserted"

    results.append({
        "target": target,
        "judgment_id": record_id,
        "case_number": case_num or pat,
        "title": title,
        "decision_date": str(j_date),
        "pages": pages,
        "char_count": len(text),
        "text_quality": quality,
        "pdf_size": download_size,
        "status": text_status,
        "action": action,
        "preview": text[:200].replace("\n", " ")
    })

db.close()

import json
print(json.dumps(results, indent=2))
