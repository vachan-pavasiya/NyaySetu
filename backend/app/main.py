"""Main FastAPI application entry point.

Role: Configures HTTP server, CORS middleware, startup events, and health check.
Data flow: Inbound HTTP -> Router -> Database/Pipelines -> JSON response.
"""

from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.config import get_settings, Settings
from backend.app.database import engine, Base, get_db
import backend.app.models  # Registers models with Base.metadata

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
