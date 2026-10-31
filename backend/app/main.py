"""Main FastAPI application entry point.

Role: Configures HTTP server, CORS middleware, lifespan events, health check,
      background ingestion jobs, and judgment query API.
Data flow: Inbound HTTP -> Router -> Database/Pipelines -> JSON response.
"""

import uuid
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional, Union, Any

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text, desc
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
)
from backend.pipeline.ingest import run_ingestion
from backend.pipeline.agent import ComplianceExtractionAgent, analyze_judgment

logger = logging.getLogger("compliance_radar.api")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager: initialises database tables on startup."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Court-Order Compliance Radar",
    description="Agentic tracking and verification of High Court compliance directions.",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for frontend Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    flags: dict
    explanation_text: Optional[str] = None
    evidence: List[EvidenceItem]
    created_at: str


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
    metrics: dict
    step_logs: List[dict]


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
    """Run agentic segmentation, direction extraction, and verbatim verification on a judgment."""
    try:
        result = analyze_judgment(judgment_id, db=db)
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
            model_used=e.model_used,
            method=e.method,
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in d.evidence_list
    ]

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
        flags={
            "contempt_filed": bool(d.contempt_filed or d.has_contempt_flag),
            "extension_sought": bool(d.extension_sought),
            "overdue_no_record": bool(d.overdue_no_record),
            "contempt_dismissed_for_default": bool(d.contempt_dismissed_for_default),
        },
        explanation_text=d.explanation_text,
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


@app.get("/cases/{cnr:path}/timeline", response_model=CaseTimelineResponse, tags=["Timeline"])
def get_case_timeline(cnr: str, db: Session = Depends(get_db)):
    """Retrieve unified case timeline by CNR or Case Number."""
    # Support lookup by CNR or Case Number
    j = (
        db.query(Judgment)
        .filter((Judgment.cnr == cnr) | (Judgment.case_number == cnr))
        .first()
    )
    if not j:
        # Case insensitive case number lookup
        j = db.query(Judgment).filter(Judgment.case_number.ilike(cnr)).first()

    if not j:
        raise HTTPException(status_code=404, detail=f"Case with CNR / Case Number '{cnr}' not found")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
