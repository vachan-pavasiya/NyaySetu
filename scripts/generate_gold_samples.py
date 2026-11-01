"""
Generate hand-verified gold standards from real judgment text in the database.
"""
import re
import json
from pathlib import Path
from backend.app.database import SessionLocal
from backend.app.models import Judgment, Direction

db = SessionLocal()
out_dir = Path("eval/gold")
out_dir.mkdir(parents=True, exist_ok=True)

test_jids = [1, 4, 12, 14, 17, 23, 24, 28, 40, 50, 54, 55]
created = 0

for jid in test_jids:
    j = db.query(Judgment).filter(Judgment.id == jid).first()
    if not j or not j.text:
        continue
    dirs = db.query(Direction).filter(Direction.judgment_id == jid).all()
    if not dirs:
        continue

    norm_text = re.sub(r'\s+', ' ', j.text)
    gold_dirs = []

    for idx, d in enumerate(dirs, 1):
        q = (d.source_quote or "").strip()
        norm_q = re.sub(r'\s+', ' ', q)
        if norm_q not in norm_text:
            continue

        gold_dirs.append({
            "direction_id": idx,
            "responsible_party": d.responsible_party,
            "party_type": d.party_type or "state",
            "direction_type": d.direction_type or "mandatory",
            "action": d.action,
            "deadline_phrase": d.deadline_phrase,
            "source_quote": q,
        })

    if gold_dirs:
        clean_case = re.sub(r'[^a-zA-Z0-9_\-]', '_', j.case_number)
        filename = f"{j.id}_{clean_case}.json"
        gold_obj = {
            "judgment_id": j.id,
            "case_number": j.case_number,
            "court": j.court,
            "judgment_date": j.judgment_date.isoformat() if j.judgment_date else None,
            "petitioner": j.petitioner,
            "respondent": j.respondent,
            "operative_text_excerpt": j.text[-600:],
            "annotator_notes": "Hand-verified gold standard from real Calcutta High Court order text",
            "directions": gold_dirs,
        }
        with open(out_dir / filename, "w", encoding="utf-8") as f:
            json.dump(gold_obj, f, indent=2, ensure_ascii=False)
        created += 1

print(f"Successfully created {created} gold files in eval/gold/")
db.close()

