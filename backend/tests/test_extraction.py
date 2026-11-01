"""Unit and integration tests for Segmentation, Direction Extraction, and Verbatim Verification.

Role: Validates heuristic segmentation, dismissal handling, Pydantic schemas,
      whitespace-tolerant verbatim quote verification, extraction pipeline state machine, and analysis API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import app
from backend.app.database import Base, get_db
from backend.app.models import Judgment, Direction, OperativeSegment
from backend.pipeline.models import ExtractedDirection, PartyType, DirectionType
from backend.pipeline.segment import segment_operative_part, check_is_pure_dismissal
from backend.pipeline.verify import verify_direction_quote, locate_verbatim_quote_offsets
from backend.pipeline.agent import ComplianceExtractionAgent

# Test SQLite in-memory database with StaticPool
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


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=test_engine)


client = TestClient(app)


def test_heuristic_segmentation_with_directions():
    """Verify that heuristic segmenter isolates operative part with correct offsets."""
    text = (
        "IN THE HIGH COURT AT CALCUTTA\n"
        "WPA 1234 of 2023\n"
        "The petitioner has approached this Court challenging inaction of municipal authorities.\n"
        "Heard learned counsel for the parties.\n"
        "In view of the above observations, the respondent Municipal Commissioner is directed to\n"
        "consider and dispose of the representation within six weeks from the date of communication of this order.\n"
        "With the aforesaid directions, WPA 1234 of 2023 is disposed of."
    )
    seg = segment_operative_part(text)
    assert seg.has_directions is True
    assert seg.segment_text is not None
    assert "In view of the above observations" in seg.segment_text
    assert seg.start_char is not None
    assert seg.end_char == len(text)
    assert text[seg.start_char:seg.end_char].strip() == seg.segment_text.strip()


def test_heuristic_segmentation_pure_dismissal():
    """Verify that orders with dismissals and no positive directions return has_directions=False."""
    dismissal_text = (
        "IN THE HIGH COURT AT CALCUTTA\n"
        "WPA 9999 of 2023\n"
        "Learned counsel for the petitioner submits that the petitioner does not wish to proceed with the matter.\n"
        "Leave to withdraw is granted. The writ petition is dismissed as withdrawn. There will be no order as to costs."
    )
    seg = segment_operative_part(dismissal_text)
    assert seg.has_directions is False
    assert seg.segment_text is None


def test_verbatim_verification_exact_and_multiline():
    """Verify verbatim quote verification with linebreaks and whitespace variation."""
    doc_text = (
        "The District Magistrate, 24 Parganas is hereby directed to inspect the premises "
        "and pass a reasoned order within a period of four weeks."
    )
    # 1. Exact quote
    d1 = ExtractedDirection(
        responsible_party="District Magistrate, 24 Parganas",
        party_type=PartyType.officer,
        action="inspect premises and pass reasoned order",
        deadline_phrase="within a period of four weeks",
        source_quote="The District Magistrate, 24 Parganas is hereby directed to inspect the premises and pass a reasoned order within a period of four weeks.",
    )
    v1 = verify_direction_quote(d1, doc_text)
    assert v1.verified is True
    assert v1.direction.quote_start == 0
    assert v1.direction.quote_end == len(doc_text)

    # 2. Quote with erratic whitespace / newlines
    d2 = ExtractedDirection(
        responsible_party="District Magistrate",
        party_type=PartyType.officer,
        action="inspect premises",
        source_quote="The   District Magistrate, 24 Parganas\n  is hereby directed to inspect",
    )
    v2 = verify_direction_quote(d2, doc_text)
    assert v2.verified is True
    assert v2.direction.quote_start == 0
    assert v2.direction.quote_end > 0

    # 3. Hallucinated / Paraphrased quote (Must fail!)
    d3 = ExtractedDirection(
        responsible_party="District Magistrate",
        party_type=PartyType.officer,
        action="inspect premises",
        source_quote="The Commissioner shall immediately visit the building and demolish it.",
    )
    v3 = verify_direction_quote(d3, doc_text)
    assert v3.verified is False
    assert "not a verbatim substring" in v3.rejection_reason


def test_deadline_phrase_verbatim_verification_and_extension():
    """Verify that deadline_phrase must be verbatim and extends adjacent source quotes."""
    text = (
        "The respondent Treasury Officer is directed to pay interest @ 8% per annum on gratuity. "
        "The payment as aforesaid shall be made within eight weeks from date of communication of this order."
    )

    # 1. Hallucinated deadline phrase -> set to None
    d_fake = ExtractedDirection(
        responsible_party="Treasury Officer",
        party_type=PartyType.officer,
        action="pay interest",
        deadline_phrase="within 10 days immediately",
        source_quote="The respondent Treasury Officer is directed to pay interest @ 8% per annum on gratuity.",
    )
    res_fake = verify_direction_quote(d_fake, text)
    assert res_fake.verified is True
    assert res_fake.deadline_verified is False
    assert res_fake.direction.deadline_phrase is None

    # 2. Adjacent deadline sentence -> source_quote extended
    d_adj = ExtractedDirection(
        responsible_party="Treasury Officer",
        party_type=PartyType.officer,
        action="pay interest",
        deadline_phrase="within eight weeks from date of communication of this order",
        source_quote="The respondent Treasury Officer is directed to pay interest @ 8% per annum on gratuity.",
    )
    res_adj = verify_direction_quote(d_adj, text)
    assert res_adj.verified is True
    assert res_adj.deadline_verified is True
    assert res_adj.quote_extended is True
    assert "within eight weeks" in res_adj.direction.source_quote
    assert res_adj.direction.quote_end == len(text)


def test_pipeline_loop_execution_and_persistence():
    """Verify end-to-end extraction pipeline state machine on a real judgment."""
    sample_text = (
        "IN THE HIGH COURT AT CALCUTTA\n"
        "Constitutional Writ Jurisdiction\n"
        "WPA 14470 of 2023\n"
        "Ram Sharma vs. State of West Bengal & Ors.\n"
        "Having heard the parties, this Court directs respondent no. 3 to consider and decide "
        "the petitioner's application within 4 weeks from date.\n"
        "Accordingly, the writ petition is disposed of."
    )

    with TestingSessionLocal() as db:
        j = Judgment(
            court="Calcutta High Court",
            year=2023,
            case_number="WPA/14470/2023",
            cnr="WBCHCA0144702023",
            petitioner="Ram Sharma",
            respondent="State of West Bengal & Ors.",
            text=sample_text,
            text_quality=0.88,
            status="INGESTED",
        )
        db.add(j)
        db.commit()
        db.refresh(j)

        agent = ComplianceExtractionAgent(judgment=j)
        res = agent.run(db)

        assert res["has_directions"] is True
        assert res["total_directions"] >= 1
        assert len(res["step_logs"]) >= 3

        # Verify database persistence
        db_dirs = db.query(Direction).filter(Direction.judgment_id == j.id).all()
        assert len(db_dirs) == res["total_directions"]
        assert db_dirs[0].quote_verified is True
        assert db_dirs[0].quote_start is not None


def test_api_analysis_endpoints():
    """Verify POST /judgments/{id}/analyze, POST /analyze/batch, and GET /judgments/{id}/directions."""
    sample_text = (
        "Court at Calcutta. In view of the above, respondent authorities are directed to "
        "release the payment within 30 days. WPA disposed of."
    )

    with TestingSessionLocal() as db:
        j = Judgment(
            court="Calcutta High Court",
            year=2023,
            case_number="WPA/500/2023",
            cnr="WBCHCA0005002023",
            text=sample_text,
            text_quality=0.85,
            status="INGESTED",
        )
        db.add(j)
        db.commit()
        j_id = j.id

    # 1. POST /judgments/{id}/analyze
    resp_analyze = client.post(f"/judgments/{j_id}/analyze")
    assert resp_analyze.status_code == 200
    data = resp_analyze.json()
    assert data["judgment_id"] == j_id
    assert data["has_directions"] is True
    assert data["total_directions"] >= 1

    # 2. GET /judgments/{id}/directions
    resp_dirs = client.get(f"/judgments/{j_id}/directions")
    assert resp_dirs.status_code == 200
    dirs = resp_dirs.json()
    assert len(dirs) == data["total_directions"]
    assert dirs[0]["quote_verified"] is True
    assert dirs[0]["deadline_phrase"] is not None

    # 3. POST /analyze/batch
    resp_batch = client.post("/analyze/batch", json={"judgment_ids": [j_id]})
    assert resp_batch.status_code == 200
    batch_data = resp_batch.json()
    assert batch_data["total_judgments"] == 1
    assert batch_data["total_directions"] >= 1
    assert batch_data["verified_first_try_pct"] >= 50.0
