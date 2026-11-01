"""
CLI Labelling Helper for Court-Order Compliance Radar
Role: Interactive tool to annotate real court judgments with ground-truth operative directions.
Data Flow: Database (Judgment) -> CLI display -> User annotation -> JSON Schema validation -> eval/gold/*.json
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.database import SessionLocal
from backend.app.models import Judgment


def clean_filename(text: str) -> str:
    """Sanitise case numbers for valid filenames."""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', text)


def normalize_ws(s: str) -> str:
    """Normalise whitespace for verbatim quote checking."""
    return re.sub(r'\s+', ' ', s or '').strip()


def validate_gold_data(data: dict) -> bool:
    """Simple validator conforming to eval/label_schema.json."""
    required_top = ["judgment_id", "case_number", "court", "judgment_date", "directions"]
    for field in required_top:
        if field not in data:
            print(f"[ERROR] Missing required field: {field}")
            return False

    if not isinstance(data["directions"], list):
        print("[ERROR] 'directions' must be a list")
        return False

    for idx, d in enumerate(data["directions"]):
        for req in ["responsible_party", "action", "source_quote"]:
            if not d.get(req):
                print(f"[ERROR] Direction #{idx+1} missing required field '{req}'")
                return False
    return True


def run_labeling(judgment_id: int, out_dir: Path):
    """Run interactive labelling loop for a single judgment."""
    db = SessionLocal()
    try:
        j = db.query(Judgment).filter(Judgment.id == judgment_id).first()
        if not j:
            print(f"[ERROR] Judgment with ID {judgment_id} not found in database.")
            return

        print("\n" + "=" * 80)
        print(f"ANNOTATING JUDGMENT #{j.id}: {j.case_number} ({j.court})")
        print(f"Date: {j.judgment_date} | Quality: {j.text_quality}")
        print(f"Parties: {j.petitioner} vs {j.respondent}")
        print("=" * 80)

        full_text = j.text or ""
        norm_text = normalize_ws(full_text)

        # Display operative portion (approx last 2500 chars where High Court operative orders reside)
        operative_excerpt = full_text[-2500:] if len(full_text) > 2500 else full_text
        print("\n--- OPERATIVE TEXT EXCERPT ---")
        print(operative_excerpt)
        print("--- END EXCERPT ---\n")

        directions = []
        dir_idx = 1

        while True:
            print(f"\n--- ENTER DIRECTION #{dir_idx} (or leave party empty to finish) ---")
            resp_party = input("Responsible Party: ").strip()
            if not resp_party:
                break

            party_type = input("Party Type [state/individual/corporate/court/other] (default: state): ").strip() or "state"
            dir_type = input("Direction Type [mandatory/prohibitory/declaratory/conditional] (default: mandatory): ").strip() or "mandatory"
            action = input("Action Ordered: ").strip()
            while not action:
                print("Action cannot be empty.")
                action = input("Action Ordered: ").strip()

            deadline = input("Deadline Phrase (leave empty if none): ").strip() or None
            
            # Verbatim source quote input
            while True:
                quote = input("Source Quote (exact verbatim text): ").strip()
                if not quote:
                    print("Source quote is required.")
                    continue
                if normalize_ws(quote) in norm_text:
                    print("[OK] Verbatim quote verified in judgment text.")
                    break
                else:
                    print("[WARNING] Quote was not found as a verbatim substring in judgment text.")
                    retry = input("Re-enter quote? (y/n, default: y): ").strip().lower()
                    if retry == 'n':
                        break

            directions.append({
                "direction_id": dir_idx,
                "responsible_party": resp_party,
                "party_type": party_type,
                "direction_type": dir_type,
                "action": action,
                "deadline_phrase": deadline,
                "source_quote": quote,
            })

            dir_idx += 1
            another = input("\nAdd another direction? (y/n, default: n): ").strip().lower()
            if another != 'y':
                break

        if not directions:
            print("[INFO] No directions recorded. Aborting save.")
            return

        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{j.id}_{clean_filename(j.case_number)}.json"
        out_file = out_dir / filename

        gold_doc = {
          "judgment_id": j.id,
          "case_number": j.case_number,
          "court": j.court,
          "judgment_date": j.judgment_date.isoformat() if j.judgment_date else None,
          "petitioner": j.petitioner,
          "respondent": j.respondent,
          "operative_text_excerpt": operative_excerpt[:500],
          "annotator_notes": f"Annotated via label_cli at {datetime.now().isoformat()}",
          "directions": directions,
        }

        if validate_gold_data(gold_doc):
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(gold_doc, f, indent=2, ensure_ascii=False)
            print(f"\n[SUCCESS] Saved {len(directions)} gold directions to: {out_file}")
        else:
            print("[ERROR] Gold document validation failed. File not saved.")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="CLI Labelling Helper for Court Judgments")
    parser.add_argument("--judgment-id", type=int, help="ID of the judgment to annotate")
    parser.add_argument("--list", action="store_true", help="List unlabelled judgments")
    parser.add_argument("--out-dir", type=str, default="eval/gold", help="Output directory for gold files")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)

    if args.list:
        db = SessionLocal()
        try:
            judgments = db.query(Judgment).filter(Judgment.text != None).limit(30).all()
            print(f"{'ID':<6} {'CASE NUMBER':<25} {'DATE':<12} {'STATUS':<10}")
            print("-" * 65)
            for j in judgments:
                clean_name = f"{j.id}_{clean_filename(j.case_number)}.json"
                is_done = (out_dir / clean_name).exists()
                done_marker = "[DONE]" if is_done else "[TODO]"
                print(f"{j.id:<6} {j.case_number:<25} {str(j.judgment_date):<12} {done_marker}")
        finally:
            db.close()
        return

    if args.judgment_id:
        run_labeling(args.judgment_id, out_dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
