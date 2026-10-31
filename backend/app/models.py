"""Database ORM models module.

Role: Defines schema for judgments, operative segments, directions, case links, and LLM cache.
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
    """Judgment record ingested from public high court datasets."""

    __tablename__ = "judgments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cnr = Column(String(64), index=True, nullable=True)
    court = Column(String(128), index=True, nullable=False)
    year = Column(Integer, index=True, nullable=False)
    case_number = Column(String(256), index=True, nullable=True)
    petitioner = Column(Text, nullable=True)
    respondent = Column(Text, nullable=True)
    judgment_date = Column(Date, index=True, nullable=True)
    bench = Column(String(512), nullable=True)
    pdf_s3_key = Column(String(512), nullable=True)
    local_pdf_path = Column(String(512), nullable=True)
    
    # Text Extraction & Quality
    text_status = Column(String(32), default="PENDING", index=True)  # PENDING, SUCCESS, FAILED_UNREADABLE
    quality_score = Column(Float, default=0.0)
    raw_text = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)

    # Relationships
    segments = relationship("OperativeSegment", back_populates="judgment", cascade="all, delete-orphan")
    directions = relationship("Direction", back_populates="judgment", cascade="all, delete-orphan")


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
    party_type = Column(String(64), default="GOVERNMENT_DEPARTMENT")  # GOV, PRIVATE, COURT_OFFICIAL, UNKNOWN
    action = Column(Text, nullable=False)
    deadline_phrase = Column(String(256), nullable=True)
    source_quote = Column(Text, nullable=False)
    quote_start_offset = Column(Integer, nullable=True)
    quote_end_offset = Column(Integer, nullable=True)
    confidence = Column(Float, default=0.0)
    quote_verified = Column(Boolean, default=False)

    # Resolved Deadline Window (Deterministic math)
    deadline_window_start = Column(Date, nullable=True, index=True)
    deadline_window_end = Column(Date, nullable=True, index=True)
    deadline_status = Column(String(32), default="UNVERIFIED", index=True)  # COMPLIED, PENDING, LAPSED_NO_RECORD, UNVERIFIED

    created_at = Column(DateTime, default=utcnow)

    # Relationships
    judgment = relationship("Judgment", back_populates="directions")
    segment = relationship("OperativeSegment", back_populates="directions")


class CaseLink(Base):
    """Link between an original order and subsequent proceedings (e.g. contempt, compliance filings)."""

    __tablename__ = "case_links"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    primary_judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=False, index=True)
    linked_judgment_id = Column(Integer, ForeignKey("judgments.id"), nullable=True, index=True)
    link_type = Column(String(64), nullable=False)  # SAME_CASE_LATER_ORDER, CONTEMPT_PETITION, CITATION
    citation_text = Column(String(512), nullable=True)
    status_update = Column(String(32), nullable=True)  # COMPLIED, NON_COMPLIANT, PENDING
    evidence_quote = Column(Text, nullable=True)
    quote_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


class LLMCache(Base):
    """Cache of LLM queries to prevent duplicate API spend and enable deterministic replay."""

    __tablename__ = "llm_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cache_key = Column(String(64), unique=True, index=True, nullable=False)  # sha256(prompt + text)
    prompt_hash = Column(String(64), index=True, nullable=False)
    model_name = Column(String(64), nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("idx_llm_cache_lookup", "cache_key"),
    )
