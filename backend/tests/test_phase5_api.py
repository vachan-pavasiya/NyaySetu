"""Unit tests for Phase 5 aggregation APIs, department cleaner, calendar, and dashboard.

Tests:
1. Deterministic department name cleaner on Indian High Court designations and authorities.
2. GET /dashboard response structure, counts, top departments, and freshness.
3. GET /ledger pagination, cleaned department output, and query filters.
4. GET /calendar month filtering of direction deadline window ends.
5. GET /export.csv filtered CSV streaming.
"""

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.pipeline.clean_department import clean_department_name


@pytest.fixture
def client():
    return TestClient(app)


def test_clean_department_name():
    """Verify deterministic cleaning of responsible party and department strings."""
    cases = [
        ("The Director of Pension, Provident Fund and Group Insurance and the concerned Treasury Officer",
         "Director of Pension, Provident Fund & Group Insurance"),
        ("District Inspector of Schools (SE), Malda", "District Inspector of Schools (SE)"),
        ("District Inspector of School (SE)", "District Inspector of Schools (SE)"),
        ("District Inspector of Schools (P.E.)", "District Inspector of Schools (PE)"),
        ("Superintendent of Police, Ranaghat Police District", "Superintendent of Police"),
        ("Commissioner of School Education, Government of West Bengal", "Commissioner of School Education"),
        ("Chief Judicial Magistrate, Barasat", "Chief Judicial Magistrate"),
        ("learned advocate for the petitioner", "Advocate for Petitioner"),
        ("Aforesaid respondent", "Respondent Authority"),
        ("State of West Bengal through Principal Secretary...", "State of West Bengal"),
        ("Trial Court", "Trial Court"),
        ("CESC Limited", "CESC Limited"),
        ("Baduria Police Station", "Baduria Police Station"),
    ]
    for raw, expected in cases:
        cleaned = clean_department_name(raw)
        assert cleaned == expected, f"Expected {expected!r} for raw {raw!r}, got {cleaned!r}"


def test_dashboard_endpoint(client):
    """Verify GET /dashboard returns comprehensive aggregations with zero mock data."""
    res = client.get("/dashboard")
    assert res.status_code == 200
    data = res.json()

    # Required fields
    assert "status_counts" in data
    assert "COMPLIED" in data["status_counts"]
    assert "PENDING" in data["status_counts"]
    assert "UNVERIFIED" in data["status_counts"]
    assert "overdue_no_record_count" in data
    assert "contempt_filed_count" in data
    assert "evidence_strength_split" in data
    assert "deadline_bucket_counts" in data
    assert "top_departments" in data
    assert len(data["top_departments"]) <= 10
    assert "directions_due_next_30_days" in data
    assert "dataset_freshness" in data
    assert "latest_judgment_date" in data["dataset_freshness"]
    assert "link_stats" in data
    assert "recent_pipeline_runs" in data
    assert "disclaimer" in data
    assert "unverified_note" in data


def test_ledger_pagination_and_cleaned_departments(client):
    """Verify GET /ledger pagination, page calculation, and cleaned department inclusion."""
    res = client.get("/ledger?page=1&page_size=5")
    assert res.status_code == 200
    data = res.json()

    assert data["page"] == 1
    assert data["page_size"] == 5
    assert data["total"] > 0
    assert data["total_pages"] >= 1
    assert len(data["items"]) <= 5

    item0 = data["items"][0]
    assert "cleaned_department" in item0
    assert "responsible_party" in item0
    assert "judgment_link" in item0
    assert item0["judgment_link"].startswith("/judgments/")


def test_calendar_endpoint(client):
    """Verify GET /calendar returns directions matching month."""
    res = client.get("/calendar?month=2023-10")
    assert res.status_code == 200
    data = res.json()

    assert data["month"] == "2023-10"
    assert "total_directions" in data
    assert "status_summary" in data
    assert "directions" in data
    for d in data["directions"]:
        assert d["deadline_window_end"].startswith("2023-10")
        assert "cleaned_department" in d
        assert "judgment_link" in d


def test_export_csv_endpoint(client):
    """Verify GET /export.csv returns CSV with expected columns."""
    res = client.get("/export.csv?status=COMPLIED")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    csv_text = res.text
    assert "direction_id" in csv_text
    assert "cleaned_department" in csv_text
    assert "compliance_status" in csv_text

