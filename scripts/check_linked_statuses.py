from backend.app.database import SessionLocal
from backend.app.models import Judgment, Direction, CaseLink

db = SessionLocal()
links = db.query(CaseLink).all()
print(f'Total links: {len(links)}')
for l in links:
    j_from = db.query(Judgment).filter(Judgment.id == l.from_judgment_id).first()
    j_to = db.query(Judgment).filter(Judgment.id == l.to_judgment_id).first()
    if j_from:
        dirs = db.query(Direction).filter(Direction.judgment_id == j_from.id).all()
        dir_statuses = [d.compliance_status for d in dirs]
        print(f"Link {l.id}: {j_from.case_number} -> {j_to.case_number if j_to else '?'} | Dirs: {len(dirs)} | Statuses: {dir_statuses}")
db.close()

