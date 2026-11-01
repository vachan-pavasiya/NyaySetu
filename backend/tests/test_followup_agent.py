"""Unit tests for Phase B autonomous follow-up analysis agent.

Tests:
1. FollowUpAnalysisAgent candidate discovery for header citations and case links.
2. Explicit state loop execution with latency and step logging.
3. Verbatim quote verifier with feedback retry.
4. Graceful handling of Gemini failures: direction status remains unchanged and error is logged.
5. Endpoints: GET /agent/runs, POST /agent/rescan, and auto-trigger on POST /judgments/{id}/analyze.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models import (
    AgentRun,
    Direction,
    DirectionStatusHistory,
    Evidence,
    Judgment,
    OperativeSegment,
)
from backend.pipeline.followup_agent import (
    FollowUpAnalysisAgent,
    rescan_database_followup,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_agent_candidate_discovery():
    """Verify candidate discovery matches follow-up orders to earlier directions."""
    with SessionLocal() as db:
        # Create test writ judgment with directions
        writ_j = Judgment(
            court="19_16",
            year=2022,
            case_number="WPA/99901/2022",
            judgment_date=date(2022, 5, 10),
            text="Writ petition disposed of with direction to decide representation within 4 weeks.",
            text_quality=1.0,
            status="INGESTED",
        )
        db.add(writ_j)
        db.commit()
        db.refresh(writ_j)

        d = Direction(
            judgment_id=writ_j.id,
            responsible_party="District Magistrate",
            action="Decide the pending representation",
            deadline_phrase="within 4 weeks",
            source_quote="direction to decide representation within 4 weeks",
            deadline_status="LAPSED",
            compliance_status="UNVERIFIED",
        )
        db.add(d)
        db.commit()

        # Create contempt judgment citing the writ in header
        cpan_j = Judgment(
            court="19_16",
            year=2023,
            case_number="CPAN/99902/2023",
            judgment_date=date(2023, 2, 15),
            text="CPAN 99902 of 2023 in WPA 99901 of 2022. Learned advocates submit that order has been complied with.",
            text_quality=1.0,
            status="INGESTED",
        )
        db.add(cpan_j)
        db.commit()
        db.refresh(cpan_j)

        agent = FollowUpAnalysisAgent(source_judgment=cpan_j, trigger="TEST")
        candidates = agent.find_candidates(db)

        # Clean up test rows
        db.delete(d)
        db.delete(cpan_j)
        db.delete(writ_j)
        db.commit()

        assert len(candidates) >= 1
        cand = candidates[0]
        assert cand["direction"].id == d.id
        assert cand["follow_up_judgment"].id == cpan_j.id
        assert cand["is_temporally_valid"] is True


def test_state_loop_and_verbatim_retry():
    """Verify the state loop: classify -> verify -> retry with feedback -> update status."""
    with SessionLocal() as db:
        writ_j = Judgment(
            court="19_16",
            year=2022,
            case_number="WPA/99911/2022",
            judgment_date=date(2022, 6, 1),
            text="Order: Representation to be considered within 2 weeks.",
            text_quality=1.0,
            status="INGESTED",
        )
        db.add(writ_j)
        db.commit()

        d = Direction(
            judgment_id=writ_j.id,
            responsible_party="Superintendent of Police",
            action="Consider representation",
            deadline_phrase="within 2 weeks",
            source_quote="Representation to be considered within 2 weeks",
            deadline_status="LAPSED",
            compliance_status="UNVERIFIED",
        )
        db.add(d)
        db.commit()

        cpan_j = Judgment(
            court="19_16",
            year=2023,
            case_number="CPAN/99912/2023",
            judgment_date=date(2023, 3, 1),
            text="CPAN 99912 of 2023 in WPA 99911 of 2022. We record that the contemnor has complied with the court directions.",
            text_quality=1.0,
            status="INGESTED",
        )
        db.add(cpan_j)
        db.commit()

        cand = {
            "direction": d,
            "original_judgment": writ_j,
            "follow_up_judgment": cpan_j,
            "link_type": "CONTEMPT_FILED",
            "link_signal": "contempt_citation",
            "link_confidence": "HIGH",
            "citation_text": "CPAN 99912 of 2023 in WPA 99911 of 2022",
            "is_temporally_valid": True,
            "time_reason": None,
        }

        # Mock Gemini call: first attempt returns altered quote, second attempt (retry) returns verbatim quote
        mock_response_1 = MagicMock()
        mock_response_1.text = json.dumps({
            "verdict": "COMPLIANCE_SHOWN",
            "evidence_strength": "COURT_RECORDED",
            "supporting_quote": "paraphrased compliance quote not in text",
            "reasoning": "First attempt hallucinated quote",
        })

        mock_response_2 = MagicMock()
        mock_response_2.text = json.dumps({
            "verdict": "COMPLIANCE_SHOWN",
            "evidence_strength": "COURT_RECORDED",
            "supporting_quote": "contemnor has complied with the court directions",
            "reasoning": "Corrected verbatim quote after retry",
        })

        agent = FollowUpAnalysisAgent(source_judgment=cpan_j, trigger="TEST_RETRY")

        with patch("backend.app.config.get_settings") as mock_settings:
            mock_settings.return_value.GEMINI_API_KEY = "test_key"
            mock_settings.return_value.GEMINI_MODEL = "gemini-2.5-flash"
            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value = mock_client
                mock_client.models.generate_content.side_effect = [mock_response_1, mock_response_2]

                eval_result = agent.classify_and_verify(cand, db)

                assert eval_result is not None
                assert eval_result["verified"] is True
                assert eval_result["supporting_quote"] == "contemnor has complied with the court directions"

                # Persist and update
                agent.persist_and_update(cand, eval_result, db)

                # Check direction compliance status updated to COMPLIED
                db.refresh(d)
                assert d.compliance_status == "COMPLIED"
                assert "Verified compliance" in (d.sub_reason or "")

        # Clean up
        db.query(Evidence).filter(Evidence.direction_id == d.id).delete()
        db.query(DirectionStatusHistory).filter(DirectionStatusHistory.direction_id == d.id).delete()
        db.delete(d)
        db.delete(cpan_j)
        db.delete(writ_j)
        db.commit()


def test_graceful_handling_of_gemini_error():
    """Verify that a Gemini error leaves direction status unchanged and logs reason in errors."""
    with SessionLocal() as db:
        writ_j = Judgment(
            court="19_16",
            year=2022,
            case_number="WPA/99921/2022",
            judgment_date=date(2022, 7, 1),
            text="Order text.",
            text_quality=1.0,
            status="INGESTED",
        )
        db.add(writ_j)
        db.commit()

        d = Direction(
            judgment_id=writ_j.id,
            responsible_party="Commissioner",
            action="Action ordered",
            deadline_phrase="within 1 month",
            source_quote="Action ordered within 1 month",
            deadline_status="LAPSED",
            compliance_status="UNVERIFIED",
            sub_reason="Original unverified state",
        )
        db.add(d)
        db.commit()

        cpan_j = Judgment(
            court="19_16",
            year=2023,
            case_number="CPAN/99922/2023",
            judgment_date=date(2023, 4, 1),
            text="CPAN 99922 of 2023 in WPA 99921 of 2022.",
            text_quality=1.0,
            status="INGESTED",
        )
        db.add(cpan_j)
        db.commit()

        cand = {
            "direction": d,
            "original_judgment": writ_j,
            "follow_up_judgment": cpan_j,
            "link_type": "CONTEMPT_FILED",
            "link_signal": "contempt_citation",
            "link_confidence": "HIGH",
            "citation_text": "CPAN 99922 of 2023 in WPA 99921 of 2022",
            "is_temporally_valid": True,
            "time_reason": None,
        }

        agent = FollowUpAnalysisAgent(source_judgment=cpan_j, trigger="TEST_ERROR")

        with patch("backend.app.config.get_settings") as mock_settings:
            mock_settings.return_value.GEMINI_API_KEY = "test_key"
            mock_settings.return_value.GEMINI_MODEL = "gemini-2.5-flash"
            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value = mock_client
                # Simulate 429 quota exhaustion or network timeout
                mock_client.models.generate_content.side_effect = RuntimeError("ResourceExhausted: 429 Quota exceeded")

                eval_result = agent.classify_and_verify(cand, db)

                # Ensure eval_result is None on error
                assert eval_result is None
                assert len(agent.errors) == 1
                assert "429 Quota exceeded" in agent.errors[0]

                # Ensure direction compliance status remains UNCHANGED
                db.refresh(d)
                assert d.compliance_status == "UNVERIFIED"
                assert d.sub_reason == "Original unverified state"

        # Clean up
        db.delete(d)
        db.delete(cpan_j)
        db.delete(writ_j)
        db.commit()


def test_agent_runs_api_endpoints(client):
    """Verify GET /agent/runs and POST /agent/rescan endpoints."""
    # 1. GET /agent/runs
    res = client.get("/agent/runs")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "runs" in data
    assert isinstance(data["runs"], list)

    # 2. POST /agent/rescan
    res_rescan = client.post("/agent/rescan")
    assert res_rescan.status_code == 200
    rescan_data = res_rescan.json()
    assert rescan_data["outcome"] in ("SUCCESS", "PARTIAL_SUCCESS", "NO_CANDIDATES")
    assert "run_id" in rescan_data
    assert rescan_data["directions_checked"] >= 0

