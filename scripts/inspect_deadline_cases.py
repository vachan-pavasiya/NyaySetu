import json
from datetime import date
from backend.pipeline.deadline import resolve_deadline

with open('eval/deadline_cases.json', encoding='utf-8') as f:
    cases = json.load(f)

for c in cases:
    j_date = date.fromisoformat(c['judgment_date'])
    res = resolve_deadline(c['deadline_phrase'], j_date)
    print(f"ID {c['case_id']}: '{c['deadline_phrase']}' -> anchor={res.anchor_type} offset={res.offset_value} {res.offset_unit} window=[{res.window_start} -> {res.window_end}] status={res.deadline_status}")
