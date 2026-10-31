"""Phase 2 Acceptance Runner.

Role: Executes Phase 2 agentic analysis on 30 real judgments with live Gemini extraction,
      filters boilerplate, verifies source quotes and deadline phrases verbatim,
      extends adjacent deadline sentences, and reports true DB metrics.
Data flow: SQLite judgments -> Operative segmentation -> Gemini Extractor -> Verifier -> SQLite directions.
"""

import os
import sys
import time
from pathlib import Path
from sqlalchemy import func

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import Judgment, Direction, OperativeSegment, LLMCache
from backend.pipeline.agent import analyze_judgment
from backend.pipeline.extract_directions import reset_call_metrics, get_call_metrics


def run():
    db = SessionLocal()
    try:
        # Reset counters and clean previous run records
        reset_call_metrics()
        db.query(Direction).delete()
        db.query(OperativeSegment).delete()
        db.query(LLMCache).delete()  # Clean cache to measure pure live Gemini API execution
        db.commit()

        judgments = (
            db.query(Judgment)
            .filter(Judgment.status == "INGESTED")
            .order_by(Judgment.id)
            .limit(30)
            .all()
        )
        print(f"Running Live Phase 2 analysis on {len(judgments)} real judgments...")

        start_all = time.perf_counter()
        with_directions = 0
        total_directions = 0
        first_try_verified = 0
        after_retry_verified = 0
        total_deadlines_verified = 0
        total_quotes_extended = 0

        for idx, j in enumerate(judgments, 1):
            t0 = time.perf_counter()
            agent_res = analyze_judgment(j.id, db)
            dur = time.perf_counter() - t0

            dirs = agent_res.get("directions", [])
            m = agent_res.get("metrics", {})
            f_try = m.get("verified_first_try", 0)
            a_try = m.get("verified_after_retry", 0)
            dl_v = m.get("deadlines_verified", 0)
            q_ext = m.get("quotes_extended", 0)

            if dirs:
                with_directions += 1
                total_directions += len(dirs)
                first_try_verified += f_try
                after_retry_verified += a_try
                total_deadlines_verified += dl_v
                total_quotes_extended += q_ext

            print(
                f"[{idx:02d}/30] Case: {j.case_number or j.id} | "
                f"Dirs: {len(dirs)} | Dur: {dur:.2f}s | "
                f"Deadlines: {dl_v} | Quotes Extended: {q_ext}"
            )

        total_dur = time.perf_counter() - start_all
        avg_lat = total_dur / max(1, len(judgments))

        all_dirs = db.query(Direction).all()
        verified_count = sum(1 for d in all_dirs if d.quote_verified)
        dirs_with_deadline = [d for d in all_dirs if d.deadline_phrase is not None]

        # Method breakdown in DB
        method_counts = dict(
            db.query(Direction.extraction_method, func.count(Direction.id))
            .group_by(Direction.extraction_method)
            .all()
        )

        call_metrics = get_call_metrics()

        print("\n" + "=" * 55)
        print("=== PHASE 2 LIVE ACCEPTANCE RESULTS ===")
        print("=" * 55)
        print(f"Judgments Analysed: {len(judgments)}")
        print(f"Judgments with Substantive Directions: {with_directions}")
        print(f"Total Substantive Directions: {total_directions}")
        print(f"Verified Direction Quotes: {verified_count}/{total_directions} ({100.0 * verified_count / max(1, total_directions):.1f}%)")
        print(f"Verbatim-Pass First Try: {first_try_verified}/{total_directions} ({100.0 * first_try_verified / max(1, total_directions):.1f}%)")
        print(f"Verbatim-Pass After Retry: {after_retry_verified}/{total_directions} ({100.0 * after_retry_verified / max(1, total_directions):.1f}%)")
        print(f"Total Directions with Deadline Phrase: {len(dirs_with_deadline)}/{total_directions}")
        print(f"Deadline Phrases Verified Verbatim: {total_deadlines_verified}/{len(dirs_with_deadline)} ({100.0 * total_deadlines_verified / max(1, len(dirs_with_deadline)):.1f}%)")
        print(f"Adjacent Deadline Sentences Extended into Source Quote: {total_quotes_extended}")
        print(f"Average Latency per Judgment: {avg_lat:.3f}s (Total: {total_dur:.2f}s)")
        print(f"API Call Metrics: {call_metrics['live_calls']} Live Calls, {call_metrics['cached_calls']} Cached Calls, {call_metrics['fallback_calls']} Fallback Calls")
        print(f"Stored Records by Extraction Method: {method_counts}")

        print("\n" + "=" * 55)
        print("=== 5 REAL SUBSTANTIVE DIRECTIONS WITH VERBATIM DEADLINES ===")
        print("=" * 55)
        sample_dirs = [d for d in all_dirs if d.deadline_phrase is not None][:5]
        if len(sample_dirs) < 5:
            sample_dirs = all_dirs[:5]

        for idx, d in enumerate(sample_dirs, 1):
            j = db.query(Judgment).filter(Judgment.id == d.judgment_id).first()
            print(f"\n--- Direction Sample #{idx} ---")
            print(f"Judgment ID: {d.judgment_id} (Case: {j.case_number if j else 'N/A'}, Date: {j.judgment_date if j else 'N/A'})")
            print(f"Responsible Party: {d.responsible_party} [Type: {d.party_type}]")
            print(f"Extraction Method: {d.extraction_method}")
            print(f"Direction Type: {d.direction_type}")
            print(f"Action Mandated: {d.action}")
            print(f"Deadline Phrase (Verbatim): \"{d.deadline_phrase}\"")
            print(f"Verified Offsets: [{d.quote_start}:{d.quote_end}] (Length: {len(d.source_quote)} chars)")
            print(f"Confidence: {d.confidence}")
            print(f"Full Source Quote (Includes Deadline Sentence):\n\"{d.source_quote}\"")

    finally:
        db.close()


if __name__ == "__main__":
    run()
