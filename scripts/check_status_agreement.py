import json
from pathlib import Path
from backend.app.database import SessionLocal
from backend.app.models import Judgment, Direction

db = SessionLocal()
gold_files = list(Path('eval/gold').glob('*.json'))

status_counts = {}
for gf in sorted(gold_files):
    with open(gf, 'r', encoding='utf-8') as f:
        data = json.load(f)
    jid = data['judgment_id']
    dirs = db.query(Direction).filter(Direction.judgment_id == jid).all()
    for d in dirs:
        st = d.compliance_status or 'UNVERIFIED'
        status_counts[st] = status_counts.get(st, 0) + 1
        print(f"JID {jid} ({data['case_number']}): Dir {d.id} -> {st} (overdue={d.overdue_no_record}, contempt={d.contempt_filed})")

print("Status distribution in gold set:", status_counts)
db.close()

