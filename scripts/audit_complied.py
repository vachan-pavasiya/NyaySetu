"""Audit script for COMPLIED directions.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import Direction, Evidence, Judgment, CaseLink
from backend.pipeline.verify import normalize_whitespace

db = SessionLocal()
complied = db.query(Direction).filter(Direction.compliance_status == 'COMPLIED').all()
print(f"Total COMPLIED directions: {len(complied)}")

for d in complied:
    j = db.query(Judgment).filter(Judgment.id == d.judgment_id).first()
    evs = db.query(Evidence).filter(Evidence.direction_id == d.id).all()
    for ev in evs:
        later_j = db.query(Judgment).filter(Judgment.id == ev.source_judgment_id).first()
        is_verbatim = False
        if later_j and later_j.text and ev.supporting_quote:
            norm_q = normalize_whitespace(ev.supporting_quote).lower().strip()
            norm_t = normalize_whitespace(later_j.text).lower().strip()
            is_verbatim = norm_q in norm_t

        print(f"Dir {d.id} | Writ: {j.case_number} ({j.judgment_date}) | Contempt: {later_j.case_number if later_j else None} ({later_j.judgment_date if later_j else None})")
        print(f"   Action: {d.action[:60]}...")
        print(f"   Verdict: {ev.verdict} | Verbatim in Contempt Order: {is_verbatim}")
        print(f"   Quote: {ev.supporting_quote}")
        print(f"   Full Contempt Text:\n{(later_j.text or '').strip()}\n")
        print("=" * 80)

db.close()
