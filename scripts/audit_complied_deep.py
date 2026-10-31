import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import Direction, Evidence, Judgment, CaseLink
from backend.pipeline.verify import normalize_whitespace

db = SessionLocal()
complied = db.query(Direction).filter(Direction.compliance_status == 'COMPLIED').all()
print(f"Total COMPLIED directions: {len(complied)}\n")

for d in complied:
    ev = db.query(Evidence).filter(Evidence.direction_id == d.id).first()
    j = d.judgment
    later_j = db.query(Judgment).filter(Judgment.id == ev.source_judgment_id).first() if ev else None
    
    # Check verbatim match
    is_verbatim = False
    if later_j and later_j.text and ev and ev.supporting_quote:
        norm_q = normalize_whitespace(ev.supporting_quote).lower().strip()
        norm_t = normalize_whitespace(later_j.text).lower().strip()
        is_verbatim = norm_q in norm_t

    c_num = later_j.case_number if later_j else "None"
    print(f"Dir {d.id} | Writ: {j.case_number} ({j.judgment_date}) -> Contempt: {c_num}")
    print(f"  Action: {d.action}")
    print(f"  LLM Verdict: {ev.verdict if ev else 'None'}")
    print(f"  Supporting Quote: \"{ev.supporting_quote if ev else 'None'}\"")
    print(f"  Verbatim in Contempt Order: {is_verbatim}")
    print(f"  Contempt Order Final Ruling:")
    lines = [l.strip() for l in (later_j.text or '').split('\n') if l.strip()]
    for line in lines[-5:]:
        print(f"    {line}")
    print("-" * 80)

db.close()

