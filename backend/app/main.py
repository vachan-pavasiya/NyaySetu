"""Main FastAPI application entry point.

Role: Configures HTTP server, CORS middleware, lifespan events, health check,
      background ingestion jobs, and judgment query API.
Data flow: Inbound HTTP -> Router -> Database/Pipelines -> JSON response.
"""

import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text, desc
from sqlalchemy.orm import Session

from backend.app.config import get_settings, Settings
from backend.app.database import engine, Base, get_db, SessionLocal
import backend.app.models as models
from backend.app.models import Judgment, IngestJob
from backend.pipeline.ingest import run_ingestion

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
