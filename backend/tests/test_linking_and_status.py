"""Unit tests for Phase 4 follow-up linking and status engine.

Tests:
1. Citation format normalization on real contempt petition headers from the database.
2. Temporal sanity rule (valid sequence, date inverted, filing year conflict).
3. DISMISSED_FOR_DEFAULT rule (petitioner absent maintains UNVERIFIED and sets flag).
4. Verifier on follow-up quote (verbatim check and rejection of altered quotes).
5. Status model transitions and flags.
"""

from datetime import date
import pytest

from backend.pipeline.linking import (
    normalize_case_citation,
    check_temporal_sanity,
    verify_follow_up_quote,
    classify_follow_up_order_heuristic,
)
from backend.pipeline.status import evaluate_direction_status
from backend.app.models import Direction, Evidence


def test_citation_format_normalization_real_headers():
    """Verify normalisation of at least 8 real header formats from DB contempt petitions."""
    cases = [
        ("WPA 13757 of 2004", "WPA/13757/2004"),
        ("CPAN 1088 of 2023 in WPA 11369 of 2023", "WPA/11369/2023"),
        ("W.P.A. No. 2222 of 2022", "WPA/2222/2022"),
        ("W.P.A. 4835 of 2021", "WPA/4835/2021"),
        ("WPA 7971 of 2021", "WPA/7971/2021"),
        ("WPA 17378 of 2022", "WPA/17378/2022"),
        ("WPA No. 4409 of 2022", "WPA/4409/2022"),
        ("MAT 408 of 2022", "MAT/408/2022"),
        ("FMA 1879 of 2019", "FMA/1879/2019"),
        ("W.P.A. No. 18860 of 2021", "WPA/18860/2021"),
        ("WPA 4466 of 2022", "WPA/4466/2022"),
        ("WPA 5477 of 2022", "WPA/5477/2022"),
    ]

    for raw, expected in cases:
        normalized = normalize_case_citation(raw)
        assert normalized == expected, f"Expected {expected} for raw citation '{raw}', got {normalized}"


def test_temporal_sanity_rule():
    """Verify temporal sanity checks for chronological order and filing year compatibility."""
    # 1. Valid temporal sequence (e.g. MAT 408 of 2022 vs CPAN 886 of 2022)
    valid, reason = check_temporal_sanity(
        earlier_date=date(2022, 4, 26),
        later_date=date(2023, 1, 10),
        earlier_case="MAT/408/2022",
        later_case="CPAN/886/2022",
    )
    assert valid is True
    assert reason is None

    # 2. Date conflict: earlier order date is after follow-up order date
    invalid_date, reason_date = check_temporal_sanity(
        earlier_date=date(2023, 10, 17),
        later_date=date(2023, 6, 6),
        earlier_case="CPAN/1088/2023",
        later_case="WPA/11369/2023",
    )
    assert invalid_date is False
    assert "Temporal conflict" in reason_date
    assert "is after follow-up order date" in reason_date

    # 3. Filing year conflict: follow-up petition filed in 2005 predates 2022 order
    # (e.g. WPCRC/18046/2005 vs WPA/13757/2004 dated 2022-09-21)
    invalid_year, reason_year = check_temporal_sanity(
        earlier_date=date(2022, 9, 21),
        later_date=date(2023, 10, 13),
        earlier_case="WPA/13757/2004",
        later_case="WPCRC/18046/2005",
    )
    assert invalid_year is False
    assert "predates earlier order date" in reason_year


def test_dismissed_for_default_rule():
    """Verify that 'dismissed for default' keeps UNVERIFIED and sets CONTEMPT_DISMISSED_FOR_DEFAULT."""
    real_order_text = """
    23.08.2023
    Court No. 19
    CPAN 867 of 2007
    in
    WPA 9009 of 2005
    When the matter is called on for hearing, none appears for the petitioner.
    No accommodation has been sought for.
    The contempt application is dismissed for default.
    """
    # 1. Classification
    classification = classify_follow_up_order_heuristic(real_order_text)
    assert classification["verdict"] == "DISMISSED_FOR_DEFAULT"

    # 2. Status engine evaluation
    direction = Direction(
        id=999,
        judgment_id=1,
        responsible_party="State",
        action="Pass reasoned order",
        deadline_status="LAPSED",
        deadline_window_end=date(2022, 1, 1),
    )
    evidence = Evidence(
        id=501,
        direction_id=999,
        source_case_number="CPAN/867/2007",
        source_date=date(2023, 8, 23),
        verdict="DISMISSED_FOR_DEFAULT",
        supporting_quote="The contempt application is dismissed for default.",
        verified=True,
    )

    status, flags, reason, primary_id = evaluate_direction_status(direction, [evidence])

    assert status == "UNVERIFIED", "Dismissed for default must never result in COMPLIED"
    assert flags["contempt_dismissed_for_default"] is True
    assert flags["overdue_no_record"] is True
    assert "dismissed for default" in reason.lower()


def test_verifier_on_follow_up_quote():
    """Verify verbatim verification of follow-up quotes from real High Court orders."""
    real_text = (
        "In view thereof, we dispose of the contempt application by recording "
        "compliance of the order dated 26th June, 2019.\n"
        "All connected applications are also disposed of."
    )

    # Exact verbatim quote
    assert verify_follow_up_quote(
        "recording compliance of the order dated 26th June, 2019",
        real_text,
    ) is True

    # Quote with slight whitespace variation (should still pass after whitespace normalisation)
    assert verify_follow_up_quote(
        "recording   compliance of the  order dated 26th June, 2019",
        real_text,
    ) is True

    # Hallucinated or modified quote (must fail)
    assert verify_follow_up_quote(
        "The court notes that the respondent has fully complied with all instructions.",
        real_text,
    ) is False


def test_status_model_rules():
    """Verify complete status model state transitions."""
    # Direction with open window -> PENDING
    d_open = Direction(
        id=101,
        judgment_id=1,
        responsible_party="Collector",
        action="Conduct spot inspection",
        deadline_status="IN_WINDOW",
        deadline_window_end=date(2027, 1, 1),
    )
    status, flags, reason, _ = evaluate_direction_status(d_open, [])
    assert status == "PENDING"
    assert flags["overdue_no_record"] is False

    # Direction with lapsed window and no evidence -> UNVERIFIED with overdue_no_record=True
    d_lapsed = Direction(
        id=102,
        judgment_id=1,
        responsible_party="Treasury Officer",
        action="Pay pension",
        deadline_status="LAPSED",
        deadline_window_end=date(2023, 1, 1),
    )
    status, flags, reason, _ = evaluate_direction_status(d_lapsed, [])
    assert status == "UNVERIFIED"
    assert flags["overdue_no_record"] is True

    # Direction with verified COMPLIANCE_SHOWN -> COMPLIED
    ev_complied = Evidence(
        id=301,
        direction_id=102,
        source_case_number="CPAN/1261/2019",
        source_date=date(2023, 11, 30),
        verdict="COMPLIANCE_SHOWN",
        supporting_quote="recording compliance of the order",
        verified=True,
    )
    status, flags, reason, _ = evaluate_direction_status(d_lapsed, [ev_complied])
    assert status == "COMPLIED"
    assert flags["overdue_no_record"] is False
    assert flags["contempt_filed"] is True, "Evidence from CPAN case must set contempt_filed flag"
    assert "Verified compliance recorded" in reason


def test_status_model_guards_and_ongoing_process():
    """Verify guards preventing COMPLIED on dismissals, liberties, and ongoing processes."""
    # 1. Liberty direction type must never be COMPLIED
    d_liberty = Direction(
        id=201,
        judgment_id=1,
        responsible_party="Appellant",
        direction_type="liberty",
        action="At liberty to make a representation",
        deadline_status="LAPSED",
        deadline_window_end=date(2023, 1, 1),
    )
    ev_complied = Evidence(
        id=401,
        direction_id=201,
        source_case_number="CPAN/886/2022",
        source_date=date(2023, 1, 10),
        verdict="COMPLIANCE_SHOWN",
        supporting_quote="The alleged contemnor, therefore, has complied with this Court’s order.",
        verified=True,
    )
    status, flags, reason, _ = evaluate_direction_status(d_liberty, [ev_complied], has_contempt_link=True)
    assert status == "UNVERIFIED", "Liberty to a party must never be marked COMPLIED"
    assert flags["contempt_filed"] is True

    # 2. Ongoing process (e.g. DI continues to make efforts) must resolve to PENDING, not COMPLIED
    d_ongoing = Direction(
        id=202,
        judgment_id=2,
        responsible_party="DI of Schools",
        action="Process transfer application",
        deadline_status="LAPSED",
        deadline_window_end=date(2022, 5, 1),
    )
    ev_ongoing = Evidence(
        id=402,
        direction_id=202,
        source_case_number="CPAN/1262/2022",
        source_date=date(2023, 4, 21),
        verdict="COMPLIANCE_SHOWN",
        supporting_quote="Compliance report filed by the District Inspector of Schools (SE), Malda is taken on record.",
        reasoning="District Inspector continues to make efforts to give relief to the petitioner.",
        verified=True,
    )
    status, flags, reason, _ = evaluate_direction_status(d_ongoing, [ev_ongoing], has_contempt_link=True)
    assert status == "PENDING", "Ongoing process must resolve to PENDING, not COMPLIED"
    assert flags["contempt_filed"] is True

    # 3. Disposed without finding must remain UNVERIFIED
    d_disposed = Direction(
        id=203,
        judgment_id=3,
        responsible_party="Police",
        action="Ensure status quo",
        deadline_status="LAPSED",
        deadline_window_end=date(2022, 1, 1),
    )
    ev_disposed = Evidence(
        id=403,
        direction_id=203,
        source_case_number="CPAN/222/2023",
        source_date=date(2023, 4, 27),
        verdict="DISPOSED_NO_FINDING",
        supporting_quote="The contempt application is disposed of.",
        verified=True,
    )
    status, flags, reason, _ = evaluate_direction_status(d_disposed, [ev_disposed], has_contempt_link=True)
    assert status == "UNVERIFIED", "Disposed without finding must never result in COMPLIED"
    assert flags["contempt_filed"] is True


def test_ongoing_process_verdict_and_evidence_refinements():
    """Verify ONGOING_PROCESS verdict, evidence_strength, and CASE_LEVEL scope."""
    from backend.pipeline.linking import determine_evidence_strength

    # 1. Primary ONGOING_PROCESS verdict
    d = Direction(
        id=301,
        judgment_id=10,
        responsible_party="Commission",
        action="Consider transfer request",
        deadline_status="LAPSED",
        deadline_window_end=date(2023, 1, 1),
    )
    ev_ongoing = Evidence(
        id=501,
        direction_id=301,
        source_case_number="CPAN/1263/2022",
        source_date=date(2023, 2, 27),
        verdict="ONGOING_PROCESS",
        supporting_quote="the petitioner shall sit with the Chairman of the School Service Commission",
        verified=True,
    )
    status, flags, reason, _ = evaluate_direction_status(d, [ev_ongoing], has_contempt_link=True)
    assert status == "PENDING"
    assert "ongoing compliance process" in reason

    # 2. evidence_strength: COURT_RECORDED vs PARTY_SUBMISSION
    court_quote = "The alleged contemnor, therefore, has complied with this Court’s order."
    party_quote = "It is submitted on behalf of both the parties that the order under contempt has been complied with."
    advocate_quote = "The learned advocates for the parties submit that the order-in-question has been complied with."

    assert determine_evidence_strength(court_quote) == "COURT_RECORDED"
    assert determine_evidence_strength(party_quote) == "PARTY_SUBMISSION"
    assert determine_evidence_strength(advocate_quote) == "PARTY_SUBMISSION"


def test_api_status_refactor_endpoints():
    """Verify GET /directions/{id}, /ledger, /stats, and /export.csv per Phase A status refactor."""
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)

    # 1. GET /directions/{id} returns status, sub_reason, flags, and evidence list
    r_dir = client.get("/directions/24")
    assert r_dir.status_code == 200
    d_data = r_dir.json()
    assert d_data["status"] in ("COMPLIED", "PENDING", "UNVERIFIED")
    assert d_data["sub_reason"] is not None
    assert "flags" in d_data
    assert "contempt_filed" in d_data["flags"]
    assert "overdue_no_record" in d_data["flags"]
    assert isinstance(d_data["evidence"], list)

    # 2. GET /ledger uses three statuses and returns paginated records
    r_ledger = client.get("/ledger?limit=10")
    assert r_ledger.status_code == 200
    ledger_data = r_ledger.json()
    assert "total" in ledger_data
    assert "items" in ledger_data
    for item in ledger_data["items"]:
        assert item["compliance_status"] in ("COMPLIED", "PENDING", "UNVERIFIED")
        assert item["status"] in ("COMPLIED", "PENDING", "UNVERIFIED")
        assert "flags" in item
        assert "overdue_no_record" in item["flags"]

    # Filter by status
    r_complied = client.get("/ledger?status=COMPLIED")
    assert r_complied.status_code == 200
    for item in r_complied.json()["items"]:
        assert item["compliance_status"] == "COMPLIED"

    # 3. GET /stats uses the three headline statuses
    r_stats = client.get("/stats")
    assert r_stats.status_code == 200
    stats_data = r_stats.json()
    assert set(stats_data["status_distribution"].keys()) == {"COMPLIED", "PENDING", "UNVERIFIED"}
    assert "flags_distribution" in stats_data
    assert "evidence_strength_distribution" in stats_data
    assert "top_departments" in stats_data

    # 4. GET /export.csv returns CSV with the three headline statuses
    r_csv = client.get("/export.csv")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers["content-type"]
    lines = r_csv.text.strip().split("\n")
    assert len(lines) > 1
    assert "direction_id,case_number,court" in lines[0]
    assert "compliance_status" in lines[0]
    assert "sub_reason" in lines[0]

