"""Database ORM models module.

Role: Defines schema for judgments, ingestion jobs, operative segments, directions, case links, and LLM cache.
Data flow: Ingestion & agent pipeline -> ORM entities -> SQLite tables for ledger, calendar, and UI.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from backend.app.database import Base


def utcnow():
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


class Judgment(Base):
    """Judgment record ingested from public high court datasets.
    
    Fields required by Phase 1:
    id, court, year, case_number, cnr, judgment_date, petitioner, respondent,
    s3_key, text, text_quality, status, error, created_at.
    """

    __tablename__ = "judgments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    court = Column(String(128), index=True, nullable=False)
    year = Column(Integer, index=True, nullable=False)
    case_number = Column(String(256), index=True, nullable=True)
    cnr = Column(String(64), index=True, nullable=True)
    judgment_date = Column(Date, index=True, nullable=True)
    petitioner = Column(Text, nullable=True)
    respondent = Column(Text, nullable=True)
    s3_key = Column(String(512), index=True, nullable=True)
    text = Column(Text, nullable=True)
    text_quality = Column(Float, default=0.0)
    status = Column(String(32), default="INGESTED", index=True)  # INGESTED, FAILED_UNREADABLE, FAILED_DOWNLOAD
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    # Relationships for downstream phases
    segments = relationship("OperativeSegment", back_populates="judgment", cascade="all, delete-orphan")
    directions = relationship("Direction", back_populates="judgment", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_judgment_cnr", "cnr"),
        Index("idx_judgment_case_number", "case_number"),
        Index("idx_judgment_court_year", "court", "year"),
        Index("idx_judgment_s3_key", "s3_key"),
    )


class IngestJob(Base):
    """Tracks background ingestion jobs with live status and progress."""

    __tablename__ = "ingest_jobs"

    id = Column(String(36), primary_key=True, index=True)
    court = Column(String(128), nullable=False)
    year = Column(Integer, nullable=False)
    limit = Column(Integer, nullable=False)
    status = Column(String(32), default="QUEUED", index=True)  # QUEUED, RUNNING, COMPLETED, FAILED
    total = Column(Integer, default=0)
    processed = Column(Integer, default=0)
    succeeded = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    error_summary = Column(Text, nullable=True)
    avg_seconds_per_doc = Column(Float, default=0.0)
    started_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)


class OperativeSegment(Base):
    """Segment of the order containing the operative directions."""

    __tablename__ = "operative_segments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=False, index=True)
    segment_text = Column(Text, nullable=False)
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)
    segmentation_method = Column(String(64), default="heuristic")
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=utcnow)

    # Relationships
    judgment = relationship("Judgment", back_populates="segments")
    directions = relationship("Direction", back_populates="segment")


class Direction(Base):
    """Operative direction extracted from a judgment."""

    __tablename__ = "directions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=False, index=True)
    operative_segment_id = Column(Integer, ForeignKey("operative_segments.id"), nullable=True)

    # Extraction fields
    responsible_party = Column(String(512), nullable=False, index=True)
    party_type = Column(String(64), default="department")  # state, department, officer, private, other
    direction_type = Column(String(32), default="mandatory")  # mandatory, liberty, consequential
    action = Column(Text, nullable=False)
    deadline_phrase = Column(String(256), nullable=True)
    source_quote = Column(Text, nullable=False)
    quote_start = Column(Integer, nullable=True)
    quote_end = Column(Integer, nullable=True)
    confidence = Column(Float, default=1.0)
    quote_verified = Column(Boolean, default=False)
    rejection_reason = Column(Text, nullable=True)
    extraction_method = Column(String(32), default="gemini", index=True)  # gemini, fallback

    # Resolved Deadline Window (Deterministic math)
    anchor_type = Column(String(64), nullable=True)  # judgment_date, receipt, explicit_date, hearing, DEPENDENT_ON_PRIOR_EVENT, none
    offset_value = Column(Integer, nullable=True)
    offset_unit = Column(String(32), nullable=True)  # days, weeks, months, immediate, none
    deadline_window_start = Column(Date, nullable=True, index=True)
    deadline_window_end = Column(Date, nullable=True, index=True)
    is_estimated = Column(Boolean, default=False)
    explanation_text = Column(Text, nullable=True)
    deadline_status = Column(String(32), default="NO_DEADLINE", index=True)  # UPCOMING, IN_WINDOW, LAPSED, NO_DEADLINE, URGENT_UNSPECIFIED, DEPENDENT
    compliance_status = Column(String(32), default="UNVERIFIED", index=True)  # COMPLIED, PENDING, UNVERIFIED
    has_contempt_flag = Column(Boolean, default=False)
    contempt_filed = Column(Boolean, default=False)
    extension_sought = Column(Boolean, default=False)
    overdue_no_record = Column(Boolean, default=False)
    contempt_dismissed_for_default = Column(Boolean, default=False)

    created_at = Column(DateTime, default=utcnow)

    # Relationships
    judgment = relationship("Judgment", back_populates="directions")
    segment = relationship("OperativeSegment", back_populates="directions")
    evidence_list = relationship("Evidence", back_populates="direction", cascade="all, delete-orphan")
    status_history = relationship("DirectionStatusHistory", back_populates="direction", cascade="all, delete-orphan")


class CaseLink(Base):
    """Link between an original order and subsequent proceedings (e.g. contempt, compliance filings)."""

    __tablename__ = "case_links"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    from_judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=True, index=True)
    to_judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=True, index=True)
    primary_judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=True, index=True)
    linked_judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=True, index=True)
    link_type = Column(String(64), nullable=False)  # CONTEMPT_FILED, COMPLIANCE_REPORT, EXTENSION_SOUGHT, APPEAL, DISPOSED_AS_COMPLIED, OTHER
    link_signal = Column(String(64), nullable=True)  # contempt_citation, same_cnr, same_case_number, fuzzy_party
    link_confidence = Column(String(16), default="HIGH")  # HIGH, MEDIUM, LOW
    note = Column(Text, nullable=True)
    supporting_quote = Column(Text, nullable=True)
    quote_verified = Column(Boolean, default=False)
    compliance_verdict = Column(String(32), default="UNKNOWN")  # COMPLIANCE_SHOWN, NON_COMPLIANCE_ALLEGED, etc.
    compliance_quote = Column(Text, nullable=True)
    citation_text = Column(String(512), nullable=True)
    status_update = Column(String(32), nullable=True)
    evidence_quote = Column(Text, nullable=True)
    model_used = Column(String(64), nullable=True)
    method = Column(String(32), default="deterministic")
    created_at = Column(DateTime, default=utcnow)

    from_judgment = relationship("Judgment", foreign_keys=[from_judgment_id])
    to_judgment = relationship("Judgment", foreign_keys=[to_judgment_id])
    primary_judgment = relationship("Judgment", foreign_keys=[primary_judgment_id])
    linked_judgment = relationship("Judgment", foreign_keys=[linked_judgment_id])


class Evidence(Base):
    """Evidence supporting or modifying a direction's compliance status."""

    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    direction_id = Column(Integer, ForeignKey("directions.id"), nullable=False, index=True)
    supporting_quote = Column(Text, nullable=True)
    source_judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=True, index=True)
    source_case_number = Column(String(256), nullable=True)
    source_date = Column(Date, nullable=True)
    verdict = Column(String(64), nullable=False)  # COMPLIANCE_SHOWN, ONGOING_PROCESS, NON_COMPLIANCE_ALLEGED, NOTICE_ISSUED, EXTENSION_SOUGHT, DISMISSED_FOR_DEFAULT, DISPOSED_NO_FINDING, UNRELATED
    reasoning = Column(Text, nullable=True)
    verified = Column(Boolean, default=False)
    evidence_strength = Column(String(50), nullable=True)  # COURT_RECORDED vs PARTY_SUBMISSION
    evidence_scope = Column(String(50), nullable=True)  # CASE_LEVEL vs DIRECTION_SPECIFIC
    directions_covered_count = Column(Integer, nullable=True)  # Count of directions covered by this order/quote
    model_used = Column(String(64), nullable=True)
    method = Column(String(32), default="gemini")
    created_at = Column(DateTime, default=utcnow)

    direction = relationship("Direction", back_populates="evidence_list")
    source_judgment = relationship("Judgment", foreign_keys=[source_judgment_id])


class DirectionStatusHistory(Base):
    """Audit ledger tracking changes to direction compliance status."""

    __tablename__ = "direction_status_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    direction_id = Column(Integer, ForeignKey("directions.id"), nullable=False, index=True)
    old_status = Column(String(32), nullable=True)
    new_status = Column(String(32), nullable=False)  # COMPLIED, PENDING, UNVERIFIED
    reason = Column(Text, nullable=False)
    linked_judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=True)
    verified_quote = Column(Text, nullable=True)
    model_used = Column(String(64), nullable=True)
    method = Column(String(32), nullable=True)
    timestamp = Column(DateTime, default=utcnow)
    created_at = Column(DateTime, default=utcnow)

    direction = relationship("Direction", back_populates="status_history")
    linked_judgment = relationship("Judgment", foreign_keys=[linked_judgment_id])
    evidence = relationship("Evidence", foreign_keys=[evidence_id])


class LLMCache(Base):
    """Cache of LLM queries to prevent duplicate API spend and enable deterministic replay."""

    __tablename__ = "llm_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cache_key = Column(String(64), unique=True, index=True, nullable=False)  # sha256(prompt + text)
    prompt_hash = Column(String(64), index=True, nullable=False)
    model_name = Column(String(64), nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)
