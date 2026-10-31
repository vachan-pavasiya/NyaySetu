"""Deterministic deadline resolution module.

Role: Deterministically parses legal direction deadline phrases into structured anchors and offsets,
      computes estimated compliance date windows with python-dateutil (without LLM arithmetic),
      and buckets compliance statuses relative to a reference date.
Data flow: Direction.deadline_phrase + Judgment.judgment_date -> regex/rules (or LLM classification fallback) ->
           dateutil window math -> Direction record columns (window_start, window_end, explanation, status).
"""

import json
import logging
import os
import re
from datetime import date, datetime
from typing import Literal, Optional, Tuple

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.models import Direction, Judgment, LLMCache
from backend.pipeline.extract_directions import (
    compute_cache_key,
    get_cached_response,
    save_cached_response,
)

logger = logging.getLogger("compliance_radar.deadline")

# Configurable constant: estimated days for transmission and receipt of order copy
SERVICE_LAG_DAYS: int = int(os.getenv("SERVICE_LAG_DAYS", "30"))

AnchorType = Literal["judgment_date", "receipt", "explicit_date", "hearing", "none"]
OffsetUnit = Literal["days", "weeks", "months", "immediate", "hearing", "none"]
DeadlineStatus = Literal["UPCOMING", "IN_WINDOW", "LAPSED", "NO_DEADLINE", "URGENT_UNSPECIFIED"]

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "twenty-one": 21, "twenty one": 21, "twenty-two": 22, "twenty two": 22,
    "twenty-five": 25, "twenty five": 25, "thirty": 30,
    "forty": 40, "forty-five": 45, "forty five": 45,
    "fifty": 50, "sixty": 60, "ninety": 90,
}


class LLMDeadlineClassification(BaseModel):
    """Schema for LLM classification of unrecognised phrases (no date calculation)."""
    anchor_type: AnchorType = Field(description="Anchor type: judgment_date, receipt, explicit_date, hearing, or none")
    offset_value: Optional[int] = Field(default=None, description="Numeric count of days/weeks/months")
    offset_unit: Optional[OffsetUnit] = Field(default=None, description="Unit: days, weeks, months, immediate, hearing, or none")
    explicit_date_str: Optional[str] = Field(default=None, description="Verbatim date string if explicit date is mentioned")
    is_urgent_unspecified: bool = Field(default=False, description="True if forthwith/immediately/expeditiously")


class ParsedDeadline(BaseModel):
    """Full structured resolution of a deadline."""
    anchor_type: AnchorType
    offset_value: Optional[int] = None
    offset_unit: Optional[OffsetUnit] = None
    explicit_date: Optional[date] = None
    is_urgent_unspecified: bool = False
    is_estimated: bool = False
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    deadline_status: DeadlineStatus = "NO_DEADLINE"
    explanation_text: str = ""


def _get_gemini_client():
    """Lazily initializes the Google GenAI client."""
    from backend.app.config import settings
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.warning(f"Failed to initialize Gemini client for deadline classification: {e}")
        return None


def parse_number_token(token: str) -> Optional[int]:
    """Converts a digits string or word into an integer."""
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return WORD_TO_NUM.get(token) or WORD_TO_NUM.get(token.replace("-", " "))


def parse_explicit_date(date_str: str) -> Optional[date]:
    """Deterministically parses an explicit calendar date string."""
    try:
        # Strip ordinal suffixes (1st, 2nd, 3rd, 4th) attached to digits
        clean = re.sub(r"(\d+)(?:st|nd|rd|th)", r"\1", date_str.strip(), flags=re.IGNORECASE)
        dt = date_parser.parse(clean, dayfirst=True)
        return dt.date()
    except Exception as e:
        logger.warning(f"Could not parse explicit date '{date_str}': {e}")
        return None


def classify_phrase_regex(norm_phrase: str) -> Optional[dict]:
    """Applies rule-based regex patterns to classify legal deadline phrases."""
    # 1. Urgent unspecified
    if re.search(r"\b(forthwith|immediately|expeditiously|as\s+expeditiously\s+as\s+possible)\b", norm_phrase, re.IGNORECASE):
        return {
            "anchor_type": "none",
            "offset_value": None,
            "offset_unit": "immediate",
            "is_urgent_unspecified": True,
            "explicit_date": None,
        }

    # 2. Next date of hearing
    if re.search(r"\b(next\s+date\s+of\s+hearing|next\s+hearing|next\s+date)\b", norm_phrase, re.IGNORECASE):
        return {
            "anchor_type": "hearing",
            "offset_value": None,
            "offset_unit": "hearing",
            "is_urgent_unspecified": False,
            "explicit_date": None,
        }

    # 3. Explicit date ("on or before 31st March, 2024", "before 15.09.2023", "by August 15, 2023")
    exp_match = re.search(
        r"\b(?:on\s+or\s+before|before|by)\s+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+[0-9]{4}|[0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2}(?:st|nd|rd|th)?,?\s+[0-9]{4})\b",
        norm_phrase,
        re.IGNORECASE,
    )
    if exp_match:
        dt = parse_explicit_date(exp_match.group(1))
        if dt:
            return {
                "anchor_type": "explicit_date",
                "offset_value": None,
                "offset_unit": "none",
                "is_urgent_unspecified": False,
                "explicit_date": dt,
            }

    # 4. Standard duration pattern: "within [a period of] N days/weeks/months [from/of anchor]"
    dur_match = re.search(
        r"(?:within\s+(?:the\s+period\s+of\s+|a\s+period\s+of\s+)?)?(\d+|[a-zA-Z\-]+)\s+(days?|weeks?|months?|working\s+days?)(?:\s+(?:from|of)\s+(.*))?",
        norm_phrase,
        re.IGNORECASE,
    )
    if dur_match:
        num = parse_number_token(dur_match.group(1))
        if num is not None and num > 0:
            raw_unit = dur_match.group(2).lower()
            if "day" in raw_unit:
                unit = "days"
            elif "week" in raw_unit:
                unit = "weeks"
            elif "month" in raw_unit:
                unit = "months"
            else:
                unit = "days"

            anchor_text = (dur_match.group(3) or "").lower().strip()
            if re.search(r"\b(receipt|communication|service|production|served|producing|communicated|receiving)\b", anchor_text):
                anchor = "receipt"
            elif re.search(r"\b(date\s+of\s+(?:this\s+order|the\s+order|this\s+judgment)|today|this\s+date|date)\b", anchor_text) or anchor_text == "date":
                anchor = "judgment_date"
            elif not anchor_text:
                anchor = "judgment_date"
            else:
                anchor = "receipt" if "order" in anchor_text else "judgment_date"

            return {
                "anchor_type": anchor,
                "offset_value": num,
                "offset_unit": unit,
                "is_urgent_unspecified": False,
                "explicit_date": None,
            }

    # 5. Phrase indicating anchor without number: "from the date of this order/judgment/today"
    if re.search(r"\bfrom\s+the\s+date\s+of\s+(?:this\s+order|the\s+order|today|this\s+judgment)\b", norm_phrase, re.IGNORECASE):
        return {
            "anchor_type": "judgment_date",
            "offset_value": None,
            "offset_unit": "immediate",
            "is_urgent_unspecified": True,
            "explicit_date": None,
        }

    return None


def classify_phrase_llm(phrase: str) -> Optional[dict]:
    """Fallback LLM classification for unrecognised phrases (never computes dates)."""
    cache_key = compute_cache_key("deadline_classify", phrase)
    cached = get_cached_response(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            dt = parse_explicit_date(data.get("explicit_date_str")) if data.get("explicit_date_str") else None
            return {
                "anchor_type": data.get("anchor_type", "none"),
                "offset_value": data.get("offset_value"),
                "offset_unit": data.get("offset_unit"),
                "is_urgent_unspecified": data.get("is_urgent_unspecified", False),
                "explicit_date": dt,
            }
        except Exception:
            pass

    client = _get_gemini_client()
    if not client:
        return None

    prompt = (
        "Classify the following court deadline phrase into structured metadata. "
        "DO NOT calculate or compute dates. Only extract anchor type, offset value, and offset unit:\n"
        f"Phrase: {phrase}"
    )

    try:
        from backend.pipeline.extract_directions import _ACTIVE_GEMINI_MODEL
        model = _ACTIVE_GEMINI_MODEL or "gemini-flash-lite-latest"
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": LLMDeadlineClassification,
                "temperature": 0.0,
            },
        )
        if resp.text:
            save_cached_response(cache_key, "deadline_classify", model, resp.text)
            data = json.loads(resp.text)
            dt = parse_explicit_date(data.get("explicit_date_str")) if data.get("explicit_date_str") else None
            return {
                "anchor_type": data.get("anchor_type", "none"),
                "offset_value": data.get("offset_value"),
                "offset_unit": data.get("offset_unit"),
                "is_urgent_unspecified": data.get("is_urgent_unspecified", False),
                "explicit_date": dt,
            }
    except Exception as e:
        logger.warning(f"LLM deadline classification failed for '{phrase}': {e}")

    return None


def compute_deadline_window(
    anchor_type: AnchorType,
    offset_value: Optional[int],
    offset_unit: Optional[OffsetUnit],
    judgment_date: Optional[date],
    service_lag_days: int = SERVICE_LAG_DAYS,
    explicit_date: Optional[date] = None,
    is_urgent_unspecified: bool = False,
    as_of: Optional[date] = None,
) -> Tuple[Optional[date], Optional[date], bool, str, DeadlineStatus]:
    """Deterministically computes date window, estimated flag, explanation, and status."""
    ref_date = as_of or date.today()

    if is_urgent_unspecified or offset_unit == "immediate":
        w_start = judgment_date
        w_end = None
        is_est = False
        expl = "Urgent unspecified deadline (forthwith/immediately/expeditiously); no fixed duration specified."
        return w_start, w_end, is_est, expl, "URGENT_UNSPECIFIED"

    if anchor_type == "hearing":
        return None, None, True, "Deadline tied to next date of hearing; dependent on court cause list.", "UPCOMING"

    if anchor_type == "explicit_date" and explicit_date:
        w_start = explicit_date
        w_end = explicit_date
        is_est = False
        expl = f"Explicit deadline date: {explicit_date.isoformat()}."
        status: DeadlineStatus = "LAPSED" if ref_date > explicit_date else ("IN_WINDOW" if ref_date == explicit_date else "UPCOMING")
        return w_start, w_end, is_est, expl, status

    if not judgment_date or not offset_value or not offset_unit or offset_unit == "none":
        return None, None, False, "No deadline specified in order.", "NO_DEADLINE"

    # Compute delta
    if offset_unit == "days":
        delta = relativedelta(days=offset_value)
    elif offset_unit == "weeks":
        delta = relativedelta(weeks=offset_value)
    elif offset_unit == "months":
        delta = relativedelta(months=offset_value)
    else:
        delta = relativedelta(days=offset_value)

    if anchor_type == "receipt":
        w_start = judgment_date + delta
        w_end = w_start + relativedelta(days=service_lag_days)
        is_est = True
        expl = (
            f"{offset_value} {offset_unit} from receipt. "
            f"Receipt date unknown, so window = judgment date + {offset_value} {offset_unit} "
            f"to + {offset_value} {offset_unit} + {service_lag_days} days"
        )
    else:
        # anchor_type == "judgment_date"
        w_start = judgment_date + delta
        w_end = w_start
        is_est = False
        expl = f"{offset_value} {offset_unit} from date of order. Known order date, deadline is exactly judgment date + {offset_value} {offset_unit}."

    # Status bucketing
    if w_end and ref_date > w_end:
        status = "LAPSED"
    elif w_start and ref_date < w_start:
        status = "UPCOMING"
    else:
        status = "IN_WINDOW"

    return w_start, w_end, is_est, expl, status


def resolve_deadline(
    phrase: Optional[str],
    judgment_date: Optional[date],
    service_lag_days: int = SERVICE_LAG_DAYS,
    as_of: Optional[date] = None,
    allow_llm: bool = True,
) -> ParsedDeadline:
    """Main resolution function: classifies phrase and deterministically resolves deadline."""
    if not phrase or not phrase.strip():
        return ParsedDeadline(
            anchor_type="none",
            offset_unit="none",
            deadline_status="NO_DEADLINE",
            explanation_text="No deadline specified in order.",
        )

    norm = " ".join(phrase.split()).strip()

    # Step 1: Deterministic regex classification
    cls_dict = classify_phrase_regex(norm)

    # Step 2: Fallback to LLM classification only if unrecognised
    if not cls_dict and allow_llm:
        cls_dict = classify_phrase_llm(norm)

    if not cls_dict:
        return ParsedDeadline(
            anchor_type="none",
            offset_unit="none",
            deadline_status="NO_DEADLINE",
            explanation_text=f"Unrecognised deadline phrase: '{norm}'.",
        )

    w_start, w_end, is_est, expl, status = compute_deadline_window(
        anchor_type=cls_dict["anchor_type"],
        offset_value=cls_dict.get("offset_value"),
        offset_unit=cls_dict.get("offset_unit"),
        judgment_date=judgment_date,
        service_lag_days=service_lag_days,
        explicit_date=cls_dict.get("explicit_date"),
        is_urgent_unspecified=cls_dict.get("is_urgent_unspecified", False),
        as_of=as_of,
    )

    return ParsedDeadline(
        anchor_type=cls_dict["anchor_type"],
        offset_value=cls_dict.get("offset_value"),
        offset_unit=cls_dict.get("offset_unit"),
        explicit_date=cls_dict.get("explicit_date"),
        is_urgent_unspecified=cls_dict.get("is_urgent_unspecified", False),
        is_estimated=is_est,
        window_start=w_start,
        window_end=w_end,
        deadline_status=status,
        explanation_text=expl,
    )


def resolve_and_update_direction(
    direction_id: int,
    db: Session,
    service_lag_days: int = SERVICE_LAG_DAYS,
    as_of: Optional[date] = None,
) -> Optional[Direction]:
    """Resolves and updates a Direction record in SQLite."""
    d = db.query(Direction).filter(Direction.id == direction_id).first()
    if not d:
        return None

    j = db.query(Judgment).filter(Judgment.id == d.judgment_id).first()
    j_date = j.judgment_date if j else None

    res = resolve_deadline(d.deadline_phrase, j_date, service_lag_days=service_lag_days, as_of=as_of)

    d.anchor_type = res.anchor_type
    d.offset_value = res.offset_value
    d.offset_unit = res.offset_unit
    d.deadline_window_start = res.window_start
    d.deadline_window_end = res.window_end
    d.is_estimated = res.is_estimated
    d.explanation_text = res.explanation_text
    d.deadline_status = res.deadline_status

    db.commit()
    db.refresh(d)
    return d


def resolve_all_directions(
    db: Session,
    service_lag_days: int = SERVICE_LAG_DAYS,
    as_of: Optional[date] = None,
) -> int:
    """Resolves deadline windows for all directions in the database."""
    directions = db.query(Direction).all()
    count = 0
    for d in directions:
        j = db.query(Judgment).filter(Judgment.id == d.judgment_id).first()
        j_date = j.judgment_date if j else None
        res = resolve_deadline(d.deadline_phrase, j_date, service_lag_days=service_lag_days, as_of=as_of)
        d.anchor_type = res.anchor_type
        d.offset_value = res.offset_value
        d.offset_unit = res.offset_unit
        d.deadline_window_start = res.window_start
        d.deadline_window_end = res.window_end
        d.is_estimated = res.is_estimated
        d.explanation_text = res.explanation_text
        d.deadline_status = res.deadline_status
        count += 1
    db.commit()
    return count
