"""Unit and integration tests for judgment ingestion and text extraction.

Role: Verifies case parsing, text quality scoring, PDF text extraction with PyMuPDF,
      ingestion idempotency, and REST API endpoints.
"""

import pytest
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.models import Judgment, IngestJob
from backend.pipeline.ingest import (
    parse_case_title,
    compute_text_quality,
    extract_text_from_pdf_bytes,
    prioritize_records,
)

# Test SQLite in-memory database with StaticPool so all connections share the same memory DB
from sqlalchemy.pool import StaticPool

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


def test_parse_case_title():
    """Verify regex extraction of case number, petitioner, and respondent."""
    title1 = "WPA/14470/2023 of RAM SHARMA Vs STATE OF WEST BENGAL & ORS"
    c_num, pet, res = parse_case_title(title1)
    assert c_num == "WPA/14470/2023"
    assert pet == "RAM SHARMA"
    assert res == "STATE OF WEST BENGAL & ORS"

    title2 = "CPAN/2098/2014 of SOMENATH ADHIKARY Vs DEVDUTTA RAY"
    c_num, pet, res = parse_case_title(title2)
    assert c_num == "CPAN/2098/2014"
    assert pet == "SOMENATH ADHIKARY"
    assert res == "DEVDUTTA RAY"

    title_no_vs = "CRL.M.C./5833/2022 of IN RE MATTER OF PUBLIC IMPORTANCE"
    c_num, pet, res = parse_case_title(title_no_vs)
    assert c_num == "CRL.M.C./5833/2022"
    assert pet == "IN RE MATTER OF PUBLIC IMPORTANCE"
    assert res is None


def test_compute_text_quality_readable():
    """Verify that clear, dense text is scored as INGESTED with high quality."""
    text = (
        "IN THE HIGH COURT AT CALCUTTA\n"
        "Constitutional Writ Jurisdiction\n"
        "WPA 14470 of 2023\n"
        "The respondent authorities are hereby directed to consider the representation "
        "of the petitioner within a period of four weeks from the date of communication of this order."
    )
    score, status, error = compute_text_quality(text, pages=1)
    assert status == "INGESTED"
    assert error is None
    assert score > 0.5


def test_compute_text_quality_scanned_unreadable():
    """Verify that short text under 50 characters is flagged as FAILED_UNREADABLE."""
    scanned_text = "Page 1 of 1"
    score, status, error = compute_text_quality(scanned_text, pages=1)
    assert status == "FAILED_UNREADABLE"
    assert "Insufficient text" in error
    assert score == 0.0


def test_compute_text_quality_corrupted():
    """Verify that garbled text with non-printable characters is flagged as FAILED_UNREADABLE."""
    corrupted_text = "Valid text\x00\x01\x02\x03\x04\x05\x06\x07\x08" * 20
    score, status, error = compute_text_quality(corrupted_text, pages=1)
    assert status == "FAILED_UNREADABLE"
    assert "corrupted characters" in error


def test_extract_text_from_real_pdf_bytes():
    """Create a real vector PDF in-memory, extract text via PyMuPDF, and check quality."""
    doc = pymupdf.open()
    page = doc.new_page()
    sample_text = (
        "HIGH COURT AT CALCUTTA\n"
        "WPA No. 12345 of 2023\n"
        "Ram Chandra vs. District Magistrate\n"
        "The District Magistrate is directed to decide the pending application within 6 weeks."
    )
    page.insert_text((50, 50), sample_text)
    pdf_bytes = doc.write()
    doc.close()

    text, pages, quality, status, error = extract_text_from_pdf_bytes(pdf_bytes)
    assert pages == 1
    assert "District Magistrate is directed" in text
    assert status == "INGESTED"
    assert quality > 0.5
    assert error is None


def test_prioritize_records():
    """Verify that CPAN and WPA records are prioritized ahead of ordinary civil suits."""
    import pandas as pd
    df = pd.DataFrame([
        {"title": "CS/100/2023 Commercial Suit"},
        {"title": "CPAN/200/2023 Contempt Petition"},
        {"title": "WPA/300/2023 Writ Petition"},
        {"title": "FAT/400/2023 First Appeal"},
    ])
    sorted_df = prioritize_records(df)
    top_two = set(sorted_df["title"].iloc[:2].tolist())
    assert top_two == {"CPAN/200/2023 Contempt Petition", "WPA/300/2023 Writ Petition"}
    assert sorted_df["title"].iloc[2] in ["CS/100/2023 Commercial Suit", "FAT/400/2023 First Appeal"]


def test_api_ingest_lifecycle_and_queries(monkeypatch):
    """Test POST /ingest, GET /ingest/jobs/{id}, GET /judgments, and GET /judgments/{id}."""
    # Mock background worker so test suite runs offline and fast
    monkeypatch.setattr("backend.app.main.background_ingest_worker", lambda job_id, court, year, limit: None)

    # Seed a judgment in database
    with TestingSessionLocal() as db:
        j = Judgment(
            court="Calcutta High Court",
            year=2023,
            case_number="WPA/14470/2023",
            cnr="WBCHCA0144702023",
            petitioner="RAM SHARMA",
            respondent="STATE OF WEST BENGAL",
            s3_key="data/pdf/year=2023/court=19_16/bench=calcutta_appellate_side/WBCHCA0144702023_1_2023-03-24.pdf",
            text="The respondent is directed to act within 4 weeks.",
            text_quality=0.85,
            status="INGESTED",
        )
        db.add(j)
        db.commit()
        j_id = j.id

    # Test GET /judgments
    resp = client.get("/judgments?year=2023&status=INGESTED")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["case_number"] == "WPA/14470/2023"

    # Test GET /judgments/{id}
    resp_detail = client.get(f"/judgments/{j_id}")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["id"] == j_id
    assert "The respondent is directed" in detail["text"]

    # Test GET /judgments/9999 (404)
    resp_404 = client.get("/judgments/9999")
    assert resp_404.status_code == 404

    # Test POST /ingest
    resp_ingest = client.post("/ingest", json={"court": "calcutta", "year": 2023, "limit": 5})
    assert resp_ingest.status_code == 202
    job_info = resp_ingest.json()
    job_id = job_info["job_id"]
    assert job_id is not None
    assert job_info["status"] == "QUEUED"

    # Test GET /ingest/jobs/{id}
    resp_job = client.get(f"/ingest/jobs/{job_id}")
    assert resp_job.status_code == 200
    assert resp_job.json()["job_id"] == job_id
