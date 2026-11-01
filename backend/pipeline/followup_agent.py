"""Follow-up Case Linking and Compliance Analysis Engine.

Role: Whenever a judgment is ingested and analysed (or on full database rescan), automatically discovers
      candidate links to directions, evaluates follow-up orders with Gemini, verifies quotes verbatim
      with feedback retries, deterministically updates compliance statuses and audit histories,
      and records structured run telemetry into the agent_runs table.
Data flow: Trigger (Ingestion / Rescan) -> Candidate Discovery -> LLM Classification ->
           Verbatim Verifier (with retry) -> CaseLink & Evidence Persistence -> Status Recomputation ->
           DirectionStatusHistory & AgentRun DB logging.
"""

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Set

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database import SessionLocal
from backend.app.models import (
    AgentRun,
    CaseLink,
    Direction,
    DirectionStatusHistory,
    Evidence,
    Judgment,
    LLMCache,
)
from backend.pipeline.linking import (
    FOLLOW_UP_SYSTEM_PROMPT,
    build_cache_key,
    check_temporal_sanity,
    determine_evidence_strength,
    extract_header_citations,
    normalize_case_citation,
    verify_follow_up_quote,
)
from backend.pipeline.status import (
    evaluate_direction_status,
    update_evidence_metadata,
)

logger = logging.getLogger("compliance_radar.followup_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

settings = get_settings()


class FollowUpAnalysisAgent:
    """State machine engine for follow-up order linking and status resolution."""

    def __init__(
        self,
        source_judgment: Optional[Judgment] = None,
        trigger: str = "INGEST_ANALYSIS",
    ):
        self.source_judgment = source_judgment
        self.trigger = trigger
        self.step_logs: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.directions_checked = 0
        self.directions_updated = 0
        self.start_time = time.perf_counter()

    def log_step(
        self,
        step_name: str,
        status: str,
        duration: float,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Record step-level telemetry with status and duration."""
        entry = {
            "step": step_name,
            "status": status,
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details or {},
        }
        self.step_logs.append(entry)
        logger.info(
            f"[{self.trigger}] {step_name} -> {status} ({duration:.3f}s): {details or {}}"
        )

    def find_candidates(self, db: Session) -> List[Dict[str, Any]]:
        """Identify candidate earlier directions that may relate to the source judgment (or all pairs)."""
        t0 = time.perf_counter()
        candidates: List[Dict[str, Any]] = []
        seen_pairs: Set[Tuple[int, int]] = set()

        if self.source_judgment:
            target_judgments = [self.source_judgment]
        else:
            target_judgments = db.query(Judgment).filter(Judgment.status == "INGESTED").all()

        # Build index of judgments by normalized case number and CNR
        all_judgments = db.query(Judgment).filter(Judgment.status == "INGESTED").all()
        j_by_case: Dict[str, List[Judgment]] = {}
        j_by_cnr: Dict[str, List[Judgment]] = {}
        for j in all_judgments:
            norm = normalize_case_citation(j.case_number)
            if norm:
                j_by_case.setdefault(norm, []).append(j)
            if j.cnr:
                j_by_cnr.setdefault(j.cnr.strip(), []).append(j)

        for j in target_judgments:
            # 1. Header citations in j's text pointing to earlier judgments
            citations = extract_header_citations(j.text or "", j.case_number)
            for raw_cit, norm_cit in citations:
                for earlier_j in j_by_case.get(norm_cit, []):
                    if earlier_j.id == j.id:
                        continue
                    is_valid_time, time_reason = check_temporal_sanity(
                        earlier_j.judgment_date, j.judgment_date, earlier_j.case_number, j.case_number
                    )
                    for d in earlier_j.directions:
                        pair = (d.id, j.id)
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            candidates.append({
                                "direction": d,
                                "original_judgment": earlier_j,
                                "follow_up_judgment": j,
                                "link_type": "CONTEMPT_FILED",
                                "link_signal": "contempt_citation",
                                "link_confidence": "HIGH" if is_valid_time else "LOW",
                                "citation_text": raw_cit,
                                "is_temporally_valid": is_valid_time,
                                "time_reason": time_reason,
                            })

            # 2. Same CNR
            if j.cnr and j.cnr.strip() in j_by_cnr:
                for match_j in j_by_cnr[j.cnr.strip()]:
                    if match_j.id == j.id:
                        continue
                    # Order chronologically
                    if (
                        match_j.judgment_date
                        and j.judgment_date
                        and match_j.judgment_date <= j.judgment_date
                    ):
                        earlier_j, later_j = match_j, j
                    else:
                        earlier_j, later_j = j, match_j

                    is_valid_time, time_reason = check_temporal_sanity(
                        earlier_j.judgment_date, later_j.judgment_date, earlier_j.case_number, later_j.case_number
                    )
                    for d in earlier_j.directions:
                        pair = (d.id, later_j.id)
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            candidates.append({
                                "direction": d,
                                "original_judgment": earlier_j,
                                "follow_up_judgment": later_j,
                                "link_type": "OTHER",
                                "link_signal": "same_cnr",
                                "link_confidence": "HIGH" if is_valid_time else "LOW",
                                "citation_text": j.cnr,
                                "is_temporally_valid": is_valid_time,
                                "time_reason": time_reason,
                            })

            # 3. Same case number on different date
            norm_j_case = normalize_case_citation(j.case_number)
            if norm_j_case and norm_j_case in j_by_case:
                for match_j in j_by_case[norm_j_case]:
                    if match_j.id == j.id:
                        continue
                    if (
                        match_j.judgment_date
                        and j.judgment_date
                        and match_j.judgment_date < j.judgment_date
                    ):
                        earlier_j, later_j = match_j, j
                    elif (
                        match_j.judgment_date
                        and j.judgment_date
                        and j.judgment_date < match_j.judgment_date
                    ):
                        earlier_j, later_j = j, match_j
                    else:
                        continue

                    is_valid_time, time_reason = check_temporal_sanity(
                        earlier_j.judgment_date, later_j.judgment_date, earlier_j.case_number, later_j.case_number
                    )
                    for d in earlier_j.directions:
                        pair = (d.id, later_j.id)
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            candidates.append({
                                "direction": d,
                                "original_judgment": earlier_j,
                                "follow_up_judgment": later_j,
                                "link_type": "OTHER",
                                "link_signal": "same_case_number",
                                "link_confidence": "HIGH" if is_valid_time else "LOW",
                                "citation_text": norm_j_case,
                                "is_temporally_valid": is_valid_time,
                                "time_reason": time_reason,
                            })

            # 4. If j is an earlier writ, check if other existing orders cite j
            if norm_j_case:
                for other_j in all_judgments:
                    if other_j.id == j.id:
                        continue
                    other_cits = extract_header_citations(other_j.text or "", other_j.case_number)
                    for raw_c, norm_c in other_cits:
                        if norm_c == norm_j_case:
                            is_valid_time, time_reason = check_temporal_sanity(
                                j.judgment_date, other_j.judgment_date, j.case_number, other_j.case_number
                            )
                            for d in j.directions:
                                pair = (d.id, other_j.id)
                                if pair not in seen_pairs:
                                    seen_pairs.add(pair)
                                    candidates.append({
                                        "direction": d,
                                        "original_judgment": j,
                                        "follow_up_judgment": other_j,
                                        "link_type": "CONTEMPT_FILED",
                                        "link_signal": "contempt_citation",
                                        "link_confidence": "HIGH" if is_valid_time else "LOW",
                                        "citation_text": raw_c,
                                        "is_temporally_valid": is_valid_time,
                                        "time_reason": time_reason,
                                    })

        cand_dur = time.perf_counter() - t0
        self.log_step(
            "FIND_CANDIDATES",
            "COMPLETED",
            cand_dur,
            {
                "candidates_count": len(candidates),
                "source_judgment_id": self.source_judgment.id if self.source_judgment else None,
                "source_case": self.source_judgment.case_number if self.source_judgment else "ALL",
            },
        )
        return candidates

    def classify_and_verify(
        self,
        candidate: Dict[str, Any],
        db: Session,
    ) -> Optional[Dict[str, Any]]:
        """Run classification, verbatim verification, and single feedback retry for a candidate."""
        direction: Direction = candidate["direction"]
        later_j: Judgment = candidate["follow_up_judgment"]
        orig_j: Judgment = candidate["original_judgment"]

        # Temporal conflict: do not classify compliance, record low-confidence link
        if not candidate["is_temporally_valid"]:
            self.log_step(
                "TEMPORAL_SANITY",
                "FAILED",
                0.001,
                {
                    "direction_id": direction.id,
                    "reason": candidate["time_reason"],
                    "earlier_date": str(orig_j.judgment_date),
                    "later_date": str(later_j.judgment_date),
                },
            )
            return None

        # Check existing evidence in DB
        existing_ev = (
            db.query(Evidence)
            .filter(
                Evidence.direction_id == direction.id,
                Evidence.source_judgment_id == later_j.id,
            )
            .first()
        )
        if existing_ev:
            self.log_step(
                "CHECK_EXISTING_EVIDENCE",
                "SKIPPED",
                0.001,
                {
                    "direction_id": direction.id,
                    "existing_evidence_id": existing_ev.id,
                    "verdict": existing_ev.verdict,
                },
            )
            return {
                "verdict": existing_ev.verdict,
                "evidence_strength": existing_ev.evidence_strength,
                "supporting_quote": existing_ev.supporting_quote,
                "reasoning": existing_ev.reasoning,
                "verified": existing_ev.verified,
                "model_used": existing_ev.model_used,
                "method": "existing_evidence",
            }

        model_name = settings.GEMINI_MODEL
        user_prompt = f"""ORIGINAL DIRECTION (Judgment ID {direction.judgment_id}):
- Responsible Party: {direction.responsible_party}
- Action: {direction.action}
- Deadline: {direction.deadline_phrase or 'None specified'}
- Original Quote: {direction.source_quote}

LATER FOLLOW-UP ORDER (Case: {later_j.case_number}, Date: {later_j.judgment_date}):
{later_j.text}
"""
        cache_key = build_cache_key(model_name, direction.id, later_j.id, user_prompt)

        # 1. Check LLM Cache
        cached = db.query(LLMCache).filter(LLMCache.cache_key == cache_key).first()
        if cached:
            try:
                data = json.loads(cached.response_json)
                data["method"] = "cached"
                data["model_used"] = model_name
                self.log_step(
                    "CLASSIFY_CACHED",
                    "COMPLETED",
                    0.001,
                    {"direction_id": direction.id, "verdict": data.get("verdict")},
                )
                return data
            except Exception:
                pass

        # 2. Call Gemini
        if not settings.GEMINI_API_KEY:
            self.log_step(
                "CLASSIFY",
                "SKIPPED_NO_API_KEY",
                0.001,
                {"direction_id": direction.id},
            )
            return None

        t_classify = time.perf_counter()
        try:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)

            full_content = f"{FOLLOW_UP_SYSTEM_PROMPT}\n\n{user_prompt}"
            response = client.models.generate_content(
                model=model_name,
                contents=full_content,
                config={"response_mime_type": "application/json"},
            )
            dur_classify = time.perf_counter() - t_classify
            data = json.loads(response.text.strip())

            self.log_step(
                "CLASSIFY_ATTEMPT_1",
                "COMPLETED",
                dur_classify,
                {"direction_id": direction.id, "verdict": data.get("verdict")},
            )

            # 3. Verifier on quote
            quote = data.get("supporting_quote", "")
            t_verify = time.perf_counter()
            is_verbatim = verify_follow_up_quote(quote, later_j.text or "")
            dur_verify = time.perf_counter() - t_verify

            if is_verbatim:
                data["verified"] = True
                self.log_step(
                    "VERIFY_QUOTE",
                    "PASSED_ATTEMPT_1",
                    dur_verify,
                    {"direction_id": direction.id, "quote_length": len(quote)},
                )
            else:
                # 4. Retry once with explicit feedback
                self.log_step(
                    "VERIFY_QUOTE",
                    "FAILED_ATTEMPT_1",
                    dur_verify,
                    {
                        "direction_id": direction.id,
                        "rejected_quote": (quote[:60] if quote else ""),
                    },
                )
                t_retry = time.perf_counter()
                retry_prompt = (
                    f"{full_content}\n\n"
                    f"ERROR: Your previous supporting_quote was not found verbatim in the later order text: '{quote}'.\n"
                    f"Extract ONLY an exact, verbatim substring from the LATER FOLLOW-UP ORDER text above."
                )
                response2 = client.models.generate_content(
                    model=model_name,
                    contents=retry_prompt,
                    config={"response_mime_type": "application/json"},
                )
                dur_retry = time.perf_counter() - t_retry
                data2 = json.loads(response2.text.strip())
                quote2 = data2.get("supporting_quote", "")

                if verify_follow_up_quote(quote2, later_j.text or ""):
                    data = data2
                    data["verified"] = True
                    self.log_step(
                        "RETRY_WITH_FEEDBACK",
                        "PASSED_AFTER_RETRY",
                        dur_retry,
                        {"direction_id": direction.id, "quote_length": len(quote2)},
                    )
                else:
                    self.log_step(
                        "RETRY_WITH_FEEDBACK",
                        "FAILED_AFTER_RETRY",
                        dur_retry,
                        {
                            "direction_id": direction.id,
                            "rejected_quote": (quote2[:60] if quote2 else ""),
                        },
                    )
                    data["verdict"] = "UNRELATED"
                    data["reasoning"] = (
                        f"Supporting quote verification failed after retry. Rejected quote: '{quote2[:60]}...'"
                    )
                    data["supporting_quote"] = ""
                    data["verified"] = False

            data["method"] = "gemini"
            data["model_used"] = model_name

            # Cache the response
            llm_entry = LLMCache(
                cache_key=cache_key,
                prompt_hash=hashlib.sha256(user_prompt.encode()).hexdigest(),
                model_name=model_name,
                response_json=json.dumps(data),
            )
            db.merge(llm_entry)
            db.commit()

            return data

        except Exception as exc:
            # Handle failures gracefully: status must remain unchanged, log reason
            dur_err = time.perf_counter() - t_classify
            err_msg = f"Gemini follow-up classification error for Dir {direction.id}: {str(exc)}"
            logger.error(err_msg)
            self.errors.append(err_msg)
            self.log_step(
                "CLASSIFY_GEMINI_ERROR",
                "FAILED_GRACEFUL",
                dur_err,
                {"direction_id": direction.id, "error": str(exc)},
            )
            return None

    def persist_and_update(
        self,
        candidate: Dict[str, Any],
        eval_result: Optional[Dict[str, Any]],
        db: Session,
    ) -> None:
        """Persist CaseLink and Evidence, recompute direction status deterministically, and log history."""
        t0 = time.perf_counter()
        direction: Direction = candidate["direction"]
        orig_j: Judgment = candidate["original_judgment"]
        later_j: Judgment = candidate["follow_up_judgment"]

        # 1. Persist CaseLink
        existing_link = (
            db.query(CaseLink)
            .filter(
                CaseLink.from_judgment_id == orig_j.id,
                CaseLink.to_judgment_id == later_j.id,
                CaseLink.link_signal == candidate["link_signal"],
            )
            .first()
        )
        if not existing_link:
            new_link = CaseLink(
                from_judgment_id=orig_j.id,
                to_judgment_id=later_j.id,
                primary_judgment_id=orig_j.id,
                linked_judgment_id=later_j.id,
                link_type=candidate["link_type"],
                link_signal=candidate["link_signal"],
                link_confidence=candidate["link_confidence"],
                note=candidate.get("time_reason") or f"Signal: {candidate['link_signal']}",
                citation_text=candidate.get("citation_text"),
                compliance_verdict=eval_result.get("verdict", "UNKNOWN") if eval_result else "UNKNOWN",
                compliance_quote=eval_result.get("supporting_quote") if eval_result else None,
                quote_verified=eval_result.get("verified", False) if eval_result else False,
                model_used=eval_result.get("model_used") if eval_result else None,
                method=eval_result.get("method", "deterministic") if eval_result else "deterministic",
            )
            db.add(new_link)
            db.commit()
        else:
            if eval_result:
                existing_link.compliance_verdict = eval_result.get("verdict", existing_link.compliance_verdict)
                existing_link.compliance_quote = eval_result.get("supporting_quote", existing_link.compliance_quote)
                existing_link.quote_verified = eval_result.get("verified", existing_link.quote_verified)
                db.commit()

        # 2. Persist Evidence if evaluation was produced
        ev_id: Optional[int] = None
        if eval_result:
            supporting_quote = eval_result.get("supporting_quote")
            strength = eval_result.get("evidence_strength") or determine_evidence_strength(
                supporting_quote, later_j.text or ""
            )

            # Determine case level scope: check other directions in orig_j
            dir_count_in_orig = db.query(Direction).filter(Direction.judgment_id == orig_j.id).count()
            scope = "CASE_LEVEL" if dir_count_in_orig > 1 else "DIRECTION_SPECIFIC"

            ev = (
                db.query(Evidence)
                .filter(
                    Evidence.direction_id == direction.id,
                    Evidence.source_judgment_id == later_j.id,
                )
                .first()
            )
            if not ev:
                ev = Evidence(
                    direction_id=direction.id,
                    supporting_quote=supporting_quote,
                    source_judgment_id=later_j.id,
                    source_case_number=later_j.case_number,
                    source_date=later_j.judgment_date,
                    verdict=eval_result.get("verdict", "UNRELATED"),
                    reasoning=eval_result.get("reasoning"),
                    verified=eval_result.get("verified", False),
                    evidence_strength=strength,
                    evidence_scope=scope,
                    directions_covered_count=dir_count_in_orig if scope == "CASE_LEVEL" else 1,
                    model_used=eval_result.get("model_used"),
                    method=eval_result.get("method", "gemini"),
                )
                db.add(ev)
                db.commit()
                db.refresh(ev)
            ev_id = ev.id

        # 3. Deterministic status evaluation per STATUS MODEL
        all_ev = db.query(Evidence).filter(Evidence.direction_id == direction.id).all()
        invalid_ids = {later_j.id} if not candidate["is_temporally_valid"] else set()
        has_contempt = candidate["link_type"] == "CONTEMPT_FILED" or candidate["link_signal"] == "contempt_citation"

        new_status, flags, reason, primary_ev_id = evaluate_direction_status(
            direction, all_ev, invalid_judgment_ids=invalid_ids, has_contempt_link=has_contempt
        )

        old_status = direction.compliance_status
        status_changed = (old_status != new_status)
        sub_reason_changed = (direction.sub_reason != reason)
        flags_changed = (
            direction.overdue_no_record != flags["overdue_no_record"]
            or direction.contempt_filed != flags["contempt_filed"]
            or direction.extension_sought != flags["extension_sought"]
            or direction.contempt_dismissed_for_default != flags["contempt_dismissed_for_default"]
        )

        self.directions_checked += 1

        if status_changed or flags_changed or sub_reason_changed or not direction.status_history:
            direction.compliance_status = new_status
            direction.sub_reason = reason
            direction.overdue_no_record = flags["overdue_no_record"]
            direction.contempt_filed = flags["contempt_filed"]
            direction.has_contempt_flag = flags["contempt_filed"]
            direction.extension_sought = flags["extension_sought"]
            direction.contempt_dismissed_for_default = flags["contempt_dismissed_for_default"]

            history = DirectionStatusHistory(
                direction_id=direction.id,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
                linked_judgment_id=later_j.id,
                evidence_id=primary_ev_id or ev_id,
                verified_quote=eval_result.get("supporting_quote") if eval_result else None,
                model_used=eval_result.get("model_used") if eval_result else "rule_based",
                method="followup_agent",
            )
            db.add(history)
            db.commit()
            self.directions_updated += 1

        dur = time.perf_counter() - t0
        self.log_step(
            "PERSIST_AND_UPDATE",
            "COMPLETED",
            dur,
            {
                "direction_id": direction.id,
                "old_status": old_status,
                "new_status": new_status,
                "status_changed": status_changed,
            },
        )

    def run(self, db: Session) -> AgentRun:
        """Execute autonomous follow-up analysis loop."""
        candidates = self.find_candidates(db)

        if not candidates:
            total_dur = time.perf_counter() - self.start_time
            agent_run = AgentRun(
                trigger=self.trigger,
                source_judgment_id=self.source_judgment.id if self.source_judgment else None,
                source_case_number=self.source_judgment.case_number if self.source_judgment else None,
                steps=json.dumps(self.step_logs),
                directions_checked_count=0,
                directions_updated_count=0,
                outcome="NO_CANDIDATES",
                errors=None,
                duration_seconds=round(total_dur, 3),
            )
            db.add(agent_run)
            db.commit()
            db.refresh(agent_run)
            return agent_run

        # Execute classification, verification, retry, and update for each candidate
        for cand in candidates:
            eval_res = self.classify_and_verify(cand, db)
            self.persist_and_update(cand, eval_res, db)

        # Recalculate global evidence metadata (strength/scope)
        update_evidence_metadata(db)

        total_dur = time.perf_counter() - self.start_time
        outcome = (
            "FAILED"
            if len(self.errors) > 0 and self.directions_checked == 0
            else ("PARTIAL_SUCCESS" if len(self.errors) > 0 else "SUCCESS")
        )

        agent_run = AgentRun(
            trigger=self.trigger,
            source_judgment_id=self.source_judgment.id if self.source_judgment else None,
            source_case_number=self.source_judgment.case_number if self.source_judgment else "ALL_JUDGMENTS",
            steps=json.dumps(self.step_logs),
            directions_checked_count=self.directions_checked,
            directions_updated_count=self.directions_updated,
            outcome=outcome,
            errors="; ".join(self.errors) if self.errors else None,
            duration_seconds=round(total_dur, 3),
        )
        db.add(agent_run)
        db.commit()
        db.refresh(agent_run)

        logger.info(
            f"Follow-up agent run {agent_run.id} finished ({outcome}): "
            f"checked {self.directions_checked}, updated {self.directions_updated} in {total_dur:.2f}s."
        )
        return agent_run


def run_followup_for_judgment(judgment_id: int, trigger: str = "INGEST_ANALYSIS") -> AgentRun:
    """Convenience helper to run follow-up agent on a single judgment."""
    with SessionLocal() as db:
        judgment = db.query(Judgment).filter(Judgment.id == judgment_id).first()
        if not judgment:
            raise ValueError(f"Judgment ID {judgment_id} not found.")
        agent = FollowUpAnalysisAgent(source_judgment=judgment, trigger=trigger)
        return agent.run(db)


def rescan_database_followup() -> AgentRun:
    """Convenience helper to run full database rescan with follow-up agent."""
    with SessionLocal() as db:
        agent = FollowUpAnalysisAgent(source_judgment=None, trigger="RESCAN")
        return agent.run(db)

