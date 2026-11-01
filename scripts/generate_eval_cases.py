"""Generate Gold Eval Case file for Deadline Resolution Evaluation.

Role: Extracts 20+ real deadline phrases from ingested judgments in SQLite,
      creating eval/deadline_cases.json with blank expected fields for manual labelling.
Data flow: compliance_radar.db -> eval/deadline_cases.json.
"""

import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "compliance_radar.db"
EVAL_PATH = Path(__file__).resolve().parent.parent / "eval" / "deadline_cases.json"


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get extracted directions
    c.execute("""
        SELECT d.id, d.judgment_id, j.case_number, j.judgment_date, d.deadline_phrase
        FROM directions d
        JOIN judgments j ON d.judgment_id = j.id
        WHERE d.deadline_phrase IS NOT NULL
    """)
    dir_rows = c.fetchall()

    # Get judgments text
    c.execute("SELECT id, case_number, judgment_date, text FROM judgments WHERE text IS NOT NULL")
    j_rows = c.fetchall()

    patterns = [
        r"within\s+(?:a\s+period\s+of\s+|the\s+period\s+of\s+)?(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|thirty|forty\s+five|sixty)\s+(?:days|weeks|months|working\s+days)(?:\s+(?:from|of)\s+[^\.\n;]{1,60})?",
        r"from\s+the\s+date\s+of\s+(?:this\s+order|the\s+order|today|receipt[^\.\n;]{1,60})",
        r"(?:forthwith|immediately|expeditiously|as\s+expeditiously\s+as\s+possible)",
        r"(?:on\s+or\s+before|before|by)\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        r"(?:next\s+date\s+of\s+hearing|next\s+hearing)",
    ]

    seen = set()
    cases = []

    # 1. Existing extracted directions
    for d_id, j_id, case, j_date, phrase in dir_rows:
        norm = " ".join(phrase.split())
        if norm not in seen:
            seen.add(norm)
            cases.append({
                "case_id": len(cases) + 1,
                "judgment_id": j_id,
                "case_number": case,
                "judgment_date": str(j_date),
                "deadline_phrase": norm,
                "expected_anchor_type": "",
                "expected_offset_value": None,
                "expected_offset_unit": "",
                "expected_window_start": "",
                "expected_window_end": "",
                "expected_is_estimated": None,
                "expected_status": "",
                "eval_source": "extracted_direction",
                "notes": "Real extracted direction phrase from DB",
            })

    # 2. Add phrases from text across all 150 judgments
    for j_id, case, j_date, text in j_rows:
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                norm = " ".join(m.group(0).split())
                if norm not in seen and 3 < len(norm) < 95:
                    seen.add(norm)
                    cases.append({
                        "case_id": len(cases) + 1,
                        "judgment_id": j_id,
                        "case_number": case,
                        "judgment_date": str(j_date),
                        "deadline_phrase": norm,
                        "expected_anchor_type": "",
                        "expected_offset_value": None,
                        "expected_offset_unit": "",
                        "expected_window_start": "",
                        "expected_window_end": "",
                        "expected_is_estimated": None,
                        "expected_status": "",
                        "eval_source": "judgment_text_corpus",
                        "notes": "Real phrase from judgment text corpus",
                    })
                if len(cases) >= 25:
                    break
            if len(cases) >= 25:
                break
        if len(cases) >= 25:
            break

    EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)

    print(f"Generated {len(cases)} real gold eval cases in {EVAL_PATH}")


if __name__ == "__main__":
    main()

