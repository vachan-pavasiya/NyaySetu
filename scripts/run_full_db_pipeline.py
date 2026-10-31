"""Batch runner for Phase 2, Phase 3, and Phase 4 over all remaining unanalysed judgments.

Role: Sequentially runs:
      1. Phase 2 (segment, extract, verify with feedback retries)
      2. Phase 3 (deterministic deadline resolution and dedup)
      3. Phase 4 (follow-up order linking, Gemini evidence classification, status engine)
      Uses the SQLite LLM cache throughout.
"""

import sys
import time
from pathlib import Path
from collections import Counter
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import Judgment, OperativeSegment, Direction, CaseLink, Evidence
from backend.pipeline.agent import ComplianceExtractionAgent
from backend.pipeline.extract_directions import get_call_metrics, reset_call_metrics
from backend.pipeline.linking import run_full_linking_and_status_pipeline


def main():
    total_start_time = time.perf_counter()
    db = SessionLocal()

    # Identify unanalysed judgments
    already_analyzed_ids = set(
        r[0] for r in db.query(OperativeSegment.judgment_id).distinct()
    )
    unanalysed_judgments = (
        db.query(Judgment)
        .filter(Judgment.status == "INGESTED", ~Judgment.id.in_(already_analyzed_ids))
        .order_by(Judgment.id.asc())
        .all()
    )

    total_to_process = len(unanalysed_judgments)
    print("=" * 80)
    print(f"RUNNING PHASES 2, 3, AND 4 OVER {total_to_process} UNANALYSED JUDGMENTS")
    print("=" * 80)

    # Track metrics
    analyzed_count = 0
    directions_extracted_in_this_run = 0
    judgment_times: List[float] = []
    gemini_errors_encountered: List[str] = []

    # Reset call metrics for this run
    reset_call_metrics()

    # Process each unanalysed judgment through Phase 2 & 3
    for idx, j in enumerate(unanalysed_judgments, start=1):
        t0 = time.perf_counter()
        print(f"[{idx}/{total_to_process}] Analyzing Judgment ID {j.id} ({j.case_number or 'No Case Num'} - {j.judgment_date})...", end=" ", flush=True)

        try:
            agent = ComplianceExtractionAgent(j)
            result = agent.run(db)
            dur = time.perf_counter() - t0
            judgment_times.append(dur)
            analyzed_count += 1

            dirs_count = result.get("total_directions", 0)
            directions_extracted_in_this_run += dirs_count

            has_dirs = result.get("has_directions", False)
            if has_dirs:
                print(f"DONE in {dur:.2f}s -> {dirs_count} directions extracted.")
            else:
                print(f"DONE in {dur:.2f}s -> 0 directions (procedural/no directions).")

        except Exception as exc:
            dur = time.perf_counter() - t0
            judgment_times.append(dur)
            err_str = f"Judgment {j.id} ({j.case_number}): {str(exc)}"
            gemini_errors_encountered.append(err_str)
            print(f"FAILED in {dur:.2f}s -> Error: {exc}")

    # Now run Phase 4 Linking and Status over the entire DB
    print("\n" + "=" * 80)
    print("RUNNING PHASE 4: FOLLOW-UP LINKING & DETERMINISTIC STATUS ENGINE OVER FULL DB")
    print("=" * 80)

    t_p4 = time.perf_counter()
    phase4_results = run_full_linking_and_status_pipeline(db)
    dur_p4 = time.perf_counter() - t_p4
    print(f"Phase 4 pipeline completed in {dur_p4:.2f}s.")

    # ------------------------------------------------------------------------
    # FINAL CONSOLIDATED REPORT
    # ------------------------------------------------------------------------
    total_time = time.perf_counter() - total_start_time

    # Database state
    all_judgments_count = db.query(Judgment).count()
    all_directions = db.query(Direction).all()
    all_links = db.query(CaseLink).all()
    all_evidence = db.query(Evidence).all()

    # Direction statuses & flags
    status_counter = Counter(d.compliance_status for d in all_directions)
    overdue_count = sum(1 for d in all_directions if d.overdue_no_record)
    contempt_filed_count = sum(1 for d in all_directions if d.contempt_filed or d.has_contempt_flag)
    contempt_dismissed_count = sum(1 for d in all_directions if d.contempt_dismissed_for_default)
    extension_sought_count = sum(1 for d in all_directions if d.extension_sought)

    # Links by type
    link_type_counter = Counter(l.link_type for l in all_links)
    link_signal_counter = Counter(l.link_signal for l in all_links)
    link_conf_counter = Counter(l.link_confidence for l in all_links)

    # Call metrics
    metrics = get_call_metrics()

    print("\n" + "=" * 80)
    print("FINAL EXECUTION REPORT: FULL DATABASE PIPELINE COMPLETE")
    print("=" * 80)

    print(f"1. Judgments Analysed in this run: {analyzed_count} / {total_to_process}")
    print(f"   Total Judgments in DB: {all_judgments_count}")
    print(f"   Avg time per judgment: {sum(judgment_times) / max(len(judgment_times), 1):.2f}s")

    print(f"\n2. Total Directions in DB: {len(all_directions)}")
    print(f"   (Extracted in this run: {directions_extracted_in_this_run})")

    print("\n3. Directions per Headline Status:")
    for st in ["COMPLIED", "PENDING", "UNVERIFIED"]:
        count = status_counter.get(st, 0)
        pct = (count / max(len(all_directions), 1)) * 100
        print(f"   - {st}: {count} ({pct:.1f}%)")

    print("\n   Secondary Flags Breakdown:")
    print(f"   - overdue_no_record: {overdue_count}")
    print(f"   - contempt_filed: {contempt_filed_count}")
    print(f"   - contempt_dismissed_for_default: {contempt_dismissed_count}")
    print(f"   - extension_sought: {extension_sought_count}")

    print(f"\n4. Case Links Discovered: {len(all_links)}")
    print("   Links per Type:")
    for k, v in link_type_counter.items():
        print(f"   - {k}: {v}")

    print("   Links per Signal:")
    for k, v in link_signal_counter.items():
        print(f"   - {k}: {v}")

    print("   Links per Confidence:")
    for k, v in link_conf_counter.items():
        print(f"   - {k}: {v}")

    print(f"\n5. LLM Call Metrics & Cache Usage:")
    print(f"   - Live API calls: {metrics.get('live_calls', 0)}")
    print(f"   - Cached calls: {metrics.get('cached_calls', 0)}")
    print(f"   - Fallback calls: {metrics.get('fallback_calls', 0)}")
    print(f"   - Gemini errors encountered: {len(gemini_errors_encountered)}")
    if gemini_errors_encountered:
        for err in gemini_errors_encountered[:5]:
            print(f"     * {err}")

    print(f"\n6. Total Time: {total_time:.2f} seconds ({total_time / 60.0:.2f} minutes)")
    print("=" * 80)

    db.close()


if __name__ == "__main__":
    main()

