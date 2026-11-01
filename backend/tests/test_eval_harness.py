"""
Tests for Phase 6 Evaluation Harness
Role: Verifies the integrity of the evaluation scripts, gold standard schemas, and eval API endpoint.
"""

import json
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.main import app
from eval.run_deadline_eval import evaluate_deadlines
from eval.run_linking_eval import evaluate_linking
from eval.run_extraction_eval import evaluate_extraction

client = TestClient(app)


def test_label_schema_exists():
    """Verify eval/label_schema.json exists and is valid JSON schema."""
    schema_file = Path("eval/label_schema.json")
    assert schema_file.exists(), "eval/label_schema.json must exist"
    with open(schema_file, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert schema.get("title") == "JudgmentGoldAnnotation"


def test_eval_scripts_report_no_human_gold_when_empty():
    """Verify eval scripts report 'no human gold labels available' when no human annotations exist."""
    res_ext = evaluate_extraction(gold_dir=Path("eval/gold"))
    assert res_ext.get("status") == "no human gold labels available"

    res_dl = evaluate_deadlines(cases_path=Path("eval/deadline_cases.json"))
    assert res_dl.get("status") == "no human gold labels available"


def test_deadline_resolution_evaluation_with_agent_generated():
    """Verify deadline math against generated benchmark set."""
    bench_file = Path("eval/agent_generated/deadline_cases.json")
    if bench_file.exists():
        results = evaluate_deadlines(cases_path=bench_file)
        assert results["total_test_cases"] == 25
        assert results["overall_exact_accuracy_pct"] == 100.0


def test_extraction_evaluation_with_agent_generated():
    """Verify extraction evaluation against generated benchmark set."""
    bench_dir = Path("eval/agent_generated/gold")
    if bench_dir.exists():
        results = evaluate_extraction(gold_dir=bench_dir)
        assert results["gold_files_count"] >= 10
        assert results["overall_extraction"]["f1"] >= 90.0


def test_linking_evaluation():
    """Verify citation-resolution achieves 100% rule adherence and zero temporal sanity violations."""
    results = evaluate_linking()
    assert results["temporal_sanity_violations"] == 0
    assert results["citation_resolution_rate_pct"] == 100.0
    assert results["total_contempt_orders"] == 59
    assert results["contempts_with_header_citations"] == 18
    assert results["linkable_contempts_with_earlier_order_in_db"] == 12
    assert results["correctly_linked_count"] == 12
    assert "Linkable pairs were ingested by targeted search" in results["note"]


def test_eval_results_api():
    """Verify GET /eval/results returns 200 with summary status."""
    res = client.get("/eval/results")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data

