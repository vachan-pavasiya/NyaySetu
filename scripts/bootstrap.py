"""
Idempotent Deployment Bootstrap Script
Role: Performs first-deploy initialization using live data from the AWS Open Data bucket.
Data Flow: S3 reachability check -> Gemini reachability check -> Ingest real judgments -> Analyze directions -> Link follow-up cases -> Compute compliance status.
Hard Rules: Never fake or seed data. Refuses to run if S3 or Gemini is unreachable.
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from backend.app.config import get_settings
from backend.app.database import SessionLocal, Base, engine
from backend.app.models import Judgment, Direction, CaseLink
from backend.pipeline.ingest import run_ingestion
from backend.pipeline.agent import analyze_judgment
from backend.pipeline.linking import run_full_linking_and_status_pipeline

settings = get_settings()


def verify_s3_reachability(bucket_name: str, region: str) -> bool:
    """Verify that the public unsigned AWS Open Data bucket is reachable."""
    print(f"[BOOTSTRAP 1/5] Verifying AWS Open Data S3 connectivity to '{bucket_name}'...")
    try:
        s3 = boto3.client(
            "s3",
            region_name=region,
            config=Config(signature_version=UNSIGNED, connect_timeout=5, read_timeout=5),
        )
        res = s3.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        if "Contents" in res or "KeyCount" in res:
            print("[BOOTSTRAP 1/5] [OK] AWS Open Data bucket is reachable with unsigned public access.")
            return True
        print("[BOOTSTRAP 1/5] [OK] S3 responded successfully.")
        return True
    except (BotoCoreError, ClientError, Exception) as exc:
        print("\n" + "!" * 80)
        print("[BOOTSTRAP FATAL ERROR] AWS S3 Open Data bucket is UNREACHABLE.")
        print(f"Bucket:  {bucket_name}")
        print(f"Details: {exc}")
        print("\nHACKATHON HARD RULE: Zero dummy or mock data allowed.")
        print("NyaySetu refuses to seed synthetic cases or fake dates.")
        print("Please check internet connectivity / outbound HTTPS access to AWS S3.")
        print("!" * 80 + "\n")
        return False


def verify_gemini_reachability() -> bool:
    """Verify that Google Gemini API is reachable with the configured API key."""
    print("[BOOTSTRAP 2/5] Verifying Google Gemini API connectivity...")
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("\n" + "!" * 80)
        print("[BOOTSTRAP FATAL ERROR] GEMINI_API_KEY is not configured.")
        print("Please set the GEMINI_API_KEY environment variable before running bootstrap.")
        print("!" * 80 + "\n")
        return False

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model = settings.GEMINI_MODEL or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        # Lightweight connection ping
        res = client.models.generate_content(
            model=model,
            contents="State OK in one word.",
        )
        if res and res.text:
            print(f"[BOOTSTRAP 2/5] [OK] Google Gemini API reachable using model '{model}'.")
            return True
        return True
    except Exception as exc:
        print("\n" + "!" * 80)
        print("[BOOTSTRAP FATAL ERROR] Google Gemini API is UNREACHABLE or returned an error.")
        print(f"Details: {exc}")
        print("Please verify GEMINI_API_KEY validity, quota budget, and outbound access.")
        print("!" * 80 + "\n")
        return False


def run_bootstrap(exit_on_failure: bool = True) -> bool:
    """Execute idempotent bootstrap pipeline."""
    start_time = time.time()
    print("\n" + "=" * 80)
    print("NYAYSETU: COURT-ORDER COMPLIANCE RADAR - DEPLOYMENT BOOTSTRAP")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 80)

    # 1. Enforce S3 reachability
    if not verify_s3_reachability(settings.S3_BUCKET, settings.AWS_DEFAULT_REGION):
        if exit_on_failure:
            sys.exit(1)
        return False

    # 2. Enforce Gemini reachability
    if not verify_gemini_reachability():
        if exit_on_failure:
            sys.exit(1)
        return False

    # Ensure database schema is created
    print("[BOOTSTRAP 3/5] Ensuring database schema exists...")
    Base.metadata.create_all(bind=engine)

    # Check configuration from environment (default limit=15 to stay well within Render 512MB RAM free tier)
    court = os.getenv("BOOTSTRAP_COURT", "calcutta_appellate_side")
    year = int(os.getenv("BOOTSTRAP_YEAR", "2023"))
    limit = int(os.getenv("BOOTSTRAP_LIMIT", "15"))
    force = os.getenv("FORCE_BOOTSTRAP", "false").lower() == "true"

    db = SessionLocal()
    try:
        existing_judgments = db.query(Judgment).count()
        existing_directions = db.query(Direction).count()
        print(f"[BOOTSTRAP 3/5] Current DB state: {existing_judgments} judgments, {existing_directions} directions.")

        if existing_judgments >= limit and not force:
            print(f"[BOOTSTRAP] Database already bootstrapped with {existing_judgments} real judgments.")
            print("[BOOTSTRAP] Idempotent skip: No new ingestion required. Set FORCE_BOOTSTRAP=true to override.")
        else:
            # 3. Ingest real judgments
            needed = max(limit - existing_judgments, 5) if not force else limit
            print(f"\n[BOOTSTRAP 4/5] Ingesting {needed} real judgments from S3 ({court} / {year})...")
            ingest_res = run_ingestion(court=court, year=year, limit=needed)
            print(f"[BOOTSTRAP 4/5] Ingestion completed: {ingest_res.get('succeeded')} succeeded, {ingest_res.get('failed')} failed.")

        # 4. Analyze unanalyzed judgments
        unanalyzed = (
            db.query(Judgment)
            .filter(Judgment.text != None)
            .outerjoin(Direction, Direction.judgment_id == Judgment.id)
            .filter(Direction.id == None)
            .limit(limit)
            .all()
        )

        if unanalyzed:
            print(f"\n[BOOTSTRAP 4/5] Running agentic extraction on {len(unanalyzed)} unanalyzed judgments...")
            for idx, j in enumerate(unanalyzed, 1):
                try:
                    res = analyze_judgment(j.id, db=db)
                    dirs_found = res.get("total_directions", 0)
                    print(f"  * [{idx}/{len(unanalyzed)}] {j.case_number}: extracted {dirs_found} operative directions.")
                except Exception as exc:
                    print(f"  * [{idx}/{len(unanalyzed)}] {j.case_number}: analysis skipped: {exc}")
        else:
            print("\n[BOOTSTRAP 4/5] All ingested judgments have already been analyzed.")

        # 5. Link follow-up cases and compute status
        print("\n[BOOTSTRAP 5/5] Executing case linking and 3-status compliance engine...")
        link_res = run_full_linking_and_status_pipeline(db=db)
        print(f"[BOOTSTRAP 5/5] Case linking complete: {link_res.get('links_created', 0)} links established.")

        # Final Summary
        total_j = db.query(Judgment).count()
        total_d = db.query(Direction).count()
        total_l = db.query(CaseLink).count()

        status_counts = {}
        for d in db.query(Direction).all():
            st = d.compliance_status or "UNVERIFIED"
            status_counts[st] = status_counts.get(st, 0) + 1

        elapsed = time.time() - start_time
        print("\n" + "=" * 80)
        print("BOOTSTRAP COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print(f"Total Judgments in DB:  {total_j}")
        print(f"Total Directions in DB: {total_d}")
        print(f"Status Distribution:    {status_counts}")
        print(f"Total Case Links:       {total_l}")
        print(f"Elapsed Time:           {elapsed:.2f} seconds")
        print("=" * 80 + "\n")
        return True

    finally:
        db.close()


if __name__ == "__main__":
    run_bootstrap(exit_on_failure=True)
