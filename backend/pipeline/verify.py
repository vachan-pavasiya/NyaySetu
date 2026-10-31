"""Verbatim quote verification, offset resolution, and deadline alignment module.

Role: Enforces the core guardrails:
      1. Every extracted direction must have an exact, verbatim source quote from the judgment text.
      2. Every deadline_phrase must also be a verbatim substring of the judgment text. If not found,
         it is set to null and logged.
      3. If a deadline sentence sits adjacent to the direction, extends source_quote to include it.
Data flow: ExtractedDirection + Judgment text -> Verbatim matcher -> Offset mapping -> VerificationResult.
"""

import re
import logging
from typing import Optional, Tuple
from backend.pipeline.models import ExtractedDirection, VerificationResult

logger = logging.getLogger("compliance_radar.verify")


def sanitize_typography(s: str) -> str:
    """Normalize typographic characters like smart quotes, dashes, and non-breaking spaces."""
    if not s:
        return ""
    replacements = {
        "\u2018": "'",  # Left single quotation mark
        "\u2019": "'",  # Right single quotation mark
        "\u201c": '"',  # Left double quotation mark
        "\u201d": '"',  # Right double quotation mark
        "\u2013": "-",  # En dash
        "\u2014": "-",  # Em dash
        "\u00a0": " ",  # Non-breaking space
        "\ufffd": "",   # Replacement character
    }
    for orig, rep in replacements.items():
        s = s.replace(orig, rep)
    return s


def normalize_whitespace(text: str) -> str:
    """Collapse any sequence of whitespace characters into a single space."""
    return " ".join(text.split())


def locate_verbatim_quote_offsets(raw_text: str, quote: str) -> Tuple[bool, Optional[int], Optional[int], str]:
    """Find exact character offsets of quote in raw_text allowing whitespace variance.
    
    Returns:
        (found: bool, start_offset: Optional[int], end_offset: Optional[int], canonical_quote: str)
    """
    if not quote or not raw_text:
        return False, None, None, quote

    # 1. Direct exact substring match
    pos = raw_text.find(quote)
    if pos != -1:
        return True, pos, pos + len(quote), quote

    # 2. Direct match with typography normalization
    sanitized_raw = sanitize_typography(raw_text)
    sanitized_quote = sanitize_typography(quote)
    pos_sanitized = sanitized_raw.find(sanitized_quote)
    if pos_sanitized != -1:
        start_idx = pos_sanitized
        end_idx = pos_sanitized + len(sanitized_quote)
        canonical = raw_text[start_idx:end_idx]
        return True, start_idx, end_idx, canonical

    # 3. Regex token-based match (collapsing arbitrary whitespace, linebreaks, punctuation)
    tokens = [re.escape(t) for t in sanitized_quote.split() if t.strip()]
    if tokens:
        pattern_str = r"\s+".join(tokens)
        try:
            match = re.search(pattern_str, sanitized_raw, flags=re.IGNORECASE)
            if match:
                start_idx = match.start()
                end_idx = match.end()
                canonical = raw_text[start_idx:end_idx]
                return True, start_idx, end_idx, canonical
        except re.error:
            pass

    # 4. Trim wrapping quotes and trailing punctuation if model wrapped the string
    trimmed = sanitized_quote.strip(" \"'“”….,;")
    if trimmed and len(trimmed) >= 10:
        trimmed_tokens = [re.escape(t) for t in trimmed.split() if t.strip()]
        if trimmed_tokens:
            try:
                pattern_str = r"\s+".join(trimmed_tokens)
                match = re.search(pattern_str, sanitized_raw, flags=re.IGNORECASE)
                if match:
                    start_idx = match.start()
                    end_idx = match.end()
                    canonical = raw_text[start_idx:end_idx]
                    return True, start_idx, end_idx, canonical
            except re.error:
                pass

    # 5. Normalized whitespace check in case raw text has extreme formatting
    norm_raw = normalize_whitespace(sanitized_raw)
    norm_q = normalize_whitespace(sanitized_quote)
    if norm_q in norm_raw:
        norm_pos = norm_raw.find(norm_q)
        return True, norm_pos, norm_pos + len(norm_q), norm_q

    return False, None, None, quote


def verify_direction_quote(direction: ExtractedDirection, full_text: str) -> VerificationResult:
    """Verify that a direction's source_quote and deadline_phrase are verbatim substrings.
    
    1. Verifies source_quote is a verbatim substring; resolves character offsets.
    2. If deadline_phrase is present, verifies it is a verbatim substring. If not found, sets to None.
    3. If deadline sentence sits adjacent to source_quote, extends source_quote to include it.
    """
    quote = direction.source_quote.strip() if direction.source_quote else ""
    if not quote or len(quote) < 5:
        return VerificationResult(
            direction=direction,
            verified=False,
            rejection_reason="Source quote is empty or too short (<5 characters)",
        )

    found, start, end, canonical = locate_verbatim_quote_offsets(full_text, quote)
    if not found or start is None or end is None:
        sample_q = quote[:60] + "..." if len(quote) > 60 else quote
        return VerificationResult(
            direction=direction,
            verified=False,
            rejection_reason=f"Quote '{sample_q}' is not a verbatim substring of the judgment text.",
        )

    # Base verified direction
    updated_dir = direction.model_copy(
        update={
            "source_quote": canonical,
            "quote_start": start,
            "quote_end": end,
        }
    )

    deadline_verified = False
    quote_extended = False

    # Deadline phrase verification & sentence alignment
    raw_dl = direction.deadline_phrase.strip() if direction.deadline_phrase else ""
    if raw_dl:
        dl_found, dl_start, dl_end, dl_canon = locate_verbatim_quote_offsets(full_text, raw_dl)
        if dl_found and dl_start is not None and dl_end is not None:
            deadline_verified = True
            updated_dir = updated_dir.model_copy(update={"deadline_phrase": dl_canon})

            # Check if deadline sits inside or adjacent to source_quote
            if start <= dl_start and dl_end <= end:
                # Already fully inside source quote
                pass
            elif dl_start >= end and (dl_start - end) <= 350:
                # Sits in immediately succeeding sentence: extend source_quote to include it
                end_sent = full_text.find(".", dl_end)
                new_end = end_sent + 1 if (end_sent != -1 and (end_sent - dl_end) < 200) else dl_end
                extended_text = full_text[start:new_end].strip()
                updated_dir = updated_dir.model_copy(
                    update={
                        "source_quote": extended_text,
                        "quote_end": new_end,
                    }
                )
                quote_extended = True
                logger.info(f"Extended source_quote to include adjacent deadline sentence: offsets [{start}:{new_end}]")
            elif dl_end <= start and (start - dl_end) <= 350:
                # Sits in immediately preceding sentence: extend source_quote backwards
                prev_dot = full_text.rfind(".", 0, dl_start)
                new_start = prev_dot + 1 if (prev_dot != -1 and (dl_start - prev_dot) < 200) else dl_start
                extended_text = full_text[new_start:end].strip()
                updated_dir = updated_dir.model_copy(
                    update={
                        "source_quote": extended_text,
                        "quote_start": new_start,
                    }
                )
                quote_extended = True
                logger.info(f"Extended source_quote backwards to include adjacent deadline sentence: offsets [{new_start}:{end}]")
            else:
                logger.info(f"Deadline phrase '{raw_dl}' verified at [{dl_start}:{dl_end}] (distance {abs(dl_start - end)} chars from quote).")
        else:
            logger.warning(f"Deadline phrase '{raw_dl}' is NOT a verbatim substring of judgment text. Setting deadline_phrase to null.")
            updated_dir = updated_dir.model_copy(update={"deadline_phrase": None})

    return VerificationResult(
        direction=updated_dir,
        verified=True,
        normalized_matched=True,
        deadline_verified=deadline_verified,
        quote_extended=quote_extended,
    )


def verify_all_directions(directions: list[ExtractedDirection], full_text: str) -> list[VerificationResult]:
    """Verify a collection of extracted directions against judgment text."""
    return [verify_direction_quote(d, full_text) for d in directions]
