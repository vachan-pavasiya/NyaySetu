"""Phase 4 Acceptance Report Script.

Computes and prints real numbers from compliance_radar.db for Phase 4:
a. Links found by link_type, signal and confidence.
b. How many links were rejected or downgraded by the temporal rule, with their case numbers.
c. Verdict distribution from the LLM classification, and how many of the contempt orders actually say something about compliance (not just 'filed').
d. Count of directions by status (COMPLIED, PENDING, UNVERIFIED) and how many have overdue_no_record.
e. 3 real direction timelines with the exact supporting quotes.
f. pytest pass/fail count.
"""

import sys
import subprocess
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import CaseLink, Direction, Evidence, Judgment, DirectionStatusHistory


def main():
    db = SessionLocal()

    print("=" * 80)
    print("PHASE 4 ACCEPTANCE REPORT: FOLLOW-UP LINKING & STATUS ENGINE")
    print("=" * 80)

    # ------------------------------------------------------------------------
    # a. Links found by link_type, signal and confidence
    # ------------------------------------------------------------------------
    links = db.query(CaseLink).all()
    print(f"\n--- [A] CASE LINKS FOUND (Total: {len(links)}) ---")

    by_type = Counter(l.link_type for l in links)
    by_signal = Counter(l.link_signal for l in links)
    by_confidence = Counter(l.link_confidence for l in links)

    print("\nBy Link Type:")
    for k, v in by_type.items():
        print(f"  {k}: {v}")

    print("\nBy Link Signal:")
    for k, v in by_signal.items():
        print(f"  {k}: {v}")

    print("\nBy Confidence Level:")
    for k, v in by_confidence.items():
        print(f"  {k}: {v}")

    print("\nAll Discovered Links in DB:")
    for l in links:
        j1 = db.query(Judgment).filter(Judgment.id == l.from_judgment_id).first()
        j2 = db.query(Judgment).filter(Judgment.id == l.to_judgment_id).first()
        c1 = j1.case_number if j1 else f"JID-{l.from_judgment_id}"
        c2 = j2.case_number if j2 else f"JID-{l.to_judgment_id}"
        d1 = j1.judgment_date if j1 else "None"
        d2 = j2.judgment_date if j2 else "None"
        print(f"  Link {l.id:02d}: {c1} ({d1}) -> {c2} ({d2}) | Conf: {l.link_confidence} | Signal: {l.link_signal}")
        if l.note:
            print(f"           Note: {l.note}")

    # ------------------------------------------------------------------------
    # b. How many links were rejected or downgraded by the temporal rule
    # ------------------------------------------------------------------------
    downgraded = [l for l in links if l.link_confidence == "LOW" or "Temporal conflict" in (l.note or "")]
    print(f"\n--- [B] TEMPORAL SANITY RULE DOWNGRADES / REJECTIONS (Total: {len(downgraded)}) ---")
    for l in downgraded:
        j1 = db.query(Judgment).filter(Judgment.id == l.from_judgment_id).first()
        j2 = db.query(Judgment).filter(Judgment.id == l.to_judgment_id).first()
        c1 = j1.case_number if j1 else f"JID-{l.from_judgment_id}"
        c2 = j2.case_number if j2 else f"JID-{l.to_judgment_id}"
        d1 = j1.judgment_date if j1 else "None"
        d2 = j2.judgment_date if j2 else "None"
        print(f"  Downgraded Link {l.id}: {c1} (Date: {d1}) -> {c2} (Date: {d2})")
        print(f"    Reason: {l.note}")

    # ------------------------------------------------------------------------
    # c. Verdict distribution from LLM classification
    # ------------------------------------------------------------------------
    evidences = db.query(Evidence).all()
    print(f"\n--- [C] VERDICT DISTRIBUTION FROM LLM CLASSIFICATION (Total Evaluations: {len(evidences)}) ---")

    verdict_counts = Counter(e.verdict for e in evidences)
    for k, v in verdict_counts.items():
        print(f"  {k}: {v}")

    # How many actually say something about compliance (not just 'filed' or procedural)
    compliance_substantive = sum(1 for e in evidences if e.verdict == "COMPLIANCE_SHOWN")
    non_compliance_alleged = sum(1 for e in evidences if e.verdict == "NON_COMPLIANCE_ALLEGED")
    procedural_or_default = sum(1 for e in evidences if e.verdict in ("DISMISSED_FOR_DEFAULT", "DISPOSED_NO_FINDING", "UNRELATED"))

    print("\nSubstantive Compliance Findings Breakdown:")
    print(f"  - Compliance affirmatively shown/recorded: {compliance_substantive}")
    print(f"  - Non-compliance actively alleged: {non_compliance_alleged}")
    print(f"  - Disposed without finding / dismissed for default / unrelated: {procedural_or_default}")

    # ------------------------------------------------------------------------
    # d. Count of directions by status and overdue_no_record
    # ------------------------------------------------------------------------
    directions = db.query(Direction).all()
    print(f"\n--- [D] STATUS MODEL DIRECTION DISTRIBUTION (Total Directions: {len(directions)}) ---")

    status_counts = Counter(d.compliance_status for d in directions)
    for s in ["COMPLIED", "PENDING", "UNVERIFIED"]:
        print(f"  {s}: {status_counts.get(s, 0)}")

    overdue_count = sum(1 for d in directions if d.overdue_no_record)
    contempt_filed_count = sum(1 for d in directions if d.contempt_filed or d.has_contempt_flag)
    contempt_dismissed_count = sum(1 for d in directions if d.contempt_dismissed_for_default)
    extension_count = sum(1 for d in directions if d.extension_sought)

    print("\nSecondary Flags:")
    print(f"  - overdue_no_record: {overdue_count}")
    print(f"  - contempt_filed: {contempt_filed_count}")
    print(f"  - contempt_dismissed_for_default: {contempt_dismissed_count}")
    print(f"  - extension_sought: {extension_count}")

    # ------------------------------------------------------------------------
    # e. 3 real direction timelines with exact supporting quotes
    # ------------------------------------------------------------------------
    print("\n--- [E] 3 REAL DIRECTION TIMELINES WITH EXACT SUPPORTING QUOTES ---")

    sample_dir_ids = [24, 29, 37]
    for did in sample_dir_ids:
        d = db.query(Direction).filter(Direction.id == did).first()
        if not d:
            continue
        j = d.judgment
        ev_list = db.query(Evidence).filter(Evidence.direction_id == d.id).all()
        history = db.query(DirectionStatusHistory).filter(DirectionStatusHistory.direction_id == d.id).all()

        print(f"\n" + "-" * 70)
        print(f"TIMELINE: Direction ID {d.id} | Case: {j.case_number} | Responsible Party: {d.responsible_party}")
        print(f"Action: {d.action}")
        print(f"Original Source Quote: \"{d.source_quote}\"")
        print(f"Pronounced Date: {j.judgment_date} | Deadline Window: {d.deadline_window_start} to {d.deadline_window_end} ({d.deadline_status})")
        print(f"Final Status: {d.compliance_status} | overdue_no_record: {d.overdue_no_record}")

        print("Chronological Timeline Events:")
        print(f"  1. [{j.judgment_date}] PRONOUNCEMENT: High Court issued direction in {j.case_number}.")
        if d.deadline_window_end:
            print(f"  2. [{d.deadline_window_end}] DEADLINE_WINDOW_END: Prescribed period expired ({d.deadline_phrase}).")

        for idx, ev in enumerate(ev_list, start=3):
            later_j = db.query(Judgment).filter(Judgment.id == ev.source_judgment_id).first()
            print(f"  {idx}. [{ev.source_date}] FOLLOW-UP PROCEEDING ({later_j.case_number if later_j else 'Follow-up'}):")
            print(f"      Verdict: {ev.verdict} (Verified: {ev.verified})")
            print(f"      Exact Quote: \"{ev.supporting_quote}\"")
            print(f"      Reasoning: {ev.reasoning}")

        if history:
            last_hist = history[-1]
            print(f"  Audit History: [{last_hist.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {last_hist.old_status} -> {last_hist.new_status} | Reason: {last_hist.reason}")

    db.close()

    # ------------------------------------------------------------------------
    # f. Pytest run
    # ------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("--- [F] RUNNING PYTEST SUITE ---")
    print("=" * 80)
    pytest_res = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests/", "-q"],
        capture_output=True,
        text=True,
    )
    print(pytest_res.stdout)
    if pytest_res.stderr:
        print(pytest_res.stderr)


if __name__ == "__main__":
    main()

