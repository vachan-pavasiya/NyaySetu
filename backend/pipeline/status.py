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
) -> Tuple[str, Dict[str, bool], str, Optional[int]]:
    """Determine headline status and secondary flags per the STATUS MODEL.
    
    Headline statuses are exactly three: COMPLIED, PENDING, UNVERIFIED.
    Secondary flags: CONTEMPT_FILED, EXTENSION_SOUGHT, OVERDUE_NO_RECORD, CONTEMPT_DISMISSED_FOR_DEFAULT.
    
    Returns:
        (headline_status: str, flags: Dict[str, bool], reason: str, primary_evidence_id: Optional[int])
    """
    invalid_ids = invalid_judgment_ids or set()

    # Filter temporally valid evidence
    valid_evidence = [e for e in evidence_list if e.source_judgment_id not in invalid_ids]

    flags = {
        "contempt_filed": False,
        "extension_sought": False,
        "overdue_no_record": False,
        "contempt_dismissed_for_default": False,
    }

    # Inspect all evidence for secondary flags
    for ev in evidence_list:
        if ev.verdict == "NON_COMPLIANCE_ALLEGED":
            flags["contempt_filed"] = True
        elif ev.verdict == "NOTICE_ISSUED":
            flags["contempt_filed"] = True
        elif ev.verdict == "EXTENSION_SOUGHT":
            flags["extension_sought"] = True
        elif ev.verdict == "DISMISSED_FOR_DEFAULT":
            flags["contempt_dismissed_for_default"] = True

    # -------------------------------------------------------------
    # RULE 1: COMPLIED
    # COMPLIED only when a linked later order has a verified verbatim quote supporting compliance.
    # -------------------------------------------------------------
    for ev in valid_evidence:
        if ev.verdict == "COMPLIANCE_SHOWN" and ev.verified:
            reason = (
                f"Verified compliance recorded in later order {ev.source_case_number} "
                f"dated {ev.source_date}: \"{ev.supporting_quote}\""
            )
            return "COMPLIED", flags, reason, ev.id

    # -------------------------------------------------------------
    # RULE 2: PENDING
    # PENDING when deadline window is open, or later order shows ongoing process.
    # -------------------------------------------------------------
    for ev in valid_evidence:
        if ev.verdict in ("EXTENSION_SOUGHT", "NOTICE_ISSUED"):
            reason = (
                f"Follow-up order {ev.source_case_number} dated {ev.source_date} "
                f"shows ongoing process ({ev.verdict}): \"{ev.supporting_quote}\""
            )
            return "PENDING", flags, reason, ev.id

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


def update_all_direction_statuses(db: Session) -> Dict[str, Any]:
    """Execute deterministic status engine across all directions in database."""
    directions = db.query(Direction).all()
    evidence_all = db.query(Evidence).all()
    case_links = db.query(CaseLink).all()

    # Map temporally invalid later judgment IDs per earlier judgment
    invalid_links_by_orig: Dict[int, set] = {}
    for link in case_links:
        if link.link_confidence == "LOW" or "Temporal conflict" in (link.note or ""):
            invalid_links_by_orig.setdefault(link.from_judgment_id, set()).add(link.to_judgment_id)

    # Group evidence by direction_id
    evidence_by_dir: Dict[int, List[Evidence]] = {}
    for ev in evidence_all:
        evidence_by_dir.setdefault(ev.direction_id, []).append(ev)

    updated_count = 0
    status_summary = {"COMPLIED": 0, "PENDING": 0, "UNVERIFIED": 0}
    overdue_count = 0

    for d in directions:
        ev_list = evidence_by_dir.get(d.id, [])
        invalid_ids = invalid_links_by_orig.get(d.judgment_id, set())

        new_status, flags, reason, primary_ev_id = evaluate_direction_status(d, ev_list, invalid_ids)
        status_summary[new_status] = status_summary.get(new_status, 0) + 1
        if flags["overdue_no_record"]:
            overdue_count += 1

        old_status = d.compliance_status
        status_changed = (old_status != new_status)
        flags_changed = (
            d.overdue_no_record != flags["overdue_no_record"]
            or d.contempt_filed != flags["contempt_filed"]
            or d.extension_sought != flags["extension_sought"]
            or d.contempt_dismissed_for_default != flags["contempt_dismissed_for_default"]
        )

        if status_changed or flags_changed or not d.status_history:
            d.compliance_status = new_status
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
        "overdue_no_record_count": overdue_count,
        "directions_updated": updated_count,
    }

