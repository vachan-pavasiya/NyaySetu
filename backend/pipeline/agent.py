"""Agentic extraction loop state machine.

Role: Orchestrates explicit state machine:
      SEGMENT -> EXTRACT -> VERIFY -> (if unverified) RETRY with feedback (max 2) -> PERSIST / LOW_CONFIDENCE.
Data flow: Judgment ID/text -> Segmenter -> Extractor -> Verifier -> Retry Loop -> SQLite directions.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.database import SessionLocal
from backend.app.models import Judgment, OperativeSegment, Direction
from backend.pipeline.models import ExtractedDirection, OperativeSegmentResult, VerificationResult
from backend.pipeline.segment import segment_operative_part
from backend.pipeline.extract_directions import extract_directions_with_chunking
from backend.pipeline.verify import verify_all_directions

logger = logging.getLogger("compliance_radar.agent")


class ComplianceExtractionAgent:
    """Explicit state graph for judgment operative direction extraction."""

    def __init__(self, judgment: Judgment, max_retries: int = 2):
        self.judgment = judgment
        self.max_retries = max_retries
        self.step_logs: List[Dict[str, Any]] = []

    def log_step(self, step_name: str, duration: float, details: Dict[str, Any]):
        """Record execution metrics and latency for each state transition."""
        entry = {
            "step": step_name,
            "duration_seconds": round(duration, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **details,
        }
        self.step_logs.append(entry)
        logger.info(f"[{self.judgment.case_number or self.judgment.id}] {step_name} took {duration:.3f}s: {details}")

    def run(self, db: Session) -> Dict[str, Any]:
        """Execute the agentic loop end-to-end."""
        total_start = time.perf_counter()

        # ------------------------------------------------------------------
        # STATE 1: SEGMENT
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        seg_res: OperativeSegmentResult = segment_operative_part(self.judgment.text)
        seg_duration = time.perf_counter() - t0

        self.log_step(
            "SEGMENT",
            seg_duration,
            {
                "has_directions": seg_res.has_directions,
                "method": seg_res.method,
                "segment_len": len(seg_res.segment_text) if seg_res.segment_text else 0,
            },
        )

        # Save OperativeSegment in DB (records all analyzed judgments)
        op_seg = OperativeSegment(
            judgment_id=self.judgment.id,
            segment_text=seg_res.segment_text or "[NO_OPERATIVE_DIRECTIONS]",
            start_char=seg_res.start_char or 0,
            end_char=seg_res.end_char or 0,
            segmentation_method=seg_res.method,
        )
        db.add(op_seg)
        db.commit()
        db.refresh(op_seg)

        if not seg_res.has_directions or not seg_res.segment_text:
            return {
                "judgment_id": self.judgment.id,
                "case_number": self.judgment.case_number,
                "has_directions": False,
                "total_directions": 0,
                "directions": [],
                "step_logs": self.step_logs,
                "total_latency_seconds": round(time.perf_counter() - total_start, 3),
            }

        # ------------------------------------------------------------------
        # STATE 2: EXTRACT & VERIFY LOOP (with feedback retry)
        # ------------------------------------------------------------------
        retry_count = 0
        feedback: Optional[str] = None
        verified_directions: List[ExtractedDirection] = []
        verified_first_try = 0
        verified_after_retry = 0
        passed: List[VerificationResult] = []
        total_extract_time = 0.0
        total_verify_time = 0.0

        target_text = self.judgment.text or ""

        while retry_count <= self.max_retries:
            # 2A: EXTRACT
            t_ext = time.perf_counter()
            ext_output = extract_directions_with_chunking(
                seg_res.segment_text,
                feedback=feedback,
            )
            ext_dur = time.perf_counter() - t_ext
            total_extract_time += ext_dur

            self.log_step(
                f"EXTRACT_ATTEMPT_{retry_count + 1}",
                ext_dur,
                {"extracted_count": len(ext_output.directions), "retry": retry_count},
            )

            if not ext_output.has_operative_directions or not ext_output.directions:
                break

            # 2B: VERIFY
            t_ver = time.perf_counter()
            verification_results: List[VerificationResult] = verify_all_directions(
                ext_output.directions,
                target_text,
            )
            ver_dur = time.perf_counter() - t_ver
            total_verify_time += ver_dur

            passed = [vr for vr in verification_results if vr.verified]
            failed = [vr for vr in verification_results if not vr.verified]

            self.log_step(
                f"VERIFY_ATTEMPT_{retry_count + 1}",
                ver_dur,
                {"passed": len(passed), "failed": len(failed)},
            )

            if retry_count == 0:
                verified_first_try = len(passed)

            # If all passed or max retries reached, exit loop
            if len(failed) == 0 or retry_count >= self.max_retries:
                if retry_count > 0:
                    verified_after_retry = max(0, len(passed) - verified_first_try)
                # Keep verified directions
                verified_directions = [vr.direction for vr in passed]
                # Include failed ones as low confidence
                for vr in failed:
                    unverified = vr.direction.model_copy(
                        update={"confidence": 0.3}
                    )
                    verified_directions.append(unverified)
                break

            # Prepare feedback for next retry
            retry_count += 1
            feedback_issues = []
            for vr in failed:
                feedback_issues.append(f"- Quote was rejected: '{vr.direction.source_quote}'. Must be a verbatim substring.")
            feedback = "The following quotes were NOT verbatim matches in the source text:\n" + "\n".join(feedback_issues)

        # ------------------------------------------------------------------
        # STATE 3: PERSIST
        # ------------------------------------------------------------------
        persisted_records: List[Direction] = []
        for d in verified_directions:
            # Check if quote was verified (confidence >= 0.5 and offsets resolved)
            is_verified = (d.quote_start is not None and d.quote_end is not None and d.confidence >= 0.5)
            record = Direction(
                judgment_id=self.judgment.id,
                operative_segment_id=op_seg.id,
                responsible_party=d.responsible_party,
                party_type=d.party_type.value,
                direction_type=d.direction_type.value,
                action=d.action,
                deadline_phrase=d.deadline_phrase,
                source_quote=d.source_quote,
                quote_start=d.quote_start,
                quote_end=d.quote_end,
                confidence=d.confidence,
                quote_verified=is_verified,
                extraction_method=getattr(d, "extraction_method", "gemini"),
            )
            db.add(record)
            persisted_records.append(record)

        db.commit()
        for r in persisted_records:
            db.refresh(r)

        total_latency = time.perf_counter() - total_start

        return {
            "judgment_id": self.judgment.id,
            "case_number": self.judgment.case_number,
            "has_directions": len(persisted_records) > 0,
            "total_directions": len(persisted_records),
            "directions": [
                {
                    "id": r.id,
                    "responsible_party": r.responsible_party,
                    "party_type": r.party_type,
                    "direction_type": r.direction_type,
                    "action": r.action,
                    "deadline_phrase": r.deadline_phrase,
                    "source_quote": r.source_quote,
                    "quote_start": r.quote_start,
                    "quote_end": r.quote_end,
                    "quote_verified": r.quote_verified,
                    "confidence": r.confidence,
                    "extraction_method": r.extraction_method,
                }
                for r in persisted_records
            ],
            "metrics": {
                "verified_first_try": verified_first_try,
                "verified_after_retry": verified_after_retry,
                "deadlines_verified": sum(1 for vr in passed if vr.deadline_verified),
                "quotes_extended": sum(1 for vr in passed if vr.quote_extended),
                "retries_used": retry_count,
                "segmentation_latency": round(seg_duration, 3),
                "extraction_latency": round(total_extract_time, 3),
                "verification_latency": round(total_verify_time, 3),
                "total_latency_seconds": round(total_latency, 3),
            },
            "step_logs": self.step_logs,
        }


def analyze_judgment(judgment_id: int, db: Optional[Session] = None) -> Dict[str, Any]:
    """Run agentic extraction pipeline on a specific judgment by ID."""
    if db is not None:
        judgment = db.query(Judgment).filter(Judgment.id == judgment_id).first()
        if not judgment:
            raise ValueError(f"Judgment ID {judgment_id} not found.")
        agent = ComplianceExtractionAgent(judgment=judgment)
        return agent.run(db)

    with SessionLocal() as local_db:
        judgment = local_db.query(Judgment).filter(Judgment.id == judgment_id).first()
        if not judgment:
            raise ValueError(f"Judgment ID {judgment_id} not found.")
        agent = ComplianceExtractionAgent(judgment=judgment)
        return agent.run(local_db)
