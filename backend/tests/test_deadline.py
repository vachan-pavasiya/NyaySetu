"""Unit tests for Phase 3 Deterministic Deadline Resolution.

Role: Verifies deterministic parsing, date math, configurable service lag, and status bucketing
      using real phrases from ingested High Court judgments.
Data flow: Deadline phrases + judgment dates -> backend.pipeline.deadline -> assertions.
"""

from datetime import date
from unittest.mock import patch, MagicMock

import pytest
from dateutil.relativedelta import relativedelta

from backend.pipeline.deadline import (
    SERVICE_LAG_DAYS,
    classify_phrase_regex,
    compute_deadline_window,
    parse_number_token,
    parse_explicit_date,
    resolve_deadline,
)
from backend.pipeline.models import ExtractedDirection, PartyType, DirectionType
from backend.pipeline.verify import deduplicate_verified_directions


def test_number_word_parsing():
    """Verify conversion of digits and number words."""
    assert parse_number_token("30") == 30
    assert parse_number_token("eight") == 8
    assert parse_number_token("twelve") == 12
    assert parse_number_token("two") == 2
    assert parse_number_token("three") == 3
    assert parse_number_token("forty-five") == 45
    assert parse_number_token("forty five") == 45
    assert parse_number_token("invalid_token") is None


def test_explicit_date_parsing():
    """Verify deterministic parsing of calendar dates with ordinals."""
    assert parse_explicit_date("31st March, 2024") == date(2024, 3, 31)
    assert parse_explicit_date("15.09.2023") == date(2023, 9, 15)
    assert parse_explicit_date("August 15, 2023") == date(2023, 8, 15)
    assert parse_explicit_date("22nd October 2023") == date(2023, 10, 22)
    assert parse_explicit_date("not a date") is None


def test_real_phrase_days_from_communication():
    """Real DB phrase from WPA/2240/2023 (Judgment ID 4): 'within 30 days from the date of communication of this order'."""
    phrase = "within 30 days from the\ndate of communication of this order"
    j_date = date(2023, 3, 2)

    res = resolve_deadline(phrase, j_date, service_lag_days=30, as_of=date(2023, 3, 10))

    assert res.anchor_type == "receipt"
    assert res.offset_value == 30
    assert res.offset_unit == "days"
    assert res.is_estimated is True
    # window_start = 2023-03-02 + 30 days = 2023-04-01
    assert res.window_start == date(2023, 4, 1)
    # window_end = 2023-04-01 + 30 days = 2023-05-01
    assert res.window_end == date(2023, 5, 1)
    assert res.deadline_status == "UPCOMING"
    assert "30 days from receipt" in res.explanation_text
    assert "30 days" in res.explanation_text


def test_real_phrase_weeks_from_communication():
    """Real DB phrase from WPA/11854/2023 (Judgment ID 12): 'within the period of eight weeks from the date of communication of this order'."""
    phrase = "within the period of eight weeks from the date of communication of this order"
    j_date = date(2023, 7, 28)

    # Reference date within the window
    res_in_window = resolve_deadline(phrase, j_date, service_lag_days=30, as_of=date(2023, 10, 1))

    assert res_in_window.anchor_type == "receipt"
    assert res_in_window.offset_value == 8
    assert res_in_window.offset_unit == "weeks"
    assert res_in_window.is_estimated is True
    # 2023-07-28 + 8 weeks = 2023-09-22
    assert res_in_window.window_start == date(2023, 9, 22)
    # 2023-09-22 + 30 days = 2023-10-22
    assert res_in_window.window_end == date(2023, 10, 22)
    assert res_in_window.deadline_status == "IN_WINDOW"


def test_real_phrase_twelve_weeks_from_communication():
    """Real DB phrase from WPA/9716/2023 (Judgment ID 17): 'within a period of twelve weeks from the date of communication of this order'."""
    phrase = "within a period of twelve weeks from the date of communication of this order"
    j_date = date(2023, 8, 11)

    # Reference date after window has lapsed
    res_lapsed = resolve_deadline(phrase, j_date, service_lag_days=30, as_of=date(2024, 1, 1))

    assert res_lapsed.anchor_type == "receipt"
    assert res_lapsed.offset_value == 12
    assert res_lapsed.offset_unit == "weeks"
    # 2023-08-11 + 12 weeks = 2023-11-03
    assert res_lapsed.window_start == date(2023, 11, 3)
    # 2023-11-03 + 30 days = 2023-12-03
    assert res_lapsed.window_end == date(2023, 12, 3)
    assert res_lapsed.deadline_status == "LAPSED"


def test_real_phrase_months_from_date_ambiguous():
    """Real DB phrase from WPA/24727/2022 (Judgment ID 28): 'within a period of two months from date'.
    Does not clearly specify 'date of this order/judgment', so marked ambiguous (no computed window).
    """
    phrase = "within a period of two months from date"
    j_date = date(2023, 5, 15)

    res = resolve_deadline(phrase, j_date, service_lag_days=30, as_of=date(2023, 6, 1))

    assert res.anchor_type == "ambiguous"
    assert res.window_start is None
    assert res.window_end is None
    assert res.deadline_status == "AMBIGUOUS"
    assert "Ambiguous deadline phrase" in res.explanation_text


def test_clear_date_of_order_phrase():
    """Clear order date phrase: 'within a period of two months from the date of this order'."""
    phrase = "within a period of two months from the date of this order"
    j_date = date(2023, 5, 15)

    res = resolve_deadline(phrase, j_date, service_lag_days=30, as_of=date(2023, 6, 1))

    assert res.anchor_type == "judgment_date"
    assert res.offset_value == 2
    assert res.offset_unit == "months"
    assert res.is_estimated is False
    assert res.window_start == date(2023, 7, 15)
    assert res.window_end == date(2023, 7, 15)
    assert res.deadline_status == "UPCOMING"
    assert "2 months from date of order" in res.explanation_text


def test_urgent_unspecified_phrases():
    """Cover forthwith, immediately, expeditiously, as expeditiously as possible."""
    j_date = date(2023, 8, 11)

    for word in ["forthwith", "immediately", "expeditiously", "as expeditiously as possible"]:
        res = resolve_deadline(word, j_date)
        assert res.anchor_type == "none"
        assert res.offset_unit == "immediate"
        assert res.is_urgent_unspecified is True
        assert res.deadline_status == "URGENT_UNSPECIFIED"
        assert res.window_start == j_date
        assert res.window_end is None


def test_dependent_on_prior_event():
    """Phrases containing 'thereafter', 'after which', 'upon completion of', 'after compliance'."""
    j_date = date(2023, 2, 28)

    dependent_phrases = [
        "within a week thereafter",
        "within \na \nweek\nthereafter",
        "after which compliance shall be submitted within 2 weeks",
        "upon completion of the inquiry",
        "after compliance of the direction",
    ]

    for p in dependent_phrases:
        res = resolve_deadline(p, j_date)
        assert res.anchor_type == "DEPENDENT_ON_PRIOR_EVENT"
        assert res.window_start is None
        assert res.window_end is None
        assert res.deadline_status == "DEPENDENT"
        assert res.explanation_text == "Deadline depends on an earlier step in the order; no date can be computed."


def test_explicit_date_deadlines():
    """Cover 'on or before', 'before', 'by <date>'."""
    j_date = date(2023, 8, 11)

    res1 = resolve_deadline("on or before 31st March, 2024", j_date, as_of=date(2024, 1, 1))
    assert res1.anchor_type == "explicit_date"
    assert res1.window_start == date(2024, 3, 31)
    assert res1.window_end == date(2024, 3, 31)
    assert res1.deadline_status == "UPCOMING"

    res2 = resolve_deadline("by 15.09.2023", j_date, as_of=date(2023, 10, 1))
    assert res2.anchor_type == "explicit_date"
    assert res2.window_start == date(2023, 9, 15)
    assert res2.deadline_status == "LAPSED"


def test_next_date_of_hearing():
    """Cover 'next date of hearing'."""
    res = resolve_deadline("next date of hearing", date(2023, 8, 11))
    assert res.anchor_type == "hearing"
    assert res.is_estimated is True
    assert res.window_start is None
    assert res.window_end is None
    assert res.deadline_status == "UPCOMING"


def test_no_deadline_and_empty():
    """Cover empty, whitespace, and None phrases."""
    assert resolve_deadline(None, date(2023, 8, 11)).deadline_status == "NO_DEADLINE"
    assert resolve_deadline("", date(2023, 8, 11)).deadline_status == "NO_DEADLINE"
    assert resolve_deadline("   ", date(2023, 8, 11)).deadline_status == "NO_DEADLINE"


def test_configurable_service_lag_days():
    """Verify that SERVICE_LAG_DAYS adjusts the estimated window length."""
    phrase = "within 4 weeks from receipt of this order"
    j_date = date(2023, 1, 1)

    res30 = resolve_deadline(phrase, j_date, service_lag_days=30)
    res45 = resolve_deadline(phrase, j_date, service_lag_days=45)

    assert res30.window_start == res45.window_start
    assert (res45.window_end - res45.window_start).days == 45
    assert (res30.window_end - res30.window_start).days == 30


def test_llm_classification_fallback():
    """Unrecognised phrase falls back to LLM structured classification, then code computes."""
    unrecognised_phrase = "in a timeline spanning roughly six fortnights following communication"
    j_date = date(2023, 1, 1)

    mock_classification = {
        "anchor_type": "receipt",
        "offset_value": 12,
        "offset_unit": "weeks",
        "is_urgent_unspecified": False,
        "explicit_date": None,
    }

    with patch("backend.pipeline.deadline.classify_phrase_llm", return_value=mock_classification):
        res = resolve_deadline(unrecognised_phrase, j_date, service_lag_days=30)
        assert res.anchor_type == "receipt"
        assert res.offset_value == 12
        assert res.offset_unit == "weeks"
        assert res.window_start == j_date + relativedelta(weeks=12)
        assert res.window_end == res.window_start + relativedelta(days=30)


def test_deduplicate_verified_directions():
    """Overlapping direction for the same party where one quote subsumes the other is deduplicated."""
    d1 = ExtractedDirection(
        responsible_party="Treasury Officer",
        party_type=PartyType.officer,
        direction_type=DirectionType.mandatory,
        action="Pay interest at 8% per annum",
        source_quote="Full sentence containing the main direction and default clause.",
        quote_start=100,
        quote_end=300,
        confidence=0.98,
    )
    # d2 is a smaller snippet of the default clause inside d1 for the same party
    d2 = ExtractedDirection(
        responsible_party="Treasury Officer",
        party_type=PartyType.officer,
        direction_type=DirectionType.consequential,
        action="Pay additional 2% on default",
        source_quote="default clause.",
        quote_start=250,
        quote_end=300,
        confidence=0.95,
    )
    # d3 is for a DIFFERENT party, even if overlapping offsets
    d3 = ExtractedDirection(
        responsible_party="Director of Pension",
        party_type=PartyType.department,
        direction_type=DirectionType.mandatory,
        action="Issue PPO",
        source_quote="Director shall issue PPO",
        quote_start=150,
        quote_end=240,
        confidence=0.95,
    )

    deduped = deduplicate_verified_directions([d1, d2, d3])
    assert len(deduped) == 2
    assert d1 in deduped
    assert d2 not in deduped  # subsumed duplicate removed
    assert d3 in deduped      # different party preserved
