"""Pipeline package proxy to backend.pipeline."""
from backend.pipeline.ingest import run_ingestion, main

__all__ = ["run_ingestion", "main"]

