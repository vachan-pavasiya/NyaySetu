"""Operative order segmentation module.

Role: Identifies and isolates the operative portion of a High Court judgment containing
      actionable directions, computing exact character offsets.
Data flow: Full judgment text -> Heuristic pattern matcher / LLM fallback -> OperativeSegmentResult.
"""

import re
import logging
from typing import Optional, Tuple
from backend.pipeline.models import OperativeSegmentResult

logger = logging.getLogger("compliance_radar.segment")

# Explicit dismissals / withdrawals without positive relief
DISMISSAL_PATTERNS = [
    r"leave\s+to\s+withdraw\s+(?:is|has\s+been)\s+granted",
    r"prays?\s+for\s+leave\s+to\s+withdraw[^\.\n]*\.\s*(?:In\s+view\s+thereof|Leave\s+is\s+granted)[^\.\n]*dismissed\s+as\s+withdrawn",
    r"(?:writ\s+petition|application|petition|appeal)\s+(?:is|stands)\s+dismissed\s+for\s+default",
    r"(?:writ\s+petition|application|petition|appeal)\s+(?:is|stands)\s+dismissed\s+as\s+infructuous",
    r"(?:writ\s+petition|application|petition|appeal)\s+(?:is|stands)\s+dismissed\s+as\s+withdrawn",
    r"dismissed\s+for\s+non-prosecution",
    r"no\s+merit\s+in\s+the\s+(?:writ\s+petition|application)[^\.\n]*dismissed",
]

# Markers denoting transition to operative directions
OPERATIVE_MARKERS = [
    r"(?:in\s+view\s+of\s+the\s+(?:above|foregoing|discussions|facts|observations)[,\s]+)",
    r"(?:under\s+such\s+circumstances[,\s]+)",
    r"(?:having\s+heard\s+the\s+learned\s+counsel[^\.\n]*,\s*this\s+Court\s+directs)",
    r"(?:the\s+respondent[s]?\s+(?:is|are|shall\s+be)\s+directed\s+to)",
    r"(?:this\s+Court\s+(?:is\s+pleased\s+to\s+direct|directs\s+the))",
    r"(?:we\s+direct\s+that|I\s+direct\s+that|it\s+is\s+directed\s+that)",
    r"(?:it\s+is\s+hereby\s+ordered\s+and\s+directed)",
    r"(?:it\s+is\s+ordered\s+that)",
    r"(?:accordingly[,\s]+the\s+(?:writ\s+petition|application)\s+is\s+(?:disposed\s+of|allowed)\s+with)",
    r"(?:accordingly[,\s]+the\s+respondent)",
    r"(?:the\s+writ\s+petition\s+is\s+(?:disposed\s+of|allowed)\s+(?:by|with)\s+directing)",
    r"(?:\n\s*(?:\(?[1-9]\)|\(?[iIvVxX]+\)|\d+\.)\s+(?:The\s+respondent|That\s+the|Respondent))",
]

# Directional keywords that must be present in operative segment
DIRECTION_INDICATORS = [
    r"\bdirected\s+to\b",
    r"\bshall\s+(?:consider|decide|dispose|pass|release|disburse|take|comply|produce)\b",
    r"\bis\s+directed\b",
    r"\bare\s+directed\b",
    r"\bwithin\s+(?:\w+\s+)?(?:weeks?|months?|days?|fortnight)\b",
    r"\bat\s+liberty\s+to\b",
    r"\bhearing\s+shall\s+be\s+given\b",
]


def check_is_pure_dismissal(text: str) -> bool:
    """Return True if document is an outright dismissal/withdrawal without directions."""
    clean = text.lower()
    for pattern in DISMISSAL_PATTERNS:
        match = re.search(pattern, clean)
        if match:
            # Check if there are contradictory positive directions after the dismissal phrase
            tail = clean[match.end():]
            has_counter_direction = any(re.search(ind, tail) for ind in [r"however", r"subject to", r"directed to"])
            if not has_counter_direction:
                return True
    return False


def find_heuristic_boundaries(text: str) -> Optional[Tuple[int, int]]:
    """Locate the starting character offset of the operative part."""
    earliest_pos = None

    for marker in OPERATIVE_MARKERS:
        for match in re.finditer(marker, text, flags=re.IGNORECASE):
            pos = match.start()
            # Ensure the segment after this marker contains at least one actionable verb
            segment_candidate = text[pos:]
            has_actionable_verb = any(re.search(ind, segment_candidate, flags=re.IGNORECASE) for ind in DIRECTION_INDICATORS)
            if has_actionable_verb:
                if earliest_pos is None or pos < earliest_pos:
                    earliest_pos = pos

    if earliest_pos is not None:
        # Extend backwards to beginning of paragraph/line if reasonable
        line_start = text.rfind("\n", 0, earliest_pos)
        start_char = max(0, line_start + 1 if line_start != -1 else earliest_pos)
        end_char = len(text)
        return start_char, end_char

    return None


def segment_operative_part(judgment_text: Optional[str]) -> OperativeSegmentResult:
    """Segment operative portion of judgment text.
    
    Returns OperativeSegmentResult with segment_text, start_char, end_char, and method.
    """
    if not judgment_text or len(judgment_text.strip()) < 50:
        return OperativeSegmentResult(has_directions=False, method="none")

    # 1. Check for pure dismissals / unmerited withdrawals
    if check_is_pure_dismissal(judgment_text):
        logger.info("Order identified as dismissal / withdrawal without positive relief.")
        return OperativeSegmentResult(has_directions=False, method="heuristic_dismissal")

    # 2. Heuristic boundary detection
    boundaries = find_heuristic_boundaries(judgment_text)
    if boundaries:
        start, end = boundaries
        segment_text = judgment_text[start:end].strip()
        logger.info(f"Heuristic segmentation successful: offsets [{start}:{end}], length: {len(segment_text)}")
        return OperativeSegmentResult(
            has_directions=True,
            segment_text=segment_text,
            start_char=start,
            end_char=end,
            method="heuristic",
        )

    # 3. Fallback: Check if document has direction keywords anywhere
    has_direction_anywhere = any(
        re.search(ind, judgment_text, flags=re.IGNORECASE) for ind in DIRECTION_INDICATORS
    )
    if has_direction_anywhere:
        # If order is short (e.g. <3000 chars), whole body is relevant
        if len(judgment_text) <= 3000:
            return OperativeSegmentResult(
                has_directions=True,
                segment_text=judgment_text.strip(),
                start_char=0,
                end_char=len(judgment_text),
                method="heuristic_full",
            )
        # Otherwise take the final 45% where operative conclusions reside
        cutoff = int(len(judgment_text) * 0.55)
        line_break = judgment_text.find("\n", cutoff)
        start = line_break if line_break != -1 else cutoff
        return OperativeSegmentResult(
            has_directions=True,
            segment_text=judgment_text[start:].strip(),
            start_char=start,
            end_char=len(judgment_text),
            method="heuristic_tail_fallback",
        )

    # No directions detected
    return OperativeSegmentResult(has_directions=False, method="none")
