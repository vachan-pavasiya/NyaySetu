"""Gemini-powered operative direction extraction module.

Role: Prompts Google Gemini with strict Pydantic schema validation, caches responses in SQLite,
      enforces concurrency limits with exponential backoff, filters procedural boilerplate,
      and chunks long orders. Falls back to deterministic extractor only upon API failure.
Data flow: Operative segment text -> SQLite cache check -> Gemini API -> Pydantic validation -> DirectionExtractionOutput.
"""

import os
import re
import json
import time
import hashlib
import logging
import threading
from typing import Optional, List

from google import genai
from google.genai import types
from google.genai.errors import APIError

from backend.app.config import get_settings
from backend.app.database import SessionLocal
from backend.app.models import LLMCache
from backend.pipeline.models import (
    ExtractedDirection,
    DirectionExtractionOutput,
    PartyType,
    DirectionType,
)

logger = logging.getLogger("compliance_radar.extract")
settings = get_settings()

# Max 3 concurrent Gemini requests
CONCURRENCY_SEMAPHORE = threading.Semaphore(3)

# Global call counters for acceptance reporting
CALL_METRICS = {
    "live_calls": 0,
    "cached_calls": 0,
    "fallback_calls": 0,
}

_ACTIVE_GEMINI_MODEL: Optional[str] = None


def reset_call_metrics():
    """Reset call metrics counters."""
    CALL_METRICS["live_calls"] = 0
    CALL_METRICS["cached_calls"] = 0
    CALL_METRICS["fallback_calls"] = 0


def get_call_metrics() -> dict:
    """Return a snapshot of current extraction call metrics."""
    return dict(CALL_METRICS)


# Non-substantive procedural boilerplate patterns to filter out
BOILERPLATE_PATTERNS = [
    r"server\s+copy",
    r"act\s+on\s+(?:a\s+)?(?:the\s+)?(?:downloaded\s+)?server\s+copy",
    r"downloaded\s+from\s+(?:the\s+)?official\s+website",
    r"photostat\s+(?:certified\s+)?copy",
    r"urgent\s+photostat",
    r"certified\s+copy\s+of\s+this\s+order,\s*if\s+applied\s+for",
    r"affidavit\s+of\s+service",
    r"(?:taken|kept)\s+on\s+record",
    r"kept\s+with\s+(?:the\s+)?record",
    r"written\s+instruction[s]?\s+filed\s+in\s+court",
    r"stand[s]?\s+over\s+for",
    r"appear\s+in\s+the\s+list",
    r"list\s+(?:the\s+)?matter",
    r"matter\s+is\s+adjourned",
]


def is_boilerplate_direction(source_quote: str, action: str = "") -> bool:
    """Return True if direction is non-substantive administrative or procedural boilerplate."""
    combined = f"{source_quote} {action}".strip()
    for pat in BOILERPLATE_PATTERNS:
        if re.search(pat, combined, re.IGNORECASE):
            return True
    return False


EXTRACTION_SYSTEM_PROMPT = """You are an Indian High Court legal compliance auditor.
Your job is to read the operative portion of an Indian High Court judgment order and extract every distinct substantive direction issued by the court.

CRITICAL RULES:
1. ONLY extract substantive operative directions where the court commands or directs an authority, department, officer, or party to do or refrain from doing something on the merits (e.g. decide a representation, disburse retirement benefits, conduct an inspection, remove illegal encroachment, pass a reasoned order).
2. For EVERY direction, 'source_quote' MUST BE A STRICT, EXACT VERBATIM SUBSTRING of the text. Do not paraphrase, summarize, omit, or add ANY word or punctuation. Any altered quote will fail automated verification.
3. Identify the responsible party clearly (e.g. 'Howrah Municipal Corporation', 'Director of School Education', 'State of West Bengal', 'Respondent No. 3').
4. Classify party_type as: 'state', 'department', 'officer', 'private', or 'other'.
5. Classify direction_type as:
   - 'mandatory': Court orders an action to be done (e.g. 'is directed to decide representation within 4 weeks')
   - 'liberty': Court gives permission/freedom to a party (e.g. 'petitioner is at liberty to approach civil court')
   - 'consequential': Follow-up step dependent on main direction (e.g. 'upon such determination, disbursement shall follow')
6. Extract the 'deadline_phrase' if the court specifies a timeframe (e.g. 'within four weeks', 'within 30 days', 'by 15th December 2023', 'expeditiously'). If no timeframe is mentioned, set deadline_phrase to null.
7. CRITICAL EXCLUSIONS - DO NOT EXTRACT BOILERPLATE:
   - DO NOT extract instructions to "act on a server copy of this order" or "download from the official website".
   - DO NOT extract directions for "urgent photostat / certified copy" or "compliance of formalities".
   - DO NOT extract directions that "affidavit of service be kept on record".
   - DO NOT extract listing or adjournment instructions ("matter to appear in the list").
8. If the order contains NO substantive operative directions (e.g. simple dismissal, withdrawal, or only procedural boilerplate), return has_operative_directions=false and empty directions array.
"""


def compute_cache_key(prompt: str, text: str) -> str:
    """Compute SHA-256 hash of prompt and input text for deterministic replay."""
    combined = f"{prompt}\n---\n{text}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def get_cached_response(cache_key: str) -> Optional[str]:
    """Retrieve cached response JSON from SQLite table if present."""
    with SessionLocal() as db:
        cached = db.query(LLMCache).filter(LLMCache.cache_key == cache_key).first()
        if cached:
            return cached.response_json
    return None


def save_cached_response(cache_key: str, prompt_hash: str, model_name: str, response_json: str):
    """Save Gemini response JSON to SQLite cache table."""
    try:
        with SessionLocal() as db:
            entry = LLMCache(
                cache_key=cache_key,
                prompt_hash=prompt_hash,
                model_name=model_name,
                response_json=response_json,
            )
            db.merge(entry)
            db.commit()
    except Exception as exc:
        logger.warning(f"Failed to write to LLMCache: {exc}")


def rule_based_fallback_extraction(operative_text: str) -> DirectionExtractionOutput:
    """Deterministic extraction fallback triggered ONLY when Gemini API fails or key is missing."""
    directions: List[ExtractedDirection] = []

    # Sentence splitting
    sentences = re.split(r"(?<=[.!?])\s+", operative_text)
    for sent in sentences:
        s = sent.strip()
        if len(s) < 25:
            continue

        # Skip administrative/procedural boilerplate
        if is_boilerplate_direction(s):
            continue

        # Check for direction markers
        if re.search(
            r"(?:is|are|hereby)\s+directed\s+to|directing\s+(?:the\s+)?[A-Za-z\s,]+?\s+to|shall\s+(?:consider|decide|dispose|pass|release|take|verify|pay|act)|this\s+Court\s+directs",
            s,
            re.I,
        ):
            # Extract deadline phrase if present
            d_match = re.search(
                r"(?:within\s+(?:a\s+period\s+of\s+)?(?:\w+\s+)?(?:weeks?|months?|days?|fortnights?)|by\s+[0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+|\bforthwith\b|\bexpeditiously\b)",
                s,
                re.I,
            )
            deadline = d_match.group(0).strip() if d_match else None

            # Extract responsible party candidate
            resp_match = re.search(
                r"(?:respondent[s]?\s*(?:no[s]?\.?\s*\d+)?|respondent\s+authorities|State\s+of\s+[A-Za-z\s]+|Commissioner[,\s]+[A-Za-z\s]+Corporation|Director\s+of\s+[A-Za-z\s,]+|District\s+Inspector\s+of\s+School|Treasury\s+Officer|Director|Commissioner|Corporation|Board)",
                s,
                re.I,
            )
            resp_party = resp_match.group(0).strip() if resp_match else "Respondent Authorities"

            directions.append(
                ExtractedDirection(
                    responsible_party=resp_party,
                    party_type=PartyType.department,
                    action=s[:200],
                    deadline_phrase=deadline,
                    source_quote=s,
                    confidence=0.85,
                    direction_type=DirectionType.mandatory,
                    extraction_method="fallback",
                )
            )

    return DirectionExtractionOutput(
        has_operative_directions=len(directions) > 0,
        directions=directions,
    )


def call_gemini_extraction(
    operative_text: str,
    feedback: Optional[str] = None,
) -> DirectionExtractionOutput:
    """Call Google Gemini to extract structured directions with caching, retries, and fallback."""
    global _ACTIVE_GEMINI_MODEL
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")

    # If no API key configured, use deterministic rule-based extractor
    if not api_key:
        logger.warning("GEMINI_API_KEY not configured. Falling back to deterministic rule-based extractor.")
        CALL_METRICS["fallback_calls"] += 1
        return rule_based_fallback_extraction(operative_text)

    prompt = f"OPERATIVE ORDER TEXT:\n\"\"\"\n{operative_text}\n\"\"\""
    if feedback:
        prompt += (
            f"\n\nIMPORTANT PREVIOUS ATTEMPT FEEDBACK:\n{feedback}\n"
            f"Please fix the quotes so they match the text EXACTLY verbatim without adding or removing words."
        )

    cache_key = compute_cache_key(EXTRACTION_SYSTEM_PROMPT, prompt)

    # 1. Check SQLite LLM Cache
    cached_json = get_cached_response(cache_key)
    if cached_json:
        logger.info(f"Loaded LLM response from SQLite cache (key: {cache_key[:12]}...)")
        CALL_METRICS["cached_calls"] += 1
        try:
            cached_output = DirectionExtractionOutput.model_validate_json(cached_json)
            # Ensure extraction_method and filter boilerplate on cached items
            substantive_dirs = []
            for d in cached_output.directions:
                if not is_boilerplate_direction(d.source_quote, d.action):
                    substantive_dirs.append(d.model_copy(update={"extraction_method": "gemini"}))
            return DirectionExtractionOutput(
                has_operative_directions=len(substantive_dirs) > 0,
                directions=substantive_dirs,
                dismissal_reason=cached_output.dismissal_reason,
            )
        except Exception as exc:
            logger.warning(f"Cache deserialization failed: {exc}. Re-querying Gemini.")

    # 2. Call Gemini SDK with Candidate Model Priority List & Concurrency Limiting
    client = genai.Client(api_key=api_key)

    configured_model = settings.GEMINI_MODEL or "gemini-3.8-flash"
    # Build candidate models: active working model first, then configured, then fast fallbacks
    candidate_models: List[str] = []
    if _ACTIVE_GEMINI_MODEL:
        candidate_models.append(_ACTIVE_GEMINI_MODEL)
    if configured_model not in candidate_models:
        candidate_models.append(configured_model)
    for backup in ["gemini-flash-lite-latest", "gemini-3.1-flash-lite"]:
        if backup not in candidate_models:
            candidate_models.append(backup)

    last_error: Optional[Exception] = None

    with CONCURRENCY_SEMAPHORE:
        for model_name in candidate_models:
            max_retries = 2
            delay = 1.5

            for attempt in range(max_retries):
                try:
                    logger.info(f"Invoking Gemini model '{model_name}' (attempt {attempt + 1}/{max_retries})")
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=EXTRACTION_SYSTEM_PROMPT,
                            response_mime_type="application/json",
                            response_schema=DirectionExtractionOutput,
                            temperature=0.0,
                            http_options=types.HttpOptions(timeout=10000),
                        ),
                    )

                    raw_json = response.text
                    output = DirectionExtractionOutput.model_validate_json(raw_json)

                    # Update active model on success
                    _ACTIVE_GEMINI_MODEL = model_name

                    # Save raw response to cache
                    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                    save_cached_response(cache_key, prompt_hash, model_name, raw_json)
                    CALL_METRICS["live_calls"] += 1

                    # Filter out non-substantive procedural boilerplate and tag extraction_method
                    substantive_dirs = []
                    for d in output.directions:
                        if not is_boilerplate_direction(d.source_quote, d.action):
                            substantive_dirs.append(
                                d.model_copy(update={"extraction_method": "gemini"})
                            )

                    return DirectionExtractionOutput(
                        has_operative_directions=len(substantive_dirs) > 0,
                        directions=substantive_dirs,
                        dismissal_reason=output.dismissal_reason,
                    )

                except APIError as api_err:
                    last_error = api_err
                    logger.warning(f"Gemini API error with '{model_name}': {api_err}")
                    # If 504 (timeout) or 404/503, immediately try next candidate model
                    err_msg = str(api_err)
                    if "504" in err_msg or "404" in err_msg or "503" in err_msg:
                        logger.info(f"Model '{model_name}' degraded or unavailable. Trying alternative model.")
                        break
                    time.sleep(delay)
                    delay *= 2.0
                except Exception as exc:
                    last_error = exc
                    logger.warning(f"Gemini call exception with '{model_name}': {exc}")
                    err_msg = str(exc)
                    if "504" in err_msg or "404" in err_msg or "503" in err_msg:
                        break
                    time.sleep(delay)
                    delay *= 2.0

    # 3. Only if ALL Gemini candidates fail, trigger deterministic rule-based fallback
    logger.error(f"All Gemini live API models failed ({last_error}). Triggering rule-based fallback.")
    CALL_METRICS["fallback_calls"] += 1
    return rule_based_fallback_extraction(operative_text)


def extract_directions_with_chunking(
    operative_text: str,
    feedback: Optional[str] = None,
) -> DirectionExtractionOutput:
    """Extract directions, chunking text if longer than 8,000 characters."""
    if len(operative_text) <= 8000:
        return call_gemini_extraction(operative_text, feedback=feedback)

    # Chunk long texts into ~4,000 char paragraphs
    paragraphs = operative_text.split("\n\n")
    chunks = []
    current_chunk = []
    current_len = 0

    for p in paragraphs:
        if current_len + len(p) > 4000 and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [p]
            current_len = len(p)
        else:
            current_chunk.append(p)
            current_len += len(p)
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    all_directions: List[ExtractedDirection] = []
    for chunk in chunks:
        res = call_gemini_extraction(chunk, feedback=feedback)
        if res.has_operative_directions:
            all_directions.extend(res.directions)

    # Deduplicate by normalized source quote and filter boilerplate
    seen_quotes = set()
    unique_dirs = []
    for d in all_directions:
        if is_boilerplate_direction(d.source_quote, d.action):
            continue
        norm = " ".join(d.source_quote.strip().split())
        if norm not in seen_quotes:
            seen_quotes.add(norm)
            unique_dirs.append(d)

    return DirectionExtractionOutput(
        has_operative_directions=len(unique_dirs) > 0,
        directions=unique_dirs,
    )
