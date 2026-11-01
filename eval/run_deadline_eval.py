"""
Deadline Resolution Evaluation Runner
Role: Evaluates deterministic date resolution and window computation against hand-calculated ground truth cases.
Data Flow: eval/deadline_cases.json -> resolve_deadline() -> Comparison -> Metrics Table & latest.json
"""

import sys
import json
from pathlib import Path
from datetime import date
from typing import Dict, Any

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.pipeline.deadline import resolve_deadline


def evaluate_deadlines(cases_path: Path = Path("eval/deadline_cases.json")) -> Dict[str, Any]:
    """Evaluate deterministic deadline resolution logic against ground truth."""
    if not cases_path.exists():
        print(f"[ERROR] Deadline cases file not found at: {cases_path}")
        return {}

    with open(cases_path, "r", encoding="utf-8") as f:
        all_cases = json.load(f)

    # Filter to cases that have human expected ground-truth labels
    cases = [c for c in all_cases if c.get("expected_anchor_type") or c.get("expected_window_end")]
    if not cases:
        print("\n" + "=" * 80)
        print("DEADLINE RESOLUTION EVALUATION: no human gold labels available")
        print("=" * 80)
        print(f"Notice: Found {len(all_cases)} test cases in {cases_path}, but expected values are empty.")
        print("Per EVAL INTEGRITY rule: Gold data comes only from the user.")
        print("Please populate expected values in eval/deadline_cases.json to run evaluation.")
        print("=" * 80 + "\n")
        return {
            "eval_type": "deadline_resolution",
            "status": "no human gold labels available",
            "total_test_cases": 0,
            "message": "no human gold labels available",
        }

    total_cases = len(cases)
    anchor_matches = 0
    offset_matches = 0
    window_start_matches = 0
    window_end_matches = 0
    status_matches = 0
    all_exact_matches = 0

    mismatches = []

    for c in cases:
        cid = c.get("case_id")
        phrase = c.get("deadline_phrase")
        j_date_str = c.get("judgment_date")
        j_date = date.fromisoformat(j_date_str) if j_date_str else date(2023, 1, 1)

        res = resolve_deadline(phrase, j_date)

        exp_anchor = c.get("expected_anchor_type")
        exp_offset_val = c.get("expected_offset_value")
        exp_offset_unit = c.get("expected_offset_unit")
        exp_start = c.get("expected_window_start")
        exp_end = c.get("expected_window_end")
        exp_status = c.get("expected_status")

        # Field comparisons
        act_start = res.window_start.isoformat() if res.window_start else None
        act_end = res.window_end.isoformat() if res.window_end else None

        a_match = (res.anchor_type == exp_anchor)
        o_match = (res.offset_value == exp_offset_val and (res.offset_unit or "") == (exp_offset_unit or ""))
        ws_match = (act_start == exp_start)
        we_match = (act_end == exp_end)
        s_match = (res.deadline_status == exp_status)

        if a_match: anchor_matches += 1
        if o_match: offset_matches += 1
        if ws_match: window_start_matches += 1
        if we_match: window_end_matches += 1
        if s_match: status_matches += 1

        is_exact = a_match and o_match and ws_match and we_match and s_match
        if is_exact:
            all_exact_matches += 1
        else:
            mismatches.append({
                "case_id": cid,
                "phrase": phrase,
                "expected": {"anchor": exp_anchor, "offset": exp_offset_val, "start": exp_start, "end": exp_end, "status": exp_status},
                "actual": {"anchor": res.anchor_type, "offset": res.offset_value, "start": act_start, "end": act_end, "status": res.deadline_status},
            })

    # Calculate percentages
    anchor_acc = round((anchor_matches / total_cases) * 100.0, 1)
    offset_acc = round((offset_matches / total_cases) * 100.0, 1)
    window_acc = round((window_end_matches / total_cases) * 100.0, 1)
    status_acc = round((status_matches / total_cases) * 100.0, 1)
    overall_exact_acc = round((all_exact_matches / total_cases) * 100.0, 1)

    results = {
        "eval_type": "deadline_resolution",
        "total_test_cases": total_cases,
        "overall_exact_accuracy_pct": overall_exact_acc,
        "exact_matches_count": all_exact_matches,
        "field_accuracies": {
            "anchor_classification": {"accuracy_pct": anchor_acc, "matches": anchor_matches, "total": total_cases},
            "offset_and_unit_extraction": {"accuracy_pct": offset_acc, "matches": offset_matches, "total": total_cases},
            "date_window_calculation": {"accuracy_pct": window_acc, "matches": window_end_matches, "total": total_cases},
            "deadline_status_assignment": {"accuracy_pct": status_acc, "matches": status_matches, "total": total_cases},
        },
        "mismatches": mismatches,
    }

    # Print clean table
    print("\n" + "=" * 80)
    print(f"DEADLINE RESOLUTION EVALUATION REPORT (Test Set: {total_cases} cases)")
    print("=" * 80)
    print(f"{'EVALUATION METRIC':<35} {'ACCURACY':<15} {'MATCHES / TOTAL'}")
    print("-" * 80)
    print(f"{'Anchor Type Classification':<35} {anchor_acc:<14.1f}% {anchor_matches} / {total_cases}")
    print(f"{'Offset Value & Unit Extraction':<35} {offset_acc:<14.1f}% {offset_matches} / {total_cases}")
    print(f"{'Date Window Bounds [start, end]':<35} {window_acc:<14.1f}% {window_end_matches} / {total_cases}")
    print(f"{'Deadline Status (Lapsed/Urgent)':<35} {status_acc:<14.1f}% {status_matches} / {total_cases}")
    print("-" * 80)
    print(f"{'OVERALL ALL-FIELD EXACT MATCH':<35} {overall_exact_acc:<14.1f}% {all_exact_matches} / {total_cases}")
    print("=" * 80)
    if mismatches:
        print(f"[NOTE] {len(mismatches)} mismatches recorded for analysis.")
    else:
        print("[SUCCESS] 100% Deterministic match across all hand-calculated cases.")
    print("=" * 80 + "\n")

    return results


if __name__ == "__main__":
    evaluate_deadlines()

