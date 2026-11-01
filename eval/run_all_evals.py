"""
Master Evaluation Suite Runner
Role: Executes extraction, deadline, and linking evaluation harnesses and writes eval/results/latest.json.
Data Flow: eval/run_extraction_eval.py + eval/run_deadline_eval.py + eval/run_linking_eval.py -> eval/results/latest.json
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from eval.run_extraction_eval import evaluate_extraction
from eval.run_deadline_eval import evaluate_deadlines
from eval.run_linking_eval import evaluate_linking


def run_all_evaluations() -> dict:
    """Run all evaluation suites and produce latest.json."""
    print("\n" + "#" * 80)
    print("STARTING COURT-ORDER COMPLIANCE RADAR FULL EVALUATION SUITE")
    print("#" * 80)

    # 1. Extraction Eval
    extraction_results = evaluate_extraction()

    # 2. Deadline Eval
    deadline_results = evaluate_deadlines()

    # 3. Linking Eval
    linking_results = evaluate_linking()

    results_dir = Path("eval/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    latest_file = results_dir / "latest.json"

    consolidated = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "gold_files_count": extraction_results.get("gold_files_count", 0),
            "overall_extraction_f1": extraction_results.get("overall_extraction", {}).get("f1", 0.0),
            "overall_extraction_precision": extraction_results.get("overall_extraction", {}).get("precision", 0.0),
            "overall_extraction_recall": extraction_results.get("overall_extraction", {}).get("recall", 0.0),
            "hallucination_rate_pct": extraction_results.get("hallucination_rate_pct", 0.0),
            "deadline_exact_accuracy_pct": deadline_results.get("overall_exact_accuracy_pct", 0.0),
            "deadline_cases_tested": deadline_results.get("total_test_cases", 0),
            "linking_f1_pct": linking_results.get("linking_f1_pct", 0.0),
            "linking_precision_pct": linking_results.get("linking_precision_pct", 0.0),
            "linking_recall_pct": linking_results.get("linking_recall_pct", 0.0),
            "temporal_sanity_violations": linking_results.get("temporal_sanity_violations", 0),
        },
        "extraction": extraction_results,
        "deadline_resolution": deadline_results,
        "linking": linking_results,
    }

    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, indent=2, ensure_ascii=False)

    print(f"[SUCCESS] Consolidated evaluation results written to: {latest_file}\n")
    return consolidated


if __name__ == "__main__":
    run_all_evaluations()

