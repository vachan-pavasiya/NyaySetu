"""Main FastAPI application entry point.

Role: Configures HTTP server, CORS middleware, lifespan events, health check,
      background ingestion jobs, and judgment query API.
Data flow: Inbound HTTP -> Router -> Database/Pipelines -> JSON response.
"""

import os
import csv
import io
import json
import math
import time
import uuid
import logging
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional, Union, Any, Dict, Tuple, Set

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query, Response, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text, desc, func
from sqlalchemy.orm import Session

from backend.app.config import get_settings, Settings
from backend.app.database import engine, Base, get_db, SessionLocal
import backend.app.models as models
from backend.app.models import (
    Judgment,
    IngestJob,
    Direction,
    OperativeSegment,
    CaseLink,
    DirectionStatusHistory,
    Evidence,
    AgentRun,
)
from backend.pipeline.ingest import run_ingestion
from backend.pipeline.agent import ComplianceExtractionAgent, analyze_judgment
from backend.pipeline.clean_department import clean_department_name
from backend.pipeline.linking import normalize_case_citation

logger = logging.getLogger("compliance_radar.api")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager: initialises database tables and runs auto-bootstrap if DB is empty."""
    Base.metadata.create_all(bind=engine)

    # Auto-run bootstrap if DB is completely empty on first deploy
    db = SessionLocal()
    try:
        if db.query(Judgment).count() == 0 and os.getenv("DISABLE_AUTO_BOOTSTRAP", "").lower() != "true":
            logger.info("Database is empty on initial startup. Triggering auto-bootstrap from real S3 Open Data...")
            from scripts.bootstrap import run_bootstrap
            run_bootstrap(exit_on_failure=False)
    except Exception as exc:
        logger.warning(f"Initial startup bootstrap check: {exc}")
    finally:
        db.close()

    yield


app = FastAPI(
    title="Court-Order Compliance Radar",
    description="Agentic tracking and verification of High Court compliance directions.",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS from configured ALLOWED_ORIGINS
_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------------
# In-memory Aggregate Caching (Short TTL) & Global Error Handler
# ----------------------------------------------------------------------------
_AGG_CACHE: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 20.0


def get_from_cache(key: str) -> Optional[Any]:
    """Retrieve value from in-memory cache if not expired."""
    if key in _AGG_CACHE:
        timestamp, value = _AGG_CACHE[key]
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return value
        del _AGG_CACHE[key]
    return None


def store_in_cache(key: str, value: Any) -> None:
    """Store value in cache with current timestamp."""
    _AGG_CACHE[key] = (time.time(), value)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global JSON error handler for unhandled exceptions."""
    logger.error(f"Global unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "path": request.url.path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# ============================================================================
# Schemas
# ============================================================================

class IngestRequest(BaseModel):
    court: str = Field(default="calcutta_appellate_side", description="Court name or alias")
    year: int = Field(default=2023, description="Judgment year")
    limit: int = Field(default=100, ge=1, le=1000, description="Max judgments to ingest")


class IngestJobResponse(BaseModel):
    job_id: str
    status: str
    court: str
    year: int
    limit: int
    total: int
    processed: int
    succeeded: int
    failed: int
    avg_seconds_per_doc: float
    error_summary: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None


class JudgmentListItem(BaseModel):
    id: int
    court: str
    year: int
    case_number: Optional[str] = None
    cnr: Optional[str] = None
    judgment_date: Optional[str] = None
    petitioner: Optional[str] = None
    respondent: Optional[str] = None
    s3_key: Optional[str] = None
    text_length: int = 0
    text_quality: float
    status: str
    error: Optional[str] = None
    created_at: str


class DirectionItem(BaseModel):
    id: int
    judgment_id: int
    responsible_party: str
    party_type: str
    direction_type: str
    action: str
    deadline_phrase: Optional[str] = None
    source_quote: str
    quote_start: Optional[int] = None
    quote_end: Optional[int] = None
    quote_verified: bool
    confidence: float
    deadline_status: str
    extraction_method: Optional[str] = "gemini"
    anchor_type: Optional[str] = None
    offset_value: Optional[int] = None
    offset_unit: Optional[str] = None
    deadline_window_start: Optional[str] = None
    deadline_window_end: Optional[str] = None
    is_estimated: bool = False
    explanation_text: Optional[str] = None
    created_at: str


class EvidenceItem(BaseModel):
    id: int
    source_case_number: Optional[str] = None
    source_judgment_id: Optional[int] = None
    source_date: Optional[str] = None
    verdict: str
    supporting_quote: Optional[str] = None
    reasoning: Optional[str] = None
    verified: bool = False
    evidence_strength: Optional[str] = None  # COURT_RECORDED vs PARTY_SUBMISSION
    evidence_scope: Optional[str] = None  # CASE_LEVEL vs DIRECTION_SPECIFIC
    directions_covered_count: Optional[int] = None
    model_used: Optional[str] = None
    method: Optional[str] = None
    created_at: str


class DirectionDetailResponse(BaseModel):
    id: int
    judgment_id: int
    case_number: Optional[str] = None
    judgment_date: Optional[str] = None
    responsible_party: str
    party_type: str
    direction_type: str
    action: str
    deadline_phrase: Optional[str] = None
    source_quote: str
    anchor_type: Optional[str] = None
    offset_value: Optional[int] = None
    offset_unit: Optional[str] = None
    deadline_window_start: Optional[str] = None
    deadline_window_end: Optional[str] = None
    deadline_status: str
    compliance_status: str
    status: str
    sub_reason: Optional[str] = None
    flags: dict
    explanation_text: Optional[str] = None
    evidence_strength: Optional[str] = None  # COURT_RECORDED vs PARTY_SUBMISSION
    evidence_scope: Optional[str] = None  # CASE_LEVEL vs DIRECTION_SPECIFIC
    directions_covered_count: Optional[int] = None
    evidence: List[EvidenceItem]
    created_at: str


class LedgerItem(BaseModel):
    id: int
    direction_id: int
    judgment_id: int
    case_number: Optional[str] = None
    court: Optional[str] = None
    judgment_date: Optional[str] = None
    responsible_party: str
    cleaned_department: str
    party_type: str
    direction_type: str
    action: str
    deadline_phrase: Optional[str] = None
    deadline_window_start: Optional[str] = None
    deadline_window_end: Optional[str] = None
    deadline_status: str
    explanation_text: Optional[str] = None
    compliance_status: str  # COMPLIED, PENDING, UNVERIFIED
    status: str             # alias for compliance_status
    sub_reason: Optional[str] = None
    flags: dict
    evidence_strength: Optional[str] = None
    evidence_scope: Optional[str] = None
    directions_covered_count: Optional[int] = None
    primary_quote: Optional[str] = None
    primary_verdict: Optional[str] = None
    primary_case: Optional[str] = None
    evidence_count: int = 0
    judgment_link: str


class LedgerResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    limit: int
    offset: int
    items: List[LedgerItem]


class CalendarDirectionItem(BaseModel):
    id: int
    direction_id: int
    judgment_id: int
    case_number: Optional[str] = None
    court: Optional[str] = None
    judgment_date: Optional[str] = None
    responsible_party: str
    cleaned_department: str
    action: str
    deadline_phrase: Optional[str] = None
    deadline_window_start: Optional[str] = None
    deadline_window_end: str
    deadline_status: str
    compliance_status: str
    sub_reason: Optional[str] = None
    flags: dict
    explanation_text: Optional[str] = None
    evidence_strength: Optional[str] = None
    evidence_scope: Optional[str] = None
    judgment_link: str


class CalendarResponse(BaseModel):
    month: str
    total_directions: int
    status_summary: Dict[str, int]
    directions: List[CalendarDirectionItem]


class DashboardFreshness(BaseModel):
    latest_judgment_date: Optional[str] = None
    total_judgments: int
    analysed_count: int


class DashboardLinkStats(BaseModel):
    total_links: int
    by_type: Dict[str, int]
    by_signal: Dict[str, int]
    by_confidence: Dict[str, int]


class DueDirectionItem(BaseModel):
    id: int
    direction_id: int
    case_number: Optional[str] = None
    judgment_id: int
    responsible_party: str
    cleaned_department: str
    action: str
    deadline_window_end: Optional[str] = None
    deadline_status: str
    compliance_status: str
    days_remaining: Optional[int] = None
    sub_reason: Optional[str] = None
    judgment_link: str


class DashboardDepartmentSummary(BaseModel):
    department: str
    total: int
    open_count: int
    complied: int
    pending: int
    unverified: int
    overdue: int


class AgentRunItem(BaseModel):
    id: int
    trigger: str
    source_judgment_id: Optional[int] = None
    source_case_number: Optional[str] = None
    steps: List[Dict[str, Any]]
    directions_checked_count: int
    directions_updated_count: int
    outcome: str
    errors: Optional[str] = None
    duration_seconds: float
    created_at: str
    message: str


class DashboardResponse(BaseModel):
    status_counts: Dict[str, int]
    overdue_no_record_count: int
    contempt_filed_count: int
    evidence_strength_split: Dict[str, int]
    deadline_bucket_counts: Dict[str, int]
    top_departments: List[DashboardDepartmentSummary]
    directions_due_next_30_days: List[DueDirectionItem]
    due_next_30_days_count: int
    dataset_freshness: DashboardFreshness
    link_stats: DashboardLinkStats
    recent_pipeline_runs: List[AgentRunItem]
    disclaimer: str = "Legal information, not legal advice."
    unverified_note: str = "UNVERIFIED means no public evidence found, not non-compliance."


class DepartmentSummary(BaseModel):
    department: str
    total: int
    complied: int
    pending: int
    unverified: int
    overdue: int


class OverallStatsResponse(BaseModel):
    total_judgments: int
    total_directions: int
    status_distribution: dict
    flags_distribution: dict
    evidence_strength_distribution: dict
    case_level_directions_count: int
    top_departments: List[DepartmentSummary]


class DirectionTimelineEvent(BaseModel):
    date: Optional[str] = None
    event_type: str
    title: str
    description: str
    case_number: Optional[str] = None
    judgment_id: Optional[int] = None
    verified_quote: Optional[str] = None
    confidence: Optional[Union[float, str]] = None


class DirectionTimelineResponse(BaseModel):
    direction_id: int
    judgment_id: int
    case_number: Optional[str] = None
    responsible_party: str
    action: str
    deadline_phrase: Optional[str] = None
    deadline_window_start: Optional[str] = None
    deadline_window_end: Optional[str] = None
    deadline_status: str
    compliance_status: str
    has_contempt_flag: bool
    events: List[DirectionTimelineEvent]


class CaseTimelineResponse(BaseModel):
    cnr: Optional[str] = None
    case_number: Optional[str] = None
    court: str
    judgment_date: Optional[str] = None
    petitioner: Optional[str] = None
    respondent: Optional[str] = None
    compliance_status: str
    has_contempt_flag: bool
    directions_count: int
    events: List[DirectionTimelineEvent]


class AnalyzeJudgmentResponse(BaseModel):
    judgment_id: int
    case_number: Optional[str] = None
    has_directions: bool
    total_directions: int
    directions: List[dict]
    metrics: Optional[dict] = Field(default_factory=dict)
    step_logs: List[dict]
    followup_run_id: Optional[int] = None
    followup_updated_directions: Optional[int] = None


class AgentRunsResponse(BaseModel):
    total: int
    runs: List[AgentRunItem]


class RescanResponse(BaseModel):
    run_id: int
    trigger: str
    outcome: str
    directions_checked: int
    directions_updated: int
    duration_seconds: float
    message: str


class BatchAnalyzeRequest(BaseModel):
    judgment_ids: Optional[List[int]] = None
    limit: int = Field(default=30, ge=1, le=100)


class BatchAnalyzeResponse(BaseModel):
    total_judgments: int
    judgments_with_directions: int
    total_directions: int
    verified_first_try_pct: float
    verified_after_retry_pct: float
    average_latency_seconds: float
    results: List[dict]


class JudgmentDetail(BaseModel):
    id: int
    court: str
    year: int
    case_number: Optional[str] = None
    cnr: Optional[str] = None
    judgment_date: Optional[str] = None
    petitioner: Optional[str] = None
    respondent: Optional[str] = None
    s3_key: Optional[str] = None
    text: Optional[str] = None
    text_quality: float
    status: str
    error: Optional[str] = None
    created_at: str


class JudgmentListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[JudgmentListItem]


# ============================================================================
# System Endpoints
# ============================================================================

@app.get("/", include_in_schema=False)
def root():
    return {
        "app": "NyaySetu: Court-Order Compliance Radar",
        "status": "running",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "health": "/health",
    }

@app.get("/health", tags=["System"])
def health_check(
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_settings),
) -> dict:
    """System health check verifying database and configuration connectivity."""
    db_status = "error"
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as exc:  # pylint: disable=broad-exception-caught
        db_status = f"unhealthy: {str(exc)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service_lag_days": cfg.SERVICE_LAG_DAYS,
        "s3_bucket": cfg.S3_BUCKET,
        "environment": cfg.ENVIRONMENT,
    }


# ============================================================================
# Ingestion Endpoints
# ============================================================================

def background_ingest_worker(job_id: str, court: str, year: int, limit: int):
    """Background task executing the ingestion pipeline."""
    try:
        run_ingestion(court=court, year=year, limit=limit, job_id=job_id)
    except Exception as exc:
        with SessionLocal() as db:
            job = db.query(IngestJob).filter(IngestJob.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.error_summary = str(exc)
                job.completed_at = datetime.now(timezone.utc)
                db.commit()


@app.post("/ingest", response_model=IngestJobResponse, status_code=202, tags=["Ingestion"])
def trigger_ingest(
    req: IngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger asynchronous judgment ingestion from S3 as a background job."""
    job_id = str(uuid.uuid4())
    job = IngestJob(
        id=job_id,
        court=req.court,
        year=req.year,
        limit=req.limit,
        status="QUEUED",
        total=req.limit,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        background_ingest_worker,
        job_id=job_id,
        court=req.court,
        year=req.year,
        limit=req.limit,
    )

    return IngestJobResponse(
        job_id=job.id,
        status=job.status,
        court=job.court,
        year=job.year,
        limit=job.limit,
        total=job.total,
        processed=job.processed,
        succeeded=job.succeeded,
        failed=job.failed,
        avg_seconds_per_doc=job.avg_seconds_per_doc,
        error_summary=job.error_summary,
        started_at=job.started_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@app.get("/ingest/jobs/{job_id}", response_model=IngestJobResponse, tags=["Ingestion"])
def get_ingest_job_status(job_id: str, db: Session = Depends(get_db)):
    """Retrieve live progress and status of an ingestion background job."""
    job = db.query(IngestJob).filter(IngestJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found.")

    return IngestJobResponse(
        job_id=job.id,
        status=job.status,
        court=job.court,
        year=job.year,
        limit=job.limit,
        total=job.total,
        processed=job.processed,
        succeeded=job.succeeded,
        failed=job.failed,
        avg_seconds_per_doc=job.avg_seconds_per_doc,
        error_summary=job.error_summary,
        started_at=job.started_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


# ============================================================================
# Judgment Query Endpoints
# ============================================================================

@app.get("/judgments", response_model=JudgmentListResponse, tags=["Judgments"])
def list_judgments(
    court: Optional[str] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    case_number: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve paginated list of judgments with optional filters."""
    query = db.query(Judgment)

    if court:
        query = query.filter(Judgment.court.ilike(f"%{court}%"))
    if year:
        query = query.filter(Judgment.year == year)
    if status:
        query = query.filter(Judgment.status == status)
    if case_number:
        query = query.filter(Judgment.case_number.ilike(f"%{case_number}%"))

    total = query.count()
    records = query.order_by(desc(Judgment.id)).offset(offset).limit(limit).all()

    items = [
        JudgmentListItem(
            id=r.id,
            court=r.court,
            year=r.year,
            case_number=r.case_number,
            cnr=r.cnr,
            judgment_date=r.judgment_date.isoformat() if r.judgment_date else None,
            petitioner=r.petitioner,
            respondent=r.respondent,
            s3_key=r.s3_key,
            text_length=len(r.text) if r.text else 0,
            text_quality=r.text_quality,
            status=r.status,
            error=r.error,
            created_at=r.created_at.isoformat(),
        )
        for r in records
    ]

    return JudgmentListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@app.get("/judgments/{judgment_id}", response_model=JudgmentDetail, tags=["Judgments"])
def get_judgment_detail(judgment_id: int, db: Session = Depends(get_db)):
    """Retrieve full judgment details including extracted text and quality score."""
    record = db.query(Judgment).filter(Judgment.id == judgment_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Judgment ID {judgment_id} not found.")

    return JudgmentDetail(
        id=record.id,
        court=record.court,
        year=record.year,
        case_number=record.case_number,
        cnr=record.cnr,
        judgment_date=record.judgment_date.isoformat() if record.judgment_date else None,
        petitioner=record.petitioner,
        respondent=record.respondent,
        s3_key=record.s3_key,
        text=record.text,
        text_quality=record.text_quality,
        status=record.status,
        error=record.error,
        created_at=record.created_at.isoformat(),
    )


@app.post("/judgments/{judgment_id}/analyze", response_model=AnalyzeJudgmentResponse, tags=["Analysis"])
def analyze_single_judgment(judgment_id: int, db: Session = Depends(get_db)):
    """Run agentic segmentation, direction extraction, and verbatim verification on a judgment,
    then automatically trigger autonomous follow-up analysis to link and update directions."""
    try:
        result = analyze_judgment(judgment_id, db=db)

        # Autonomous follow-up analysis: automatically link, classify, verify, and update status
        try:
            from backend.pipeline.followup_agent import FollowUpAnalysisAgent
            judgment = db.query(Judgment).filter(Judgment.id == judgment_id).first()
            if judgment:
                followup_agent = FollowUpAnalysisAgent(source_judgment=judgment, trigger="INGEST_ANALYSIS")
                agent_run = followup_agent.run(db=db)
                result["followup_run_id"] = agent_run.id
                result["followup_updated_directions"] = agent_run.directions_updated_count
        except Exception as f_err:
            logger.error(f"Follow-up agent auto-run failed for judgment {judgment_id}: {f_err}")

        return result
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis pipeline error: {str(exc)}")


@app.post("/analyze/batch", response_model=BatchAnalyzeResponse, tags=["Analysis"])
def analyze_batch(req: BatchAnalyzeRequest, db: Session = Depends(get_db)):
    """Run agentic extraction on a batch of ingested judgments."""
    if req.judgment_ids:
        records = db.query(Judgment).filter(Judgment.id.in_(req.judgment_ids)).all()
    else:
        # Select judgments that haven't been analyzed yet, prioritizing INGESTED ones
        records = (
            db.query(Judgment)
            .filter(Judgment.status == "INGESTED")
            .order_by(Judgment.id.asc())
            .limit(req.limit)
            .all()
        )

    if not records:
        return BatchAnalyzeResponse(
            total_judgments=0,
            judgments_with_directions=0,
            total_directions=0,
            verified_first_try_pct=0.0,
            verified_after_retry_pct=0.0,
            average_latency_seconds=0.0,
            results=[],
        )

    results = []
    total_directions = 0
    total_verified_first = 0
    total_verified_retry = 0
    judgments_with_dirs = 0
    latencies = []

    for r in records:
        try:
            res = analyze_judgment(r.id, db=db)
            results.append(res)
            if res.get("has_directions"):
                judgments_with_dirs += 1
            dirs_count = res.get("total_directions", 0)
            total_directions += dirs_count
            m = res.get("metrics", {})
            total_verified_first += m.get("verified_first_try", 0)
            total_verified_retry += m.get("verified_after_retry", 0)
            latencies.append(m.get("total_latency_seconds", 0.0))
        except Exception as exc:
            logger.error(f"Error analyzing judgment {r.id}: {exc}")

    avg_lat = round(sum(latencies) / max(len(latencies), 1), 3)
    first_try_pct = round((total_verified_first / max(total_directions, 1)) * 100, 1)
    after_retry_pct = round(((total_verified_first + total_verified_retry) / max(total_directions, 1)) * 100, 1)

    return BatchAnalyzeResponse(
        total_judgments=len(records),
        judgments_with_directions=judgments_with_dirs,
        total_directions=total_directions,
        verified_first_try_pct=first_try_pct,
        verified_after_retry_pct=after_retry_pct,
        average_latency_seconds=avg_lat,
        results=results,
    )


@app.get("/judgments/{judgment_id}/directions", response_model=List[DirectionItem], tags=["Judgments"])
def get_judgment_directions(judgment_id: int, db: Session = Depends(get_db)):
    """Retrieve all verified operative directions extracted for a judgment."""
    records = db.query(Direction).filter(Direction.judgment_id == judgment_id).all()
    return [
        DirectionItem(
            id=r.id,
            judgment_id=r.judgment_id,
            responsible_party=r.responsible_party,
            party_type=r.party_type,
            direction_type=r.direction_type or "mandatory",
            action=r.action,
            deadline_phrase=r.deadline_phrase,
            source_quote=r.source_quote,
            quote_start=r.quote_start,
            quote_end=r.quote_end,
            quote_verified=r.quote_verified,
            confidence=r.confidence,
            deadline_status=r.deadline_status or "NO_DEADLINE",
            extraction_method=r.extraction_method or "gemini",
            anchor_type=r.anchor_type,
            offset_value=r.offset_value,
            offset_unit=r.offset_unit,
            deadline_window_start=r.deadline_window_start.isoformat() if r.deadline_window_start else None,
            deadline_window_end=r.deadline_window_end.isoformat() if r.deadline_window_end else None,
            is_estimated=bool(r.is_estimated),
            explanation_text=r.explanation_text,
            created_at=r.created_at.isoformat(),
        )
        for r in records
    ]


@app.get("/directions/{direction_id}", response_model=DirectionDetailResponse, tags=["Directions"])
def get_direction_detail(direction_id: int, db: Session = Depends(get_db)):
    """Retrieve detailed direction record with status, flags, and supporting evidence list."""
    d = db.query(Direction).filter(Direction.id == direction_id).first()
    if not d:
        raise HTTPException(status_code=404, detail=f"Direction ID {direction_id} not found")

    j = d.judgment
    ev_items = [
        EvidenceItem(
            id=e.id,
            source_case_number=e.source_case_number,
            source_judgment_id=e.source_judgment_id,
            source_date=e.source_date.isoformat() if e.source_date else None,
            verdict=e.verdict,
            supporting_quote=e.supporting_quote,
            reasoning=e.reasoning,
            verified=bool(e.verified),
            evidence_strength=e.evidence_strength,
            evidence_scope=e.evidence_scope,
            directions_covered_count=e.directions_covered_count,
            model_used=e.model_used,
            method=e.method,
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in d.evidence_list
    ]

    primary_ev = d.evidence_list[0] if d.evidence_list else None

    return DirectionDetailResponse(
        id=d.id,
        judgment_id=d.judgment_id,
        case_number=j.case_number if j else None,
        judgment_date=j.judgment_date.isoformat() if j and j.judgment_date else None,
        responsible_party=d.responsible_party,
        party_type=d.party_type,
        direction_type=d.direction_type or "mandatory",
        action=d.action,
        deadline_phrase=d.deadline_phrase,
        source_quote=d.source_quote,
        anchor_type=d.anchor_type,
        offset_value=d.offset_value,
        offset_unit=d.offset_unit,
        deadline_window_start=d.deadline_window_start.isoformat() if d.deadline_window_start else None,
        deadline_window_end=d.deadline_window_end.isoformat() if d.deadline_window_end else None,
        deadline_status=d.deadline_status or "NO_DEADLINE",
        compliance_status=d.compliance_status or "UNVERIFIED",
        status=d.compliance_status or "UNVERIFIED",
        sub_reason=d.sub_reason,
        flags={
            "contempt_filed": bool(d.contempt_filed or d.has_contempt_flag),
            "extension_sought": bool(d.extension_sought),
            "overdue_no_record": bool(d.overdue_no_record),
            "contempt_dismissed_for_default": bool(d.contempt_dismissed_for_default),
        },
        explanation_text=d.explanation_text,
        evidence_strength=primary_ev.evidence_strength if primary_ev else None,
        evidence_scope=primary_ev.evidence_scope if primary_ev else None,
        directions_covered_count=primary_ev.directions_covered_count if primary_ev else None,
        evidence=ev_items,
        created_at=d.created_at.isoformat() if d.created_at else "",
    )


@app.get("/directions/{direction_id}/timeline", response_model=DirectionTimelineResponse, tags=["Timeline"])
def get_direction_timeline(direction_id: int, db: Session = Depends(get_db)):
    """Retrieve comprehensive compliance event timeline for a specific direction."""
    d = db.query(Direction).filter(Direction.id == direction_id).first()
    if not d:
        raise HTTPException(status_code=404, detail=f"Direction ID {direction_id} not found")

    j = d.judgment
    events: List[DirectionTimelineEvent] = []

    # 1. Pronouncement event
    if j and j.judgment_date:
        events.append(
            DirectionTimelineEvent(
                date=j.judgment_date.isoformat(),
                event_type="PRONOUNCEMENT",
                title="Direction Pronounced",
                description=f"High Court pronounced direction in {j.case_number or 'order'}.",
                case_number=j.case_number,
                judgment_id=j.id,
                verified_quote=d.source_quote,
                confidence=d.confidence,
            )
        )

    # 2. Window start
    if d.deadline_window_start:
        events.append(
            DirectionTimelineEvent(
                date=d.deadline_window_start.isoformat(),
                event_type="DEADLINE_WINDOW_START",
                title="Estimated Compliance Window Opens",
                description=d.explanation_text or "Compliance window opened.",
                case_number=j.case_number if j else None,
                judgment_id=d.judgment_id,
            )
        )

    # 3. Window end
    if d.deadline_window_end:
        events.append(
            DirectionTimelineEvent(
                date=d.deadline_window_end.isoformat(),
                event_type="DEADLINE_WINDOW_END",
                title="Estimated Compliance Window Deadline",
                description=f"Prescribed period concluded ({d.deadline_phrase or ''}).",
                case_number=j.case_number if j else None,
                judgment_id=d.judgment_id,
            )
        )

    # 4. Status history audits
    history_entries = (
        db.query(DirectionStatusHistory)
        .filter(DirectionStatusHistory.direction_id == direction_id)
        .order_by(DirectionStatusHistory.id.asc())
        .all()
    )
    for h in history_entries:
        events.append(
            DirectionTimelineEvent(
                date=h.created_at.date().isoformat() if h.created_at else None,
                event_type="STATUS_CHANGE",
                title=f"Compliance Ledger: {h.new_status}",
                description=h.reason,
                judgment_id=h.linked_judgment_id,
                verified_quote=h.verified_quote,
            )
        )

    # 5. Linked later orders
    links = (
        db.query(CaseLink)
        .filter(CaseLink.primary_judgment_id == d.judgment_id)
        .all()
    )
    for cl in links:
        linked_j = cl.linked_judgment
        events.append(
            DirectionTimelineEvent(
                date=linked_j.judgment_date.isoformat() if linked_j and linked_j.judgment_date else None,
                event_type=cl.link_type,
                title=f"Later Proceeding: {cl.link_type.replace('_', ' ')}",
                description=f"Linked order in {linked_j.case_number if linked_j else 'later case'}. Verdict: {cl.compliance_verdict}.",
                case_number=linked_j.case_number if linked_j else None,
                judgment_id=cl.linked_judgment_id,
                verified_quote=cl.compliance_quote or cl.supporting_quote,
                confidence=cl.link_confidence,
            )
        )

    # Sort events chronologically (None dates go to end)
    events.sort(key=lambda e: e.date or "9999-99-99")

    return DirectionTimelineResponse(
        direction_id=d.id,
        judgment_id=d.judgment_id,
        case_number=j.case_number if j else None,
        responsible_party=d.responsible_party,
        action=d.action,
        deadline_phrase=d.deadline_phrase,
        deadline_window_start=d.deadline_window_start.isoformat() if d.deadline_window_start else None,
        deadline_window_end=d.deadline_window_end.isoformat() if d.deadline_window_end else None,
        deadline_status=d.deadline_status or "NO_DEADLINE",
        compliance_status=d.compliance_status or "UNVERIFIED",
        has_contempt_flag=bool(d.has_contempt_flag),
        events=events,
    )


@app.get("/cases", tags=["Timeline"])
def list_available_timeline_cases(db: Session = Depends(get_db)):
    """List available cases that exist in the database for the timeline dropdown."""
    # Find cases that have directions or are referenced in case links
    judgments = (
        db.query(Judgment.case_number, Judgment.cnr, Judgment.petitioner, Judgment.respondent)
        .filter(Judgment.case_number.isnot(None), Judgment.status == "INGESTED")
        .order_by(Judgment.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "case_number": j.case_number,
            "cnr": j.cnr,
            "title": f"{j.case_number}: {j.petitioner or ''} Vs {j.respondent or ''}".strip(),
        }
        for j in judgments
    ]


@app.get("/cases/{cnr:path}/timeline", response_model=CaseTimelineResponse, tags=["Timeline"])
def get_case_timeline(cnr: str, db: Session = Depends(get_db)):
    """Retrieve unified case timeline by CNR or Case Number."""
    norm_cnr = normalize_case_citation(cnr)
    j = (
        db.query(Judgment)
        .filter((Judgment.cnr == cnr) | (Judgment.case_number == cnr) | (Judgment.case_number == norm_cnr))
        .first()
    )
    if not j:
        j = db.query(Judgment).filter(
            (Judgment.case_number.ilike(cnr)) | (Judgment.case_number.ilike(norm_cnr))
        ).first()

    if not j:
        raise HTTPException(
            status_code=404,
            detail=f"Case '{cnr}' has not been ingested yet. Please trigger ingestion or select an available case."
        )

    events: List[DirectionTimelineEvent] = []

    # 1. Original Pronouncement
    if j.judgment_date:
        events.append(
            DirectionTimelineEvent(
                date=j.judgment_date.isoformat(),
                event_type="PRONOUNCEMENT",
                title=f"Judgment Pronounced ({j.court})",
                description=f"Final order passed in {j.case_number or 'case'}.",
                case_number=j.case_number,
                judgment_id=j.id,
            )
        )

    # 2. Directions
    has_contempt = False
    overall_compliance = "UNVERIFIED"

    for d in j.directions:
        if d.has_contempt_flag:
            has_contempt = True
        if d.compliance_status == "COMPLIED":
            overall_compliance = "COMPLIED"
        elif d.compliance_status == "LAPSED_NO_RECORD" and overall_compliance != "COMPLIED":
            overall_compliance = "LAPSED_NO_RECORD"

        if d.deadline_window_end:
            events.append(
                DirectionTimelineEvent(
                    date=d.deadline_window_end.isoformat(),
                    event_type="DEADLINE_WINDOW_END",
                    title=f"Deadline: {d.responsible_party[:40]}",
                    description=f"Action: {d.action[:100]}... ({d.explanation_text or ''})",
                    case_number=j.case_number,
                    judgment_id=j.id,
                    verified_quote=d.source_quote,
                )
            )

    # 3. Linked Proceedings
    links = (
        db.query(CaseLink)
        .filter((CaseLink.primary_judgment_id == j.id) | (CaseLink.linked_judgment_id == j.id))
        .all()
    )
    for cl in links:
        other_j = cl.linked_judgment if cl.primary_judgment_id == j.id else cl.primary_judgment
        if cl.link_type in ("CONTEMPT_FILED", "COMPLIANCE_REPORT"):
            has_contempt = True
        if cl.compliance_verdict == "COMPLIED":
            overall_compliance = "COMPLIED"

        events.append(
            DirectionTimelineEvent(
                date=other_j.judgment_date.isoformat() if other_j and other_j.judgment_date else None,
                event_type=cl.link_type,
                title=f"Proceedings Linked: {cl.link_type.replace('_', ' ')}",
                description=f"Related to {other_j.case_number if other_j else 'case'}. Verdict: {cl.compliance_verdict}.",
                case_number=other_j.case_number if other_j else None,
                judgment_id=other_j.id if other_j else None,
                verified_quote=cl.compliance_quote or cl.supporting_quote,
                confidence=cl.link_confidence,
            )
        )

    events.sort(key=lambda e: e.date or "9999-99-99")

    return CaseTimelineResponse(
        cnr=j.cnr,
        case_number=j.case_number,
        court=j.court,
        judgment_date=j.judgment_date.isoformat() if j.judgment_date else None,
        petitioner=j.petitioner,
        respondent=j.respondent,
        compliance_status=overall_compliance,
        has_contempt_flag=has_contempt,
        directions_count=len(j.directions),
        events=events,
    )


@app.post("/link/run", tags=["Linking"])
def trigger_linking_run(background_tasks: BackgroundTasks):
    """Trigger background execution of follow-up order linking and status engine over DB."""
    def run_job():
        with SessionLocal() as db:
            from backend.pipeline.linking import run_full_linking_and_status_pipeline
            run_full_linking_and_status_pipeline(db)

    background_tasks.add_task(run_job)
    return {
        "status": "QUEUED",
        "message": "Follow-up order linking and status engine started in background.",
    }


@app.get("/stats/links", tags=["Linking"])
def get_link_stats(db: Session = Depends(get_db)):
    """Retrieve statistical summary of discovered links, verdicts, and status breakdown."""
    links = db.query(CaseLink).all()
    evs = db.query(Evidence).all()
    dirs = db.query(Direction).all()

    by_type: dict = {}
    by_signal: dict = {}
    by_confidence: dict = {}
    temporal_downgrades: list = []

    for l in links:
        by_type[l.link_type] = by_type.get(l.link_type, 0) + 1
        sig = l.link_signal or "unknown"
        by_signal[sig] = by_signal.get(sig, 0) + 1
        conf = l.link_confidence or "MEDIUM"
        by_confidence[conf] = by_confidence.get(conf, 0) + 1
        if conf == "LOW" or "Temporal conflict" in (l.note or ""):
            temporal_downgrades.append({
                "link_id": l.id,
                "from_judgment_id": l.from_judgment_id,
                "to_judgment_id": l.to_judgment_id,
                "note": l.note,
            })

    verdicts: dict = {}
    for e in evs:
        verdicts[e.verdict] = verdicts.get(e.verdict, 0) + 1

    status_dist = {"COMPLIED": 0, "PENDING": 0, "UNVERIFIED": 0}
    overdue_count = 0
    flags_summary = {
        "contempt_filed": 0,
        "extension_sought": 0,
        "overdue_no_record": 0,
        "contempt_dismissed_for_default": 0,
    }

    for d in dirs:
        st = d.compliance_status or "UNVERIFIED"
        status_dist[st] = status_dist.get(st, 0) + 1
        if d.overdue_no_record:
            overdue_count += 1
            flags_summary["overdue_no_record"] += 1
        if d.contempt_filed or d.has_contempt_flag:
            flags_summary["contempt_filed"] += 1
        if d.extension_sought:
            flags_summary["extension_sought"] += 1
        if d.contempt_dismissed_for_default:
            flags_summary["contempt_dismissed_for_default"] += 1

    return {
        "total_links": len(links),
        "by_type": by_type,
        "by_signal": by_signal,
        "by_confidence": by_confidence,
        "temporal_downgrades_count": len(temporal_downgrades),
        "temporal_downgrades": temporal_downgrades,
        "verdict_distribution": verdicts,
        "status_distribution": status_dist,
        "overdue_no_record_count": overdue_count,
        "flags_summary": flags_summary,
        "total_directions": len(dirs),
    }


# ============================================================================
# Dashboard & Aggregations Endpoints
# ============================================================================

@app.get("/dashboard", response_model=DashboardResponse, tags=["Dashboard"])
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Retrieve comprehensive compliance radar dashboard telemetry with short TTL caching."""
    cache_key = "dashboard_summary"
    cached = get_from_cache(cache_key)
    if cached:
        return cached

    # 1. Directions and status counts
    directions = db.query(Direction).join(Judgment, Direction.judgment_id == Judgment.id).all()
    total_judgments = db.query(Judgment).count()
    analysed_count = db.query(Judgment).filter(Judgment.status == "INGESTED").count()
    max_j_date = db.query(func.max(Judgment.judgment_date)).scalar()

    status_counts = {"COMPLIED": 0, "PENDING": 0, "UNVERIFIED": 0}
    bucket_counts: Dict[str, int] = {}
    overdue_count = 0
    contempt_count = 0
    dept_map: Dict[str, Dict[str, int]] = {}

    today = date.today()
    due_items = []

    for d in directions:
        st = d.compliance_status or "UNVERIFIED"
        status_counts[st] = status_counts.get(st, 0) + 1

        b = d.deadline_status or "NO_DEADLINE"
        bucket_counts[b] = bucket_counts.get(b, 0) + 1

        if d.overdue_no_record:
            overdue_count += 1
        if d.contempt_filed or d.has_contempt_flag:
            contempt_count += 1

        # Cleaned department aggregation
        c_dept = clean_department_name(d.responsible_party)
        if c_dept not in dept_map:
            dept_map[c_dept] = {"total": 0, "complied": 0, "pending": 0, "unverified": 0, "overdue": 0}
        dept_map[c_dept]["total"] += 1
        if st == "COMPLIED":
            dept_map[c_dept]["complied"] += 1
        elif st == "PENDING":
            dept_map[c_dept]["pending"] += 1
        else:
            dept_map[c_dept]["unverified"] += 1
        if d.overdue_no_record:
            dept_map[c_dept]["overdue"] += 1

        # Check due next 30 days or active upcoming/in-window deadlines
        if d.deadline_window_end:
            days_rem = (d.deadline_window_end - today).days
            if (0 <= days_rem <= 30) or d.deadline_status in ("UPCOMING", "IN_WINDOW"):
                j = d.judgment
                due_items.append(
                    DueDirectionItem(
                        id=d.id,
                        direction_id=d.id,
                        case_number=j.case_number if j else None,
                        judgment_id=d.judgment_id,
                        responsible_party=d.responsible_party,
                        cleaned_department=c_dept,
                        action=d.action,
                        deadline_window_end=d.deadline_window_end.isoformat(),
                        deadline_status=d.deadline_status or "NO_DEADLINE",
                        compliance_status=st,
                        days_remaining=days_rem,
                        sub_reason=d.sub_reason,
                        judgment_link=f"/judgments/{d.judgment_id}",
                    )
                )

    # Top 10 departments by open directions (pending + unverified)
    top_depts = []
    for dept_name, m in dept_map.items():
        open_cnt = m["pending"] + m["unverified"]
        top_depts.append(
            DashboardDepartmentSummary(
                department=dept_name,
                total=m["total"],
                open_count=open_cnt,
                complied=m["complied"],
                pending=m["pending"],
                unverified=m["unverified"],
                overdue=m["overdue"],
            )
        )
    top_depts.sort(key=lambda x: (x.open_count, x.total), reverse=True)
    top_10_depts = top_depts[:10]

    # 2. Evidence strength split
    evidences = db.query(Evidence).all()
    strength_split = {"COURT_RECORDED": 0, "PARTY_SUBMISSION": 0}
    for ev in evidences:
        if ev.evidence_strength == "COURT_RECORDED":
            strength_split["COURT_RECORDED"] += 1
        elif ev.evidence_strength == "PARTY_SUBMISSION":
            strength_split["PARTY_SUBMISSION"] += 1

    # 3. Link stats
    links = db.query(CaseLink).all()
    by_type: Dict[str, int] = {}
    by_signal: Dict[str, int] = {}
    by_conf: Dict[str, int] = {}
    for lk in links:
        by_type[lk.link_type] = by_type.get(lk.link_type, 0) + 1
        sig = lk.link_signal or "unknown"
        by_signal[sig] = by_signal.get(sig, 0) + 1
        conf = lk.link_confidence or "MEDIUM"
        by_conf[conf] = by_conf.get(conf, 0) + 1

    link_stats = DashboardLinkStats(
        total_links=len(links),
        by_type=by_type,
        by_signal=by_signal,
        by_confidence=by_conf,
    )

    # 4. Recent pipeline runs (last 10)
    recent_runs_db = db.query(AgentRun).order_by(desc(AgentRun.id)).limit(10).all()
    recent_runs = []
    for r in recent_runs_db:
        try:
            steps_list = json.loads(r.steps) if r.steps else []
        except Exception:
            steps_list = []
        case_info = (
            r.source_case_number
            or (f"Judgment #{r.source_judgment_id}" if r.source_judgment_id else "Database")
        )
        if r.trigger == "RESCAN":
            msg = f"Database rescan checked {r.directions_checked_count} directions, updated {r.directions_updated_count}"
        elif r.outcome == "NO_CANDIDATES":
            msg = f"Order {case_info} analysed: no linked earlier directions found"
        elif r.directions_updated_count > 0:
            msg = f"New order {case_info} updated {r.directions_updated_count} directions (checked {r.directions_checked_count})"
        else:
            msg = f"Order {case_info} checked {r.directions_checked_count} directions (status verified)"

        recent_runs.append(
            AgentRunItem(
                id=r.id,
                trigger=r.trigger,
                source_judgment_id=r.source_judgment_id,
                source_case_number=r.source_case_number,
                steps=steps_list,
                directions_checked_count=r.directions_checked_count,
                directions_updated_count=r.directions_updated_count,
                outcome=r.outcome,
                errors=r.errors,
                duration_seconds=r.duration_seconds,
                created_at=r.created_at.isoformat() if r.created_at else "",
                message=msg,
            )
        )

    due_items.sort(key=lambda x: x.deadline_window_end or "9999-99-99")

    resp = DashboardResponse(
        status_counts=status_counts,
        overdue_no_record_count=overdue_count,
        contempt_filed_count=contempt_count,
        evidence_strength_split=strength_split,
        deadline_bucket_counts=bucket_counts,
        top_departments=top_10_depts,
        directions_due_next_30_days=due_items[:10],
        due_next_30_days_count=len(due_items),
        dataset_freshness=DashboardFreshness(
            latest_judgment_date=max_j_date.isoformat() if max_j_date else None,
            total_judgments=total_judgments,
            analysed_count=analysed_count,
        ),
        link_stats=link_stats,
        recent_pipeline_runs=recent_runs,
    )
    store_in_cache(cache_key, resp)
    return resp


@app.get("/calendar", response_model=CalendarResponse, tags=["Calendar"])
def get_compliance_calendar(
    month: Optional[str] = Query(None, description="Calendar month in YYYY-MM format"),
    db: Session = Depends(get_db),
):
    """Retrieve operative directions whose deadline window ends in the specified month."""
    if not month:
        latest_d = (
            db.query(Direction)
            .filter(Direction.deadline_window_end.isnot(None))
            .order_by(Direction.deadline_window_end.desc())
            .first()
        )
        if latest_d and latest_d.deadline_window_end:
            month = latest_d.deadline_window_end.strftime("%Y-%m")
        else:
            month = datetime.now(timezone.utc).strftime("%Y-%m")

    q = (
        db.query(Direction)
        .join(Judgment, Direction.judgment_id == Judgment.id)
        .filter(Direction.deadline_window_end.isnot(None))
        .filter(func.strftime("%Y-%m", Direction.deadline_window_end) == month)
        .order_by(Direction.deadline_window_end.asc())
    )
    records = q.all()

    status_summary = {"COMPLIED": 0, "PENDING": 0, "UNVERIFIED": 0}
    items = []
    for d in records:
        st = d.compliance_status or "UNVERIFIED"
        status_summary[st] = status_summary.get(st, 0) + 1
        j = d.judgment
        pev = d.evidence_list[0] if d.evidence_list else None
        cleaned_dept = clean_department_name(d.responsible_party)

        items.append(
            CalendarDirectionItem(
                id=d.id,
                direction_id=d.id,
                judgment_id=d.judgment_id,
                case_number=j.case_number if j else None,
                court=j.court if j else None,
                judgment_date=j.judgment_date.isoformat() if j and j.judgment_date else None,
                responsible_party=d.responsible_party,
                cleaned_department=cleaned_dept,
                action=d.action,
                deadline_phrase=d.deadline_phrase,
                deadline_window_start=d.deadline_window_start.isoformat() if d.deadline_window_start else None,
                deadline_window_end=d.deadline_window_end.isoformat(),
                deadline_status=d.deadline_status or "NO_DEADLINE",
                compliance_status=st,
                sub_reason=d.sub_reason,
                flags={
                    "contempt_filed": bool(d.contempt_filed or d.has_contempt_flag),
                    "extension_sought": bool(d.extension_sought),
                    "overdue_no_record": bool(d.overdue_no_record),
                    "contempt_dismissed_for_default": bool(d.contempt_dismissed_for_default),
                },
                explanation_text=d.explanation_text,
                evidence_strength=pev.evidence_strength if pev else None,
                evidence_scope=pev.evidence_scope if pev else None,
                judgment_link=f"/judgments/{d.judgment_id}",
            )
        )

    return CalendarResponse(
        month=month,
        total_directions=len(items),
        status_summary=status_summary,
        directions=items,
    )


@app.get("/ledger", response_model=LedgerResponse, tags=["Ledger"])
def get_compliance_ledger(
    department: Optional[str] = Query(None, description="Filter by responsible department/party"),
    court: Optional[str] = Query(None, description="Filter by court code or name"),
    status: Optional[str] = Query(None, description="Filter by headline status: COMPLIED, PENDING, UNVERIFIED"),
    bucket: Optional[str] = Query(None, description="Filter by deadline bucket: UPCOMING, IN_WINDOW, LAPSED, etc."),
    from_date: Optional[str] = Query(None, alias="from", description="Filter from date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="Filter to date (YYYY-MM-DD)"),
    year: Optional[int] = Query(None, description="Filter by year"),
    search: Optional[str] = Query(None, description="Text search in action, party, or case number"),
    overdue_only: bool = Query(False, description="Filter to overdue directions only"),
    contempt_only: bool = Query(False, description="Filter to directions with contempt petitions"),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="Override limit (compatibility)"),
    offset: Optional[int] = Query(None, ge=0, description="Override offset (compatibility)"),
    db: Session = Depends(get_db),
):
    """Retrieve operative directions compliance ledger with deterministic department cleaning and pagination."""
    q = db.query(Direction).join(Judgment, Direction.judgment_id == Judgment.id)

    if status:
        st_upper = status.strip().upper()
        q = q.filter(Direction.compliance_status == st_upper)

    if court:
        q = q.filter(Judgment.court.ilike(f"%{court.strip()}%"))

    if year:
        q = q.filter(Judgment.year == year)

    if bucket:
        b_upper = bucket.strip().upper()
        q = q.filter(Direction.deadline_status == b_upper)

    if from_date:
        try:
            f_d = date.fromisoformat(from_date.strip())
            q = q.filter((Direction.deadline_window_end >= f_d) | (Direction.deadline_window_start >= f_d))
        except Exception:
            pass

    if to_date:
        try:
            t_d = date.fromisoformat(to_date.strip())
            q = q.filter(Direction.deadline_window_end <= t_d)
        except Exception:
            pass

    if overdue_only:
        q = q.filter(Direction.overdue_no_record == True)

    if contempt_only:
        q = q.filter((Direction.contempt_filed == True) | (Direction.has_contempt_flag == True))

    if search:
        s_term = f"%{search.strip()}%"
        q = q.filter(
            (Direction.action.ilike(s_term))
            | (Direction.responsible_party.ilike(s_term))
            | (Judgment.case_number.ilike(s_term))
        )

    # Department filter: match either raw party or cleaned department
    all_matched_records = q.order_by(desc(Direction.id)).all()
    if department:
        d_lower = department.strip().lower()
        matched_records = [
            d for d in all_matched_records
            if d_lower in (d.responsible_party or "").lower() or d_lower in clean_department_name(d.responsible_party).lower()
        ]
    else:
        matched_records = all_matched_records

    total = len(matched_records)

    eff_limit = limit if limit is not None else page_size
    eff_offset = offset if offset is not None else (page - 1) * page_size
    eff_page = page if limit is None else (eff_offset // eff_limit) + 1
    total_pages = max(1, math.ceil(total / eff_limit))

    paged_records = matched_records[eff_offset : eff_offset + eff_limit]

    items = []
    for d in paged_records:
        j = d.judgment
        primary_ev = d.evidence_list[0] if d.evidence_list else None
        cleaned_dept = clean_department_name(d.responsible_party)
        items.append(
            LedgerItem(
                id=d.id,
                direction_id=d.id,
                judgment_id=d.judgment_id,
                case_number=j.case_number if j else None,
                court=j.court if j else None,
                judgment_date=j.judgment_date.isoformat() if j and j.judgment_date else None,
                responsible_party=d.responsible_party,
                cleaned_department=cleaned_dept,
                party_type=d.party_type,
                direction_type=d.direction_type or "mandatory",
                action=d.action,
                deadline_phrase=d.deadline_phrase,
                deadline_window_start=d.deadline_window_start.isoformat() if d.deadline_window_start else None,
                deadline_window_end=d.deadline_window_end.isoformat() if d.deadline_window_end else None,
                deadline_status=d.deadline_status or "NO_DEADLINE",
                explanation_text=d.explanation_text,
                compliance_status=d.compliance_status or "UNVERIFIED",
                status=d.compliance_status or "UNVERIFIED",
                sub_reason=d.sub_reason,
                flags={
                    "contempt_filed": bool(d.contempt_filed or d.has_contempt_flag),
                    "extension_sought": bool(d.extension_sought),
                    "overdue_no_record": bool(d.overdue_no_record),
                    "contempt_dismissed_for_default": bool(d.contempt_dismissed_for_default),
                },
                evidence_strength=primary_ev.evidence_strength if primary_ev else None,
                evidence_scope=primary_ev.evidence_scope if primary_ev else None,
                directions_covered_count=primary_ev.directions_covered_count if primary_ev else None,
                primary_quote=primary_ev.supporting_quote if primary_ev else None,
                primary_verdict=primary_ev.verdict if primary_ev else None,
                primary_case=primary_ev.source_case_number if primary_ev else None,
                evidence_count=len(d.evidence_list),
                judgment_link=f"/judgments/{d.judgment_id}",
            )
        )

    return LedgerResponse(
        total=total,
        page=eff_page,
        page_size=eff_limit,
        total_pages=total_pages,
        limit=eff_limit,
        offset=eff_offset,
        items=items,
    )


@app.get("/stats", response_model=OverallStatsResponse, tags=["Stats"])
def get_compliance_stats(db: Session = Depends(get_db)):
    """Retrieve compliance radar summary statistics with short TTL caching."""
    cache_key = "compliance_stats"
    cached = get_from_cache(cache_key)
    if cached:
        return cached

    total_judgments = db.query(Judgment).filter(Judgment.status == "INGESTED").count()
    directions = db.query(Direction).all()

    status_dist = {"COMPLIED": 0, "PENDING": 0, "UNVERIFIED": 0}
    flags_dist = {
        "overdue_no_record": 0,
        "contempt_filed": 0,
        "extension_sought": 0,
        "contempt_dismissed_for_default": 0,
    }
    strength_dist = {"COURT_RECORDED": 0, "PARTY_SUBMISSION": 0}
    case_level_count = 0
    dept_map: dict = {}

    for d in directions:
        st = d.compliance_status or "UNVERIFIED"
        status_dist[st] = status_dist.get(st, 0) + 1

        if d.overdue_no_record:
            flags_dist["overdue_no_record"] += 1
        if d.contempt_filed or d.has_contempt_flag:
            flags_dist["contempt_filed"] += 1
        if d.extension_sought:
            flags_dist["extension_sought"] += 1
        if d.contempt_dismissed_for_default:
            flags_dist["contempt_dismissed_for_default"] += 1

        if d.evidence_list:
            pev = d.evidence_list[0]
            if pev.evidence_strength in strength_dist:
                strength_dist[pev.evidence_strength] += 1
            if pev.evidence_scope == "CASE_LEVEL":
                case_level_count += 1

        dept = clean_department_name(d.responsible_party)
        dept_entry = dept_map.setdefault(dept, {"total": 0, "complied": 0, "pending": 0, "unverified": 0, "overdue": 0})
        dept_entry["total"] += 1
        if st == "COMPLIED":
            dept_entry["complied"] += 1
        elif st == "PENDING":
            dept_entry["pending"] += 1
        else:
            dept_entry["unverified"] += 1
        if d.overdue_no_record:
            dept_entry["overdue"] += 1

    top_depts = [
        DepartmentSummary(
            department=dept,
            total=data["total"],
            complied=data["complied"],
            pending=data["pending"],
            unverified=data["unverified"],
            overdue=data["overdue"],
        )
        for dept, data in sorted(dept_map.items(), key=lambda x: x[1]["total"], reverse=True)[:15]
    ]

    res = OverallStatsResponse(
        total_judgments=total_judgments,
        total_directions=len(directions),
        status_distribution=status_dist,
        flags_distribution=flags_dist,
        evidence_strength_distribution=strength_dist,
        case_level_directions_count=case_level_count,
        top_departments=top_depts,
    )
    store_in_cache(cache_key, res)
    return res


@app.get("/export.csv", tags=["Export"])
def export_compliance_csv(
    department: Optional[str] = Query(None, description="Filter by responsible department/party"),
    court: Optional[str] = Query(None, description="Filter by court code or name"),
    status: Optional[str] = Query(None, description="Filter by headline status: COMPLIED, PENDING, UNVERIFIED"),
    bucket: Optional[str] = Query(None, description="Filter by deadline bucket"),
    from_date: Optional[str] = Query(None, alias="from", description="Filter from date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, alias="to", description="Filter to date (YYYY-MM-DD)"),
    year: Optional[int] = Query(None, description="Filter by judgment year"),
    search: Optional[str] = Query(None, description="Text search"),
    overdue_only: bool = Query(False, description="Filter to overdue directions only"),
    contempt_only: bool = Query(False, description="Filter to directions with contempt petitions"),
    db: Session = Depends(get_db),
):
    """Export filtered operative directions compliance ledger as CSV."""
    q = db.query(Direction).join(Judgment, Direction.judgment_id == Judgment.id)

    if status:
        st_upper = status.strip().upper()
        q = q.filter(Direction.compliance_status == st_upper)

    if court:
        q = q.filter(Judgment.court.ilike(f"%{court.strip()}%"))

    if year:
        q = q.filter(Judgment.year == year)

    if bucket:
        b_upper = bucket.strip().upper()
        q = q.filter(Direction.deadline_status == b_upper)

    if from_date:
        try:
            f_d = date.fromisoformat(from_date.strip())
            q = q.filter((Direction.deadline_window_end >= f_d) | (Direction.deadline_window_start >= f_d))
        except Exception:
            pass

    if to_date:
        try:
            t_d = date.fromisoformat(to_date.strip())
            q = q.filter(Direction.deadline_window_end <= t_d)
        except Exception:
            pass

    if overdue_only:
        q = q.filter(Direction.overdue_no_record == True)

    if contempt_only:
        q = q.filter((Direction.contempt_filed == True) | (Direction.has_contempt_flag == True))

    if search:
        s_term = f"%{search.strip()}%"
        q = q.filter(
            (Direction.action.ilike(s_term))
            | (Direction.responsible_party.ilike(s_term))
            | (Judgment.case_number.ilike(s_term))
        )

    all_matched = q.order_by(Direction.id.asc()).all()
    if department:
        d_lower = department.strip().lower()
        directions = [
            d for d in all_matched
            if d_lower in (d.responsible_party or "").lower() or d_lower in clean_department_name(d.responsible_party).lower()
        ]
    else:
        directions = all_matched

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "direction_id",
        "case_number",
        "court",
        "judgment_date",
        "responsible_party_raw",
        "cleaned_department",
        "party_type",
        "direction_type",
        "action",
        "deadline_phrase",
        "deadline_window_start",
        "deadline_window_end",
        "deadline_status",
        "compliance_status",
        "sub_reason",
        "overdue_no_record",
        "contempt_filed",
        "extension_sought",
        "contempt_dismissed_for_default",
        "evidence_strength",
        "evidence_scope",
        "directions_covered_count",
        "supporting_quote",
        "linked_follow_up_case",
    ])

    for d in directions:
        j = d.judgment
        pev = d.evidence_list[0] if d.evidence_list else None
        cleaned_dept = clean_department_name(d.responsible_party)
        writer.writerow([
            d.id,
            j.case_number if j else "",
            j.court if j else "",
            j.judgment_date.isoformat() if j and j.judgment_date else "",
            d.responsible_party,
            cleaned_dept,
            d.party_type,
            d.direction_type or "mandatory",
            d.action,
            d.deadline_phrase or "",
            d.deadline_window_start.isoformat() if d.deadline_window_start else "",
            d.deadline_window_end.isoformat() if d.deadline_window_end else "",
            d.deadline_status or "NO_DEADLINE",
            d.compliance_status or "UNVERIFIED",
            d.sub_reason or "",
            bool(d.overdue_no_record),
            bool(d.contempt_filed or d.has_contempt_flag),
            bool(d.extension_sought),
            bool(d.contempt_dismissed_for_default),
            pev.evidence_strength if pev else "",
            pev.evidence_scope if pev else "",
            pev.directions_covered_count if pev else "",
            pev.supporting_quote if pev else "",
            pev.source_case_number if pev else "",
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="compliance_ledger.csv"'},
    )


# ============================================================================
# Autonomous Agent Endpoints
# ============================================================================

@app.get("/agent/runs", response_model=AgentRunsResponse, tags=["Autonomous Agent"])
def list_agent_runs(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Retrieve recent autonomous follow-up analysis agent runs and activity feed."""
    query = db.query(AgentRun).order_by(desc(AgentRun.id))
    total = query.count()
    records = query.offset(offset).limit(limit).all()

    items = []
    for r in records:
        try:
            steps_list = json.loads(r.steps) if r.steps else []
        except Exception:
            steps_list = []

        case_info = (
            r.source_case_number
            or (f"Judgment #{r.source_judgment_id}" if r.source_judgment_id else "Database")
        )
        if r.trigger == "RESCAN":
            msg = f"Database rescan checked {r.directions_checked_count} directions, updated {r.directions_updated_count}"
        elif r.outcome == "NO_CANDIDATES":
            msg = f"Order {case_info} analysed: no linked earlier directions found"
        elif r.directions_updated_count > 0:
            msg = f"New order {case_info} updated {r.directions_updated_count} directions (checked {r.directions_checked_count})"
        else:
            msg = f"Order {case_info} checked {r.directions_checked_count} directions (status verified)"

        items.append(
            AgentRunItem(
                id=r.id,
                trigger=r.trigger,
                source_judgment_id=r.source_judgment_id,
                source_case_number=r.source_case_number,
                steps=steps_list,
                directions_checked_count=r.directions_checked_count,
                directions_updated_count=r.directions_updated_count,
                outcome=r.outcome,
                errors=r.errors,
                duration_seconds=r.duration_seconds,
                created_at=r.created_at.isoformat() if r.created_at else "",
                message=msg,
            )
        )

    return AgentRunsResponse(total=total, runs=items)


@app.post("/agent/rescan", response_model=RescanResponse, tags=["Autonomous Agent"])
def trigger_agent_rescan(db: Session = Depends(get_db)):
    """Run full autonomous follow-up agent scan across all database judgments."""
    try:
        from backend.pipeline.followup_agent import FollowUpAnalysisAgent
        agent = FollowUpAnalysisAgent(source_judgment=None, trigger="RESCAN")
        run_rec = agent.run(db=db)
        msg = (
            f"Rescan completed ({run_rec.outcome}): checked {run_rec.directions_checked_count}, "
            f"updated {run_rec.directions_updated_count} directions in {run_rec.duration_seconds:.2f}s."
        )
        return RescanResponse(
            run_id=run_rec.id,
            trigger=run_rec.trigger,
            outcome=run_rec.outcome,
            directions_checked=run_rec.directions_checked_count,
            directions_updated=run_rec.directions_updated_count,
            duration_seconds=run_rec.duration_seconds,
            message=msg,
        )
    except Exception as exc:
        logger.error(f"Agent rescan failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Agent rescan error: {str(exc)}")


# ============================================================================
# Phase 6: Evaluation Harness Endpoints
# ============================================================================

@app.get("/eval/results", tags=["Evaluation"])
def get_evaluation_results():
    """Retrieve the latest evaluation metrics across extraction, deadline resolution, and linking."""
    results_file = Path("eval/results/latest.json")
    if not results_file.exists():
        try:
            from eval.run_all_evals import run_all_evaluations
            return run_all_evaluations()
        except Exception as exc:
            logger.error(f"Failed to run evaluations: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to generate evaluation results: {str(exc)}")

    try:
        with open(results_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read evaluation results: {str(exc)}")


@app.post("/eval/run", tags=["Evaluation"])
def run_evaluation_suite():
    """Trigger a live execution of the full evaluation harness and update latest.json."""
    try:
        from eval.run_all_evals import run_all_evaluations
        results = run_all_evaluations()
        return results
    except Exception as exc:
        logger.error(f"Evaluation suite run failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Evaluation run failed: {str(exc)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
