"""Pipeline package for data ingestion, text extraction, segmentation, and compliance analysis.

Role: Exposes ingestion, segmentation, LLM extraction, verification, and deadline resolution interfaces.
Data flow: AWS S3 / Raw Judgment -> Ingestion -> Segmentation -> Extraction -> Verification -> Deadline Resolution -> DB.
"""

from backend.pipeline.ingest import run_ingestion, main as ingest_main
from backend.pipeline.agent import ComplianceExtractionAgent, analyze_judgment
from backend.pipeline.segment import segment_operative_part, check_is_pure_dismissal
from backend.pipeline.verify import verify_direction_quote, verify_all_directions
from backend.pipeline.deadline import (
    SERVICE_LAG_DAYS,
    ParsedDeadline,
    resolve_deadline,
    resolve_and_update_direction,
    resolve_all_directions,
)
from backend.pipeline.models import (
    ExtractedDirection,
    PartyType,
    DirectionType,
    DirectionExtractionOutput,
    OperativeSegmentResult,
    VerificationResult,
)

__all__ = [
    "run_ingestion",
    "ingest_main",
    "ComplianceExtractionAgent",
    "analyze_judgment",
    "segment_operative_part",
    "check_is_pure_dismissal",
    "verify_direction_quote",
    "verify_all_directions",
    "SERVICE_LAG_DAYS",
    "ParsedDeadline",
    "resolve_deadline",
    "resolve_and_update_direction",
    "resolve_all_directions",
    "ExtractedDirection",
    "PartyType",
    "DirectionType",
    "DirectionExtractionOutput",
    "OperativeSegmentResult",
    "VerificationResult",
]
