"""Analyze contempt petitions and extract cited underlying cases.

Role: Extracts the earlier writ/case cited by each of the 48 contempt petitions in SQLite,
      and verifies whether the cited case exists in the judgments table.
Data flow: compliance_radar.db (contempt texts) -> regex extraction -> match against judgments -> report.
"""

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "compliance_radar.db"


def normalize_case(s: str) -> str:
    """Normalizes case number representations, e.g. 'WPA 13757 of 2004' -> 'WPA/13757/2004'."""
    s = s.strip()
    m = re.search(
        r"(WPA|W\.P\.A\.|W\.P\.|WP|WP\.ST|WPLRT|WP\.TT|WPCRC|CPAN)\s*(?:No\.?)?\s*(\d+)\s*(?:of|/)\s*(\d{4})",
        s,
        re.IGNORECASE,
    )
    if m:
        c_type = m.group(1).upper().replace(".", "").strip()
        if c_type == "WP":
            c_type = "WPA"
        return f"{c_type}/{m.group(2)}/{m.group(3)}"
    return s


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get all contempt petitions
    c.execute("""
        SELECT id, case_number, text
        FROM judgments
        WHERE case_number LIKE 'CPAN%' OR case_number LIKE 'WPCRC%'
        ORDER BY id ASC
    """)
    contempt_rows = c.fetchall()

    # Get all case numbers in judgments table
    c.execute("SELECT id, case_number FROM judgments")
    all_cases = dict(c.fetchall())

    # Build lookup maps for case numbers
    exact_case_map = {}
    num_year_map = {}
    for j_id, case_num in all_cases.items():
        if case_num:
            norm = normalize_case(case_num)
            exact_case_map[norm] = j_id
            parts = norm.split("/")
            if len(parts) == 3:
                num_year_map[(parts[1], parts[2])] = (j_id, norm)

    # Patterns for extracting cited writ from contempt text
    patterns = [
        r"(?:In|in)\s*\n*\s*(W\.?P\.?A?\.?(?:\([A-Z]+\))?\.?\s*(?:No\.?)?\s*\d+\s*(?:of|/)\s*\d{4})",
        r"(?:in|arising out of|passed in|compliance of)\s+(W\.?P\.?A?\.?(?:\([A-Z]+\))?\.?\s*(?:No\.?)?\s*\d+\s*(?:of|/)\s*\d{4})",
        r"(W\.?P\.?A?\.?(?:\([A-Z]+\))?\s*(?:No\.?)?\s*\d+\s+of\s+\d{4})",
        r"(W\.?P\.?\s*(?:No\.?)?\s*\d+\s*\([Ww]\)\s*(?:of|/)\s*\d{4})",
    ]

    results = []
    for c_id, c_case, text in contempt_rows:
        found_cited = None
        matched_snippet = None
        if text:
            # Check preamble / header (first 3000 chars)
            header_text = text[:3000]
            for pat in patterns:
                m = re.search(pat, header_text, re.IGNORECASE)
                if m:
                    raw_cited = m.group(1)
                    norm_cited = normalize_case(raw_cited)
                    if norm_cited != c_case:
                        found_cited = norm_cited
                        matched_snippet = " ".join(m.group(0).split())
                        break

        # Check DB match
        exists_in_db = False
        matched_j_id = None
        matched_case = None

        if found_cited:
            if found_cited in exact_case_map:
                exists_in_db = True
                matched_j_id = exact_case_map[found_cited]
                matched_case = found_cited
            else:
                parts = found_cited.split("/")
                if len(parts) == 3 and (parts[1], parts[2]) in num_year_map:
                    exists_in_db = True
                    matched_j_id, matched_case = num_year_map[(parts[1], parts[2])]

        results.append({
            "contempt_id": c_id,
            "contempt_case": c_case,
            "cited_snippet": matched_snippet,
            "cited_case": found_cited,
            "exists_in_db": exists_in_db,
            "matched_judgment_id": matched_j_id,
            "matched_case": matched_case,
        })

    with_cited = [r for r in results if r["cited_case"]]
    in_db = [r for r in results if r["exists_in_db"]]

    print("=" * 65)
    print("=== CONTEMPT PETITION CITATION EXTRACTION RESULTS ===")
    print("=" * 65)
    print(f"Total Contempt Petitions in DB: {len(contempt_rows)}")
    print(f"Contempt Petitions with Extracted Primary Writ Citation: {len(with_cited)} / {len(contempt_rows)} ({100.0 * len(with_cited) / len(contempt_rows):.1f}%)")
    print(f"Cited Cases That Exist in Judgments Table: {len(in_db)}")

    if in_db:
        print("\n--- MATCHED CASES IN JUDGMENTS TABLE ---")
        for r in in_db:
            print(f"  Contempt {r['contempt_case']} (ID {r['contempt_id']}) -> Cited: {r['cited_case']} -> Matched Judgment ID {r['matched_judgment_id']} ({r['matched_case']})")

    print("\n--- 5 EXAMPLES OF EXTRACTED CITATIONS ---")
    for idx, r in enumerate(with_cited[:5], 1):
        status_str = f"EXISTS in DB (Judgment ID {r['matched_judgment_id']})" if r['exists_in_db'] else "NOT in DB (historical order not ingested)"
        print(f"Example {idx}:")
        print(f"  Contempt Petition: {r['contempt_case']} (Judgment ID {r['contempt_id']})")
        print(f"  Cited Earlier Case: {r['cited_case']}")
        print(f"  Text Snippet: \"{r['cited_snippet']}\"")
        print(f"  Database Match Status: {status_str}")
        print()


if __name__ == "__main__":
    main()

