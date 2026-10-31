"""Verifier module for extracted court directions.

Role: Verifies that extracted source quotes and deadline phrases are verbatim substrings of the source judgment text
      (normalising whitespace). Extends source quote to include adjacent deadline sentences, and deduplicates
      directions with overlapping/subsumed quotes for the same party.
Data flow: ExtractedDirection -> verify_direction_quote -> VerificationResult (offsets, confidence adjustment, quote extension)
           -> deduplicate_verified_directions.
"""

import re
import logging
from typing import Optional, List
from backend.pipeline.models import ExtractedDirection, VerificationResult

logger = logging.getLogger("compliance_radar.verify")


def normalize_whitespace(text: str) -> str:
    """Collapses consecutive whitespace and trims ends."""
    return " ".join(text.split())


def find_normalized_substring(needle: str, haystack: str) -> Optional[tuple[int, int]]:
    """Locates needle in haystack after normalizing whitespace.

    Returns the character offsets (start, end) in the original haystack,
    or None if needle does not occur verbatim.
    """
    norm_needle = normalize_whitespace(needle)
    if not norm_needle:
        return None

    # Exact raw search first
    raw_idx = haystack.find(needle)
    if raw_idx != -1:
        return (raw_idx, raw_idx + len(needle))

    # Tokenized regex search preserving original character offsets
    tokens = norm_needle.split(" ")
    escaped_tokens = [re.escape(t) for t in tokens]
    pattern = r"\s+".join(escaped_tokens)

    match = re.search(pattern, haystack)
    if match:
        return (match.start(), match.end())

    return None


# Alias for backward compatibility
locate_verbatim_quote_offsets = find_normalized_substring


def verify_direction_quote(direction: ExtractedDirection, full_text: str) -> VerificationResult:
    """Verifies that source_quote is a verbatim substring of full_text.

    Also verifies deadline_phrase is a verbatim substring of full_text and sits within
    or adjacent to the direction. Extends source_quote to include adjacent deadline sentences.
    """
    raw_quote = direction.source_quote
    if not raw_quote or not raw_quote.strip():
        return VerificationResult(
            direction=direction,
            verified=False,
            rejection_reason="Empty source quote",
        )

    offsets = find_normalized_substring(raw_quote, full_text)
    if not offsets:
        logger.warning(f"Verification rejected quote: '{raw_quote[:60]}...' not found in source text.")
        return VerificationResult(
            direction=direction,
            verified=False,
            rejection_reason="Quote is not a verbatim substring of the judgment text",
        )

    start, end = offsets
    updated_dir = direction.model_copy(
        update={
            "quote_start": start,
            "quote_end": end,
            "confidence": max(direction.confidence, 0.95),
        }
    )

    # ------------------------------------------------------------------
    # Verify deadline phrase and check proximity / adjacent extension
    # ------------------------------------------------------------------
    deadline_verified = False
    quote_extended = False
    raw_dl = direction.deadline_phrase

    if raw_dl and raw_dl.strip():
        dl_offsets = find_normalized_substring(raw_dl, full_text)
        if dl_offsets:
            deadline_verified = True
            dl_start, dl_end = dl_offsets

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


def deduplicate_verified_directions(directions: list[ExtractedDirection]) -> list[ExtractedDirection]:
    """Deduplicates directions for the same responsible party with overlapping/subsumed quote offsets.
    
    When an earlier direction was extended to include an adjacent deadline sentence,
    a secondary extraction of the same sentence (e.g. penalty/default clause) becomes a duplicate.
    Keeps the broader/more comprehensive direction and removes the subsumed fragment.
    """
    if len(directions) <= 1:
        return directions

    to_remove = set()
    for i in range(len(directions)):
        for j in range(len(directions)):
            if i == j or j in to_remove:
                continue
            d1, d2 = directions[i], directions[j]
            s1, e1 = d1.quote_start, d1.quote_end
            s2, e2 = d2.quote_start, d2.quote_end
            if s1 is not None and e1 is not None and s2 is not None and e2 is not None:
                # Same responsible party
                same_party = d1.responsible_party.strip().lower() == d2.responsible_party.strip().lower()
                # Check if d2 is completely subsumed by d1
                if s1 <= s2 and e1 >= e2 and (e1 - s1) > (e2 - s2) and same_party:
                    to_remove.add(j)
                    logger.info(
                        f"Deduplicated direction: '{d2.action[:50]}' subsumed by '{d1.action[:50]}' "
                        f"for party '{d1.responsible_party}' [{s2}:{e2}] in [{s1}:{e1}]"
                    )

    return [d for idx, d in enumerate(directions) if idx not in to_remove]
