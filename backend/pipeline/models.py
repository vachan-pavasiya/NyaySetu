"""Pydantic data schemas for direction extraction, verification, and segmentation.

Role: Strongly-typed models for operative directions, party classifications,
      and verification results throughout the extraction pipeline.
Data flow: Operative text -> Gemini LLM JSON -> Pydantic Models -> Verifier -> SQLite.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class PartyType(str, Enum):
    """Classification of the party directed by the court."""
    state = "state"
    department = "department"
    officer = "officer"
    private = "private"
    other = "other"


class DirectionType(str, Enum):
    """Legal nature of the operative direction."""
    mandatory = "mandatory"        # e.g., "The respondent is directed to decide..."
    liberty = "liberty"            # e.g., "Petitioner is at liberty to submit a representation..."
    consequential = "consequential"# e.g., "Upon such decision, benefits shall be disbursed..."


class ExtractedDirection(BaseModel):
    """Structured operative direction extracted from a judgment order."""

    responsible_party: str = Field(description="Name or title of the directed party/authority")
    party_type: PartyType = Field(default=PartyType.department, description="Classification of responsible party")
    action: str = Field(description="Specific mandated action or instruction to be performed")
    deadline_phrase: Optional[str] = Field(default=None, description="Exact phrase specifying the timeframe/deadline, or null if none")
    source_quote: str = Field(description="Exact verbatim sentence/clause from judgment containing this direction")
    quote_start: Optional[int] = Field(default=None, description="Character start offset in the original judgment text")
    quote_end: Optional[int] = Field(default=None, description="Character end offset in the original judgment text")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model extraction confidence score")
    direction_type: DirectionType = Field(default=DirectionType.mandatory, description="Type of direction")
    extraction_method: str = Field(default="gemini", description="Method used to extract: gemini or fallback")

    @field_validator("party_type", mode="before")
    @classmethod
    def normalize_party_type(cls, val):
        if isinstance(val, str):
            v = val.strip().lower()
            if "state" in v or "government" in v:
                return PartyType.state
            if "dept" in v or "department" in v or "board" in v or "corporation" in v or "municipality" in v:
                return PartyType.department
            if "officer" in v or "magistrate" in v or "collector" in v or "commissioner" in v or "registrar" in v:
                return PartyType.officer
            if "private" in v or "individual" in v or "company" in v:
                return PartyType.private
            return PartyType.other
        return val

    @field_validator("direction_type", mode="before")
    @classmethod
    def normalize_direction_type(cls, val):
        if isinstance(val, str):
            v = val.strip().lower()
            if "liberty" in v:
                return DirectionType.liberty
            if "consequential" in v or "follow" in v:
                return DirectionType.consequential
            return DirectionType.mandatory
        return val


class DirectionExtractionOutput(BaseModel):
    """Schema returned by LLM during direction extraction."""
    has_operative_directions: bool = Field(description="Whether the judgment contains operative directions")
    directions: List[ExtractedDirection] = Field(default_factory=list, description="List of extracted operative directions")
    dismissal_reason: Optional[str] = Field(default=None, description="If order was dismissed/disposed without directions, explanation why")


class OperativeSegmentResult(BaseModel):
    """Result of operative text segmentation."""
    has_directions: bool
    segment_text: Optional[str] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    method: str = "heuristic"  # heuristic, llm, none


class VerificationResult(BaseModel):
    """Verification outcome for an extracted direction."""
    direction: ExtractedDirection
    verified: bool
    rejection_reason: Optional[str] = None
    normalized_matched: bool = False
    deadline_verified: bool = False
    quote_extended: bool = False
