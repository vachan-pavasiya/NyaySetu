"""Deterministic compliance status resolution engine.

Role: Evaluates directions against deadline buckets, temporal validity, and linked follow-up order evidence
      to deterministically compute compliance status (COMPLIED, PENDING, UNVERIFIED) and secondary flags,
      logging every state transition to the direction_status_history audit ledger.
Data flow: Direction + Deadline Bucket + Verified Evidence -> Status Rules -> SQLite Direction & DirectionStatusHistory.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.models import (
    CaseLink,
    Direction,
    DirectionStatusHistory,
    Evidence,
    Judgment,
)

logger = logging.getLogger("compliance_radar.status")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def evaluate_direction_status(
    direction: Direction,
    evidence_list: List[Evidence],
    invalid_judgment_ids: Optional[set] = None,
    has_contempt_link: bool = False,
) -> Tuple[str, Dict[str, bool], str, Optional[int]]:
    """Determine headline status and secondary flags per the STATUS MODEL.
    
    Headline statuses are exactly three: COMPLIED, PENDING, UNVERIFIED.
    Secondary flags: CONTEMPT_FILED, EXTENSION_SOUGHT, OVERDUE_NO_RECORD, CONTEMPT_DISMISSED_FOR_DEFAULT.

    Rules:
    - COMPLIED only when a linked later order has a verified verbatim quote supporting compliance.
      Never infer compliance from silence, filing, dismissal, or disposal without finding.
      Never mark COMPLIED for directions of type 'liberty'.
    - PENDING when deadline window is open, or later order shows ongoing process (extension sought,
      compliance report awaited, notice issued, ongoing efforts directed).
    - UNVERIFIED default when no evidence either way (overdue_no_record=True if deadline lapsed).
    
    Returns:
        (headline_status: str, flags: Dict[str, bool], reason: str, primary_evidence_id: Optional[int])
    """
    invalid_ids = invalid_judgment_ids or set()

    # Filter temporally valid evidence
    valid_evidence = [e for e in evidence_list if e.source_judgment_id not in invalid_ids]

    flags = {
        "contempt_filed": has_contempt_link,
        "extension_sought": False,
        "overdue_no_record": False,
        "contempt_dismissed_for_default": False,
    }

    # Inspect all evidence for secondary flags
    for ev in evidence_list:
        case_no = ev.source_case_number or ""
        if any(prefix in case_no for prefix in ("CPAN", "WPCRC", "CRC")):
            flags["contempt_filed"] = True

        if ev.verdict in ("NON_COMPLIANCE_ALLEGED", "NOTICE_ISSUED"):
            flags["contempt_filed"] = True
        elif ev.verdict == "EXTENSION_SOUGHT":
            flags["extension_sought"] = True
        elif ev.verdict == "DISMISSED_FOR_DEFAULT":
            flags["contempt_dismissed_for_default"] = True

    # Helper: Check if evidence represents an ongoing compliance process rather than completed compliance
    def is_ongoing_process(ev: Evidence) -> bool:
        # Primary signal: Explicit verdict ONGOING_PROCESS from LLM classification
        if ev.verdict == "ONGOING_PROCESS":
            return True
        if ev.verdict in ("EXTENSION_SOUGHT", "NOTICE_ISSUED"):
            return True

        # Fallback keyword list: used ONLY when verdict is not ONGOING_PROCESS
        import re
        quote_clean = re.sub(r"\s+", " ", (ev.supporting_quote or "")).lower()
        reasoning_clean = re.sub(r"\s+", " ", (ev.reasoning or "")).lower()
        ongoing_phrases = (
            "continues to make efforts",
            "shall continue to do so",
            "shall sit with",
            "shall be considered",
            "pending before",
            "compliance report awaited",
            "compliance report filed",
            "recommendation for transfer has been sent",
        )
        affirmative_phrases = (
            "has complied",
            "complied with",
            "recording compliance",
            "substantially been complied with",
        )
        if any(p in quote_clean for p in affirmative_phrases):
            return False

        matched_phrase = next((p for p in ongoing_phrases if p in quote_clean), None)
        if not matched_phrase and any(p in reasoning_clean for p in ("ongoing", "pending", "in progress")):
            matched_phrase = "reasoning text"

        if matched_phrase:
            logger.warning(
                f"[FALLBACK FIRED] Ongoing process keyword fallback triggered ('{matched_phrase}') "
                f"for Direction ID {direction.id}, Evidence ID {ev.id}"
            )
            return True

        return False

    ongoing_ev = next((e for e in valid_evidence if is_ongoing_process(e)), None)

    # -------------------------------------------------------------
    # RULE 1: COMPLIED
    # COMPLIED only when a linked later order has a verified verbatim quote supporting compliance.
    # Never infer compliance from silence, dismissal, disposal without finding, or filing.
    # Directions of type 'liberty' (rights given to petitioner/appellant) cannot be complied by contemnor.
    # -------------------------------------------------------------
    if direction.direction_type != "liberty":
        for ev in valid_evidence:
            if ev.verdict == "COMPLIANCE_SHOWN" and ev.verified and not is_ongoing_process(ev):
                quote_lower = (ev.supporting_quote or "").lower()
                affirmative_compliance = any(
                    term in quote_lower for term in (
                        "complied with",
                        "has complied",
                        "recording compliance",
                        "substantially been complied with",
                    )
                )
                if affirmative_compliance:
                    reason = (
                        f"Verified compliance recorded in later order {ev.source_case_number} "
                        f"dated {ev.source_date}: \"{ev.supporting_quote}\""
                    )
                    return "COMPLIED", flags, reason, ev.id

    # -------------------------------------------------------------
    # RULE 2: PENDING
    # PENDING when deadline window is open, or later order shows ongoing process.
    # -------------------------------------------------------------
    if ongoing_ev:
        reason = (
            f"Follow-up order {ongoing_ev.source_case_number} dated {ongoing_ev.source_date} "
            f"shows ongoing compliance process: \"{ongoing_ev.supporting_quote}\""
        )
        return "PENDING", flags, reason, ongoing_ev.id

    if direction.deadline_status in ("UPCOMING", "IN_WINDOW"):
        reason = (
            f"Deadline window is open ({direction.deadline_status}) until "
            f"{direction.deadline_window_end or 'unspecified date'}."
        )
        return "PENDING", flags, reason, None

    # -------------------------------------------------------------
    # RULE 3: UNVERIFIED
    # Default when there is no evidence either way.
    # -------------------------------------------------------------
    reasons = []
    if direction.deadline_status == "LAPSED":
        flags["overdue_no_record"] = True
        reasons.append(
            f"Deadline window lapsed on {direction.deadline_window_end} with no record of compliance."
        )
    elif direction.deadline_status == "DEPENDENT":
        reasons.append(
            "Direction is dependent on prior events; no deadline date can be computed."
        )
    elif direction.deadline_status == "AMBIGUOUS":
        reasons.append(
            "Direction deadline phrase is ambiguous without explicit order date reference."
        )
    else:
        reasons.append(
            "No deadline or subsequent compliance verification record found."
        )

    if flags["contempt_dismissed_for_default"]:
        reasons.append(
            "Linked contempt petition was dismissed for default (petitioner absent); does not prove compliance."
        )
    if flags["contempt_filed"]:
        reasons.append("Contempt petition filed alleging non-compliance.")

    combined_reason = " ".join(reasons)
    primary_ev_id = valid_evidence[0].id if valid_evidence else None

    return "UNVERIFIED", flags, combined_reason, primary_ev_id


def update_evidence_metadata(db: Session) -> Dict[str, Any]:
    """Calculate and persist evidence_strength, evidence_scope, and directions_covered_count.
    
    Refinements:
    - evidence_strength: COURT_RECORDED (court itself records compliance) vs PARTY_SUBMISSION (counsel/party states compliance).
    - evidence_scope: For directions that share the same linked order and the same compliance quote,
      evidence_scope = CASE_LEVEL and directions_covered_count = count. Otherwise DIRECTION_SPECIFIC.
    """
    import re
    from backend.pipeline.linking import determine_evidence_strength

    evidences = db.query(Evidence).all()

    # 1. Update evidence_strength where applicable
    for ev in evidences:
        if not ev.evidence_strength and ev.supporting_quote:
            strength = determine_evidence_strength(ev.supporting_quote)
            if strength:
                ev.evidence_strength = strength

    # 2. Group by (source_judgment_id, normalized_quote) to identify case-level coverage
    groups: Dict[Tuple[int, str], List[Evidence]] = {}
    for ev in evidences:
        norm_q = re.sub(r"\s+", " ", (ev.supporting_quote or "")).strip().lower()
        key = (ev.source_judgment_id or 0, norm_q)
        groups.setdefault(key, []).append(ev)

    case_level_count = 0
    dir_specific_count = 0

    for key, ev_list in groups.items():
        count = len(ev_list)
        scope = "CASE_LEVEL" if count > 1 else "DIRECTION_SPECIFIC"
        for ev in ev_list:
            ev.evidence_scope = scope
            ev.directions_covered_count = count
            if scope == "CASE_LEVEL":
                case_level_count += 1
            else:
                dir_specific_count += 1

    db.commit()
    return {
        "case_level_evidence_count": case_level_count,
        "direction_specific_evidence_count": dir_specific_count,
    }


def update_all_direction_statuses(db: Session) -> Dict[str, Any]:
    """Execute deterministic status engine across all directions in database."""
    # First update evidence metadata (strength, scope, directions covered)
    update_evidence_metadata(db)

    directions = db.query(Direction).all()
    evidence_all = db.query(Evidence).all()
    case_links = db.query(CaseLink).all()

    # Map temporally invalid later judgment IDs per earlier judgment
    invalid_links_by_orig: Dict[int, set] = {}
    # Track judgments that have a high-confidence CONTEMPT_FILED link
    contempt_linked_judgments: set = set()

    for link in case_links:
        if link.link_confidence == "LOW" or "Temporal conflict" in (link.note or ""):
            invalid_links_by_orig.setdefault(link.from_judgment_id, set()).add(link.to_judgment_id)
        elif link.link_type == "CONTEMPT_FILED":
            contempt_linked_judgments.add(link.from_judgment_id)

    # Group evidence by direction_id
    evidence_by_dir: Dict[int, List[Evidence]] = {}
    for ev in evidence_all:
        evidence_by_dir.setdefault(ev.direction_id, []).append(ev)

    updated_count = 0
    status_summary = {"COMPLIED": 0, "PENDING": 0, "UNVERIFIED": 0}
    flags_summary = {
        "contempt_filed": 0,
        "extension_sought": 0,
        "overdue_no_record": 0,
        "contempt_dismissed_for_default": 0,
    }
    strength_summary = {"COURT_RECORDED": 0, "PARTY_SUBMISSION": 0}
    case_level_directions = 0

    for d in directions:
        ev_list = evidence_by_dir.get(d.id, [])
        invalid_ids = invalid_links_by_orig.get(d.judgment_id, set())
        has_contempt = d.judgment_id in contempt_linked_judgments

        new_status, flags, reason, primary_ev_id = evaluate_direction_status(
            d, ev_list, invalid_ids, has_contempt_link=has_contempt
        )
        status_summary[new_status] = status_summary.get(new_status, 0) + 1
        for k in flags_summary:
            if flags.get(k):
                flags_summary[k] += 1

        # Track evidence strength & scope for primary evidence
        if primary_ev_id:
            primary_ev = next((e for e in ev_list if e.id == primary_ev_id), None)
            if primary_ev:
                if primary_ev.evidence_strength in strength_summary:
                    strength_summary[primary_ev.evidence_strength] += 1
                if primary_ev.evidence_scope == "CASE_LEVEL":
                    case_level_directions += 1

        old_status = d.compliance_status
        status_changed = (old_status != new_status)
        sub_reason_changed = (d.sub_reason != reason)
        flags_changed = (
            d.overdue_no_record != flags["overdue_no_record"]
            or d.contempt_filed != flags["contempt_filed"]
            or d.extension_sought != flags["extension_sought"]
            or d.contempt_dismissed_for_default != flags["contempt_dismissed_for_default"]
        )

        if status_changed or flags_changed or sub_reason_changed or not d.status_history:
            d.compliance_status = new_status
            d.sub_reason = reason
            d.overdue_no_record = flags["overdue_no_record"]
            d.contempt_filed = flags["contempt_filed"]
            d.has_contempt_flag = flags["contempt_filed"]
            d.extension_sought = flags["extension_sought"]
            d.contempt_dismissed_for_default = flags["contempt_dismissed_for_default"]

            # Linked judgment ID if evidence present
            linked_jid = None
            if primary_ev_id:
                ev_obj = next((e for e in ev_list if e.id == primary_ev_id), None)
                if ev_obj:
                    linked_jid = ev_obj.source_judgment_id

            # Write audit history
            history_entry = DirectionStatusHistory(
                direction_id=d.id,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
                linked_judgment_id=linked_jid,
                evidence_id=primary_ev_id,
                model_used="deterministic_status_rules",
                method="rule_based",
                timestamp=datetime.now(timezone.utc),
            )
            db.add(history_entry)
            updated_count += 1

    db.commit()

    return {
        "total_directions": len(directions),
        "status_distribution": status_summary,
        "flags_distribution": flags_summary,
        "evidence_strength_distribution": strength_summary,
        "case_level_directions_count": case_level_directions,
        "directions_updated": updated_count,
    }

