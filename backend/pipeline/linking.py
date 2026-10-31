"""Follow-up order linking and compliance classification module.

Role: Identifies links between original court orders and follow-up proceedings (contempt petitions,
      appeals, compliance reports) using prioritised signals, validates temporal chronology,
      and classifies follow-up order outcomes using Gemini with verbatim quote verification.
Data flow: DB Judgments & Directions -> Citation Normalisation & Signal Matching -> Temporal Sanity Check ->
           Gemini Verdict Classifier -> Verbatim Verifier (with retry) -> SQLite CaseLinks & Evidence.
"""

import hashlib
import json
import logging
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database import SessionLocal
from backend.app.models import CaseLink, Direction, Evidence, Judgment, LLMCache
from backend.pipeline.verify import normalize_whitespace

logger = logging.getLogger("compliance_radar.linking")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

settings = get_settings()

CITATION_PATTERN = re.compile(
    r"\b(?:in\s+)?(W\.?P\.?(?:A|C)?\.?(?:\s*\([A-Za-z0-9]+\))?|MAT|M\.A\.T\.|FMA|F\.M\.A\.|WPLRT|CPAN|WPCRC)\.?\s*(?:No\.?)?\s*(\d+)\s*(?:of|/)\s*(\d{4})\b",
    re.IGNORECASE,
)


def normalize_case_citation(raw_citation: str) -> Optional[str]:
    """Normalize any Indian High Court case citation string into standard 'PREFIX/NUMBER/YEAR' format.
    
    Examples:
        'W.P.A. No. 2222 of 2022' -> 'WPA/2222/2022'
        'MAT 408 of 2022' -> 'MAT/408/2022'
        'FMA 1879 of 2019' -> 'FMA/1879/2019'
        'WPA No. 4409 of 2022' -> 'WPA/4409/2022'
        'CPAN 1088 of 2023 in WPA 11369 of 2023' -> 'WPA/11369/2023'
    """
    if not raw_citation or not isinstance(raw_citation, str):
        return None

    # If the citation contains 'in <writ>', extract the target writ first
    in_match = re.search(r"\bin\s+([A-Za-z\.\(\)\s]+?\s*\d+\s*(?:of|/)\s*\d{4})", raw_citation, re.IGNORECASE)
    target_str = in_match.group(1) if in_match else raw_citation

    match = CITATION_PATTERN.search(target_str)
    if not match:
        match = CITATION_PATTERN.search(raw_citation)
    if not match:
        # Fallback for clean 'TYPE/NUM/YEAR'
        simple = re.search(r"\b([A-Za-z\.]+)/(\d+)/(\d{4})\b", target_str)
        if simple:
            pfx, num, yr = simple.groups()
            clean_pfx = re.sub(r"[\.\s]", "", pfx).upper()
            return f"{clean_pfx}/{num}/{yr}"
        return None

    prefix, num, yr = match.groups()
    clean_pfx = re.sub(r"[\.\s\(\)]", "", prefix).upper()
    if clean_pfx in ("WP", "WPA", "WPC", "WPW", "WPAW"):
        norm_pfx = "WPA"
    elif clean_pfx in ("MAT",):
        norm_pfx = "MAT"
    elif clean_pfx in ("FMA",):
        norm_pfx = "FMA"
    elif clean_pfx in ("WPLRT",):
        norm_pfx = "WPLRT"
    elif clean_pfx in ("CPAN",):
        norm_pfx = "CPAN"
    elif clean_pfx in ("WPCRC",):
        norm_pfx = "WPCRC"
    else:
        norm_pfx = clean_pfx

    return f"{norm_pfx}/{num}/{yr}"


def extract_header_citations(text: str, current_case_number: Optional[str] = None) -> List[Tuple[str, str]]:
    """Extract cited prior case numbers from judgment header (first 1500 chars).
    
    Returns list of (raw_match_string, normalized_case_number).
    """
    if not text:
        return []

    header = text[:1500]
    matches = CITATION_PATTERN.findall(header)
    citations: List[Tuple[str, str]] = []
    seen = set()

    current_norm = normalize_case_citation(current_case_number) if current_case_number else None

    for m in matches:
        prefix, num, yr = m
        raw_str = f"{prefix} {num} of {yr}"
        norm = normalize_case_citation(raw_str)
        if not norm or norm == current_norm or norm in seen:
            continue
        seen.add(norm)
        citations.append((raw_str, norm))

    return citations


def check_temporal_sanity(
    earlier_date: Optional[date],
    later_date: Optional[date],
    earlier_case: Optional[str] = None,
    later_case: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Enforce temporal sanity rule.
    
    A writ direction can only be linked to a contempt petition if:
    1. The writ order's judgment_date is on or before the contempt order's judgment_date.
    2. The contempt filing year (parsed from case number) cannot be strictly earlier than writ order date year.
    
    Returns:
        (is_valid: bool, conflict_reason: Optional[str])
    """
    if not earlier_date or not later_date:
        return True, None

    if earlier_date > later_date:
        return False, (
            f"Temporal conflict: earlier order date ({earlier_date}) is after "
            f"follow-up order date ({later_date})."
        )

    # Check filing year in follow-up case number (e.g. WPCRC/18046/2005 filed in 2005 vs writ order dated 2022)
    if later_case:
        yr_match = re.search(r"/(\d{4})$", later_case)
        if yr_match:
            later_filing_year = int(yr_match.group(1))
            if later_filing_year < earlier_date.year:
                return False, (
                    f"Temporal conflict: follow-up case {later_case} filed in {later_filing_year}, "
                    f"which predates earlier order date ({earlier_date})."
                )

    return True, None


def verify_follow_up_quote(quote: str, source_text: str) -> bool:
    """Verify that the supporting quote is a verbatim substring of source text."""
    if not quote or not source_text:
        return False
    norm_quote = normalize_whitespace(quote).strip().lower()
    norm_source = normalize_whitespace(source_text).strip().lower()
    return norm_quote in norm_source


def build_cache_key(model: str, direction_id: int, later_judgment_id: int, prompt: str) -> str:
    """Return deterministic SHA256 cache key for LLM verdicts."""
    raw = f"{model}:{direction_id}:{later_judgment_id}:{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


FOLLOW_UP_SYSTEM_PROMPT = """You are an Indian High Court compliance verification auditor.
You are given:
1. An original court direction issued in an earlier order (responsible party, action ordered, deadline).
2. The full text of a subsequent follow-up order or contempt petition in the same matter.

Your job is to determine what the follow-up order reveals about compliance with the original direction.

VERDICT OPTIONS (choose EXACTLY ONE):
- COMPLIANCE_SHOWN: The later order records or finds that compliance has occurred (e.g. 'recording compliance of the order', 'compliance report filed and accepted', 'reasoned order passed', 'advocates submit order has been complied with').
- ONGOING_PROCESS: The later order shows that compliance is actively in progress or ongoing efforts are taking place (e.g., authorities directed to continue efforts, meetings scheduled to consider transfer/representation, compliance report taken on record but further action directed/pending).
- NON_COMPLIANCE_ALLEGED: The follow-up order is a contempt petition alleging non-compliance, but no finding of compliance is recorded yet.
- NOTICE_ISSUED: The court issued a notice, rule, or directed personal appearance / affidavit of compliance.
- EXTENSION_SOUGHT: The respondent prayed for extension of time to comply, or the court granted an extension.
- DISMISSED_FOR_DEFAULT: The contempt petition was dismissed because the applicant/petitioner or counsel was absent, took no steps, or did not press the matter. (CRITICAL: This is NOT evidence of compliance).
- DISPOSED_NO_FINDING: The follow-up order was disposed of or dismissed without any finding or detail on compliance.
- UNRELATED: The follow-up order does not relate to this direction.

OUTPUT FORMAT:
Return a strictly valid JSON object with:
{
  "verdict": "<ONE_OF_THE_ABOVE>",
  "evidence_strength": "COURT_RECORDED | PARTY_SUBMISSION | null",
  "supporting_quote": "<EXACT VERBATIM SUBSTRING from the later order text>",
  "reasoning": "<Concise explanation of how the quote supports the verdict>"
}

CRITICAL RULES:
1. 'supporting_quote' MUST be an EXACT, VERBATIM substring of the follow-up order text. Do not paraphrase or alter even one word.
2. Contempt dismissed for default or absence of petitioner is DISMISSED_FOR_DEFAULT, NEVER COMPLIANCE_SHOWN.
3. For COMPLIANCE_SHOWN:
   - Set 'evidence_strength' to 'COURT_RECORDED' if the court itself finds or records compliance (e.g. 'The alleged contemnor, therefore, has complied...', 'recording compliance of the order', 'order under contempt has substantially been complied with').
   - Set 'evidence_strength' to 'PARTY_SUBMISSION' if counsel or party states/submits that the order has been complied with (e.g. 'submitted on behalf of both the parties that the order has been complied with', 'learned advocates submit that the order-in-question has been complied with').
"""


def determine_evidence_strength(supporting_quote: Optional[str], full_text: Optional[str] = "") -> Optional[str]:
    """Determine whether evidence is COURT_RECORDED or PARTY_SUBMISSION.
    
    COURT_RECORDED: The court itself records or makes a finding of compliance.
    PARTY_SUBMISSION: Counsel or a party submits / states that compliance was made.
    """
    if not supporting_quote:
        return None
    quote_lower = supporting_quote.lower()
    full_lower = full_text.lower() if full_text else quote_lower

    party_terms = (
        "submit", "submitted", "submission", "submits",
        "learned advocate", "learned advocates", "advocate appears",
        "counsel for the", "learned counsel", "on behalf of both",
        "on behalf of the", "advocate for the",
    )
    court_direct_terms = (
        "alleged contemnor, therefore, has complied",
        "therefore, has complied",
        "recording compliance",
        "substantially been complied with",
        "we dispose of the contempt application by recording compliance",
        "contemnor has complied with this court",
    )

    # 1. Direct court findings
    for c_term in court_direct_terms:
        if c_term in quote_lower:
            return "COURT_RECORDED"

    # 2. Check for party submissions
    for p_term in party_terms:
        if p_term in quote_lower:
            # If the court weighed the submission and reached an affirmative judicial finding
            if "it appears" in quote_lower and "substantially been complied with" in quote_lower:
                return "COURT_RECORDED"
            return "PARTY_SUBMISSION"

    for c_term in court_direct_terms:
        if c_term in full_lower:
            return "COURT_RECORDED"

    for p_term in party_terms:
        if p_term in full_lower:
            return "PARTY_SUBMISSION"

    return "COURT_RECORDED"


def classify_follow_up_order_heuristic(follow_up_text: str) -> Dict[str, Any]:
    """Deterministic fallback classification when LLM is unavailable."""
    norm = normalize_whitespace(follow_up_text).lower()

    if "continues to make efforts" in norm or "shall continue to do so" in norm or "shall sit with" in norm:
        m = re.search(r"(?:continues\s+to\s+make\s+efforts[^\n\.]*|shall\s+continue\s+to\s+do\s+so[^\n\.]*|shall\s+sit\s+with[^\n\.]*)", follow_up_text, re.I)
        quote = m.group(0) if m else "continues to make efforts"
        return {
            "verdict": "ONGOING_PROCESS",
            "evidence_strength": None,
            "supporting_quote": quote,
            "reasoning": "Follow-up order indicates an ongoing process or efforts continuing towards compliance.",
            "method": "heuristic",
        }

    if "recording compliance" in norm or "compliance of the order" in norm or "has complied with" in norm or "complied with" in norm:
        # Locate exact quote
        m = re.search(r"(?:recording\s+compliance\s+of\s+the\s+order[^.\n]+|alleged\s+contemnor[^\n\.]+complied[^\n\.]+|complied\s+with[^.\n]+)", follow_up_text, re.I)
        quote = m.group(0) if m else "recording compliance"
        strength = determine_evidence_strength(quote, follow_up_text)
        return {
            "verdict": "COMPLIANCE_SHOWN",
            "evidence_strength": strength,
            "supporting_quote": quote,
            "reasoning": "Order records compliance.",
            "method": "heuristic",
        }

    if "dismissed for default" in norm or "none appears" in norm or "nobody appears" in norm:
        m = re.search(r"(?:dismissed\s+for\s+default|none\s+appears[^\n\.]+|nobody\s+appears[^\n\.]+)", follow_up_text, re.I)
        quote = m.group(0) if m else "dismissed for default"
        return {
            "verdict": "DISMISSED_FOR_DEFAULT",
            "evidence_strength": None,
            "supporting_quote": quote,
            "reasoning": "Contempt application dismissed due to absence of parties; not evidence of compliance.",
            "method": "heuristic",
        }

    if "extension of time" in norm or "prays for time" in norm:
        m = re.search(r"(?:prays\s+for\s+(?:further\s+)?time|extension\s+of\s+time)", follow_up_text, re.I)
        quote = m.group(0) if m else "extension of time"
        return {
            "verdict": "EXTENSION_SOUGHT",
            "evidence_strength": None,
            "supporting_quote": quote,
            "reasoning": "Extension of time sought by contemnors.",
            "method": "heuristic",
        }

    if "rule be issued" in norm or "notice be issued" in norm:
        m = re.search(r"(?:rule\s+be\s+issued|notice\s+be\s+issued)", follow_up_text, re.I)
        quote = m.group(0) if m else "rule be issued"
        return {
            "verdict": "NOTICE_ISSUED",
            "evidence_strength": None,
            "supporting_quote": quote,
            "reasoning": "Contempt rule or notice issued.",
            "method": "heuristic",
        }

    if "alleging violation" in norm or "alleging wilful violation" in norm or "alleged violation" in norm:
        m = re.search(r"(?:alleging\s+(?:wilful\s+)?violation[^.\n]+|alleged\s+violation[^.\n]+)", follow_up_text, re.I)
        quote = m.group(0) if m else "alleging violation"
        return {
            "verdict": "NON_COMPLIANCE_ALLEGED",
            "evidence_strength": None,
            "supporting_quote": quote,
            "reasoning": "Contempt filed alleging non-compliance.",
            "method": "heuristic",
        }

    return {
        "verdict": "DISPOSED_NO_FINDING",
        "evidence_strength": None,
        "supporting_quote": follow_up_text[:100].strip(),
        "reasoning": "Follow-up order disposed of without explicit compliance finding.",
        "method": "heuristic",
    }


def classify_follow_up_with_gemini(
    direction: Direction,
    later_judgment: Judgment,
    db: Session,
) -> Dict[str, Any]:
    """Classify the later order outcome using Gemini with cache and verbatim verification."""
    model_name = settings.GEMINI_MODEL
    user_prompt = f"""ORIGINAL DIRECTION (Judgment ID {direction.judgment_id}):
- Responsible Party: {direction.responsible_party}
- Action: {direction.action}
- Deadline: {direction.deadline_phrase or 'None specified'}
- Original Quote: {direction.source_quote}

LATER FOLLOW-UP ORDER (Case: {later_judgment.case_number}, Date: {later_judgment.judgment_date}):
{later_judgment.text}
"""

    cache_key = build_cache_key(model_name, direction.id, later_judgment.id, user_prompt)

    # Check cache
    cached = db.query(LLMCache).filter(LLMCache.cache_key == cache_key).first()
    if cached:
        try:
            data = json.loads(cached.response_json)
            data["method"] = "cached"
            data["model_used"] = model_name
            return data
        except Exception:
            pass

    # Call Gemini
    if not settings.GEMINI_API_KEY:
        res = classify_follow_up_order_heuristic(later_judgment.text or "")
        res["model_used"] = "none"
        return res

    try:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Attempt 1
        full_content = f"{FOLLOW_UP_SYSTEM_PROMPT}\n\n{user_prompt}"
        response = client.models.generate_content(
            model=model_name,
            contents=full_content,
            config={"response_mime_type": "application/json"},
        )
        resp_text = response.text.strip()
        data = json.loads(resp_text)

        # Verifier on quote
        quote = data.get("supporting_quote", "")
        if not verify_follow_up_quote(quote, later_judgment.text or ""):
            # Retry once with feedback
            logger.warning(f"Quote verification failed for Dir {direction.id}: '{quote[:50]}...'. Retrying with feedback.")
            retry_prompt = (
                f"{full_content}\n\n"
                f"ERROR: Your previous supporting_quote was not found verbatim in the later order text: '{quote}'.\n"
                f"Extract ONLY an exact, verbatim substring from the LATER FOLLOW-UP ORDER text above."
            )
            response2 = client.models.generate_content(
                model=model_name,
                contents=retry_prompt,
                config={"response_mime_type": "application/json"},
            )
            data = json.loads(response2.text.strip())
            quote2 = data.get("supporting_quote", "")
            if not verify_follow_up_quote(quote2, later_judgment.text or ""):
                # Verifier failed after retry -> Fall back to UNRELATED
                logger.error(f"Quote verification failed after retry for Dir {direction.id}. Falling back to UNRELATED.")
                data["verdict"] = "UNRELATED"
                data["reasoning"] = f"Supporting quote verification failed after retry. Rejected quote: '{quote2[:50]}...'"
                data["supporting_quote"] = ""
                data["verified"] = False
            else:
                data["verified"] = True
        else:
            data["verified"] = True

        data["method"] = "gemini"
        data["model_used"] = model_name

        # Cache response
        llm_entry = LLMCache(
            cache_key=cache_key,
            prompt_hash=hashlib.sha256(user_prompt.encode()).hexdigest(),
            model_name=model_name,
            response_json=json.dumps(data),
        )
        db.merge(llm_entry)
        db.commit()

        return data

    except Exception as exc:
        logger.warning(f"Gemini call failed for follow-up classification: {exc}. Using deterministic fallback.")
        res = classify_follow_up_order_heuristic(later_judgment.text or "")
        res["model_used"] = model_name
        res["method"] = "fallback"
        res["verified"] = verify_follow_up_quote(res.get("supporting_quote", ""), later_judgment.text or "")
        return res


def link_later_judgments_to_earlier_directions(db: Session) -> Dict[str, Any]:
    """Execute end-to-end linking and evidence generation over all database judgments.
    
    Signals in priority order:
    1. Contempt header citation (e.g. CPAN in WPA) -> HIGH confidence
    2. Same CNR -> HIGH confidence
    3. Same case number on different date -> MEDIUM confidence
    4. Fuzzy party name match -> LOW confidence
    """
    start_t = time.perf_counter()
    judgments = db.query(Judgment).filter(Judgment.status == "INGESTED").all()
    j_by_id = {j.id: j for j in judgments}

    # Index judgments by normalized case number
    j_by_case: Dict[str, List[Judgment]] = {}
    j_by_cnr: Dict[str, List[Judgment]] = {}
    for j in judgments:
        norm = normalize_case_citation(j.case_number)
        if norm:
            j_by_case.setdefault(norm, []).append(j)
        if j.cnr:
            j_by_cnr.setdefault(j.cnr.strip(), []).append(j)

    discovered_links: List[Dict[str, Any]] = []
    seen_pairs = set()

    for later_j in judgments:
        text = later_j.text or ""
        citations = extract_header_citations(text, later_j.case_number)

        # -------------------------------------------------------------
        # SIGNAL A: Contempt header citation (Highest Priority)
        # -------------------------------------------------------------
        for raw_cit, norm_cit in citations:
            target_list = j_by_case.get(norm_cit, [])
            for orig_j in target_list:
                if orig_j.id == later_j.id:
                    continue
                pair_key = (orig_j.id, later_j.id, "contempt_citation")
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                is_valid_time, time_reason = check_temporal_sanity(
                    orig_j.judgment_date, later_j.judgment_date, orig_j.case_number, later_j.case_number
                )

                link_type = "CONTEMPT_FILED"
                conf = "HIGH" if is_valid_time else "LOW"
                note = (
                    f"Cites {raw_cit} in header."
                    if is_valid_time
                    else f"Cites {raw_cit} in header. {time_reason}"
                )

                discovered_links.append({
                    "from_judgment_id": orig_j.id,
                    "to_judgment_id": later_j.id,
                    "link_type": link_type,
                    "link_signal": "contempt_citation",
                    "link_confidence": conf,
                    "note": note,
                    "is_temporally_valid": is_valid_time,
                    "time_reason": time_reason,
                    "citation_text": raw_cit,
                })

        # -------------------------------------------------------------
        # SIGNAL B: Same CNR
        # -------------------------------------------------------------
        if later_j.cnr and later_j.cnr.strip() in j_by_cnr:
            for orig_j in j_by_cnr[later_j.cnr.strip()]:
                if orig_j.id == later_j.id:
                    continue
                # Temporal order: orig_j must be earlier
                if orig_j.judgment_date and later_j.judgment_date and orig_j.judgment_date > later_j.judgment_date:
                    continue
                pair_key = (orig_j.id, later_j.id, "same_cnr")
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                is_valid_time, time_reason = check_temporal_sanity(
                    orig_j.judgment_date, later_j.judgment_date, orig_j.case_number, later_j.case_number
                )
                conf = "HIGH" if is_valid_time else "LOW"

                discovered_links.append({
                    "from_judgment_id": orig_j.id,
                    "to_judgment_id": later_j.id,
                    "link_type": "OTHER",
                    "link_signal": "same_cnr",
                    "link_confidence": conf,
                    "note": f"Identical CNR {later_j.cnr}.",
                    "is_temporally_valid": is_valid_time,
                    "time_reason": time_reason,
                    "citation_text": later_j.cnr,
                })

        # -------------------------------------------------------------
        # SIGNAL C: Same case number on different date
        # -------------------------------------------------------------
        norm_case = normalize_case_citation(later_j.case_number)
        if norm_case and norm_case in j_by_case:
            for orig_j in j_by_case[norm_case]:
                if orig_j.id == later_j.id:
                    continue
                if orig_j.judgment_date and later_j.judgment_date and orig_j.judgment_date >= later_j.judgment_date:
                    continue
                pair_key = (orig_j.id, later_j.id, "same_case_number")
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                discovered_links.append({
                    "from_judgment_id": orig_j.id,
                    "to_judgment_id": later_j.id,
                    "link_type": "OTHER",
                    "link_signal": "same_case_number",
                    "link_confidence": "HIGH",
                    "note": f"Subsequent order in same case {norm_case}.",
                    "is_temporally_valid": True,
                    "time_reason": None,
                    "citation_text": norm_case,
                })

    # Persist CaseLinks
    saved_links = []
    for lk in discovered_links:
        existing = db.query(CaseLink).filter(
            CaseLink.from_judgment_id == lk["from_judgment_id"],
            CaseLink.to_judgment_id == lk["to_judgment_id"],
            CaseLink.link_signal == lk["link_signal"],
        ).first()

        if not existing:
            rec = CaseLink(
                from_judgment_id=lk["from_judgment_id"],
                to_judgment_id=lk["to_judgment_id"],
                primary_judgment_id=lk["from_judgment_id"],
                linked_judgment_id=lk["to_judgment_id"],
                link_type=lk["link_type"],
                link_signal=lk["link_signal"],
                link_confidence=lk["link_confidence"],
                note=lk["note"],
                citation_text=lk.get("citation_text"),
                model_used=settings.GEMINI_MODEL,
                method="deterministic",
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            saved_links.append(rec)
        else:
            existing.link_confidence = lk["link_confidence"]
            existing.note = lk["note"]
            db.commit()
            saved_links.append(existing)

    duration = time.perf_counter() - start_t
    logger.info(f"Link discovery complete in {duration:.3f}s: {len(discovered_links)} links identified.")

    return {
        "total_links": len(discovered_links),
        "links": discovered_links,
        "duration_seconds": round(duration, 3),
    }


def run_full_linking_and_status_pipeline(db: Session) -> Dict[str, Any]:
    """Execute end-to-end follow-up linking, evidence classification, and status resolution."""
    from backend.pipeline.status import update_all_direction_statuses

    total_start = time.perf_counter()

    # Step 1: Discover links
    link_results = link_later_judgments_to_earlier_directions(db)

    # Step 2: Classify follow-up orders and generate Evidence for linked directions
    links = db.query(CaseLink).all()
    evidence_created = 0
    verdict_counts: Dict[str, int] = {}

    for lk in links:
        from_jid = lk.from_judgment_id or lk.primary_judgment_id
        to_jid = lk.to_judgment_id or lk.linked_judgment_id
        if not from_jid or not to_jid:
            continue

        later_j = db.query(Judgment).filter(Judgment.id == to_jid).first()
        if not later_j:
            continue

        # Directions of earlier order
        directions = db.query(Direction).filter(Direction.judgment_id == from_jid).all()
        for d in directions:
            # Check existing evidence
            existing_ev = db.query(Evidence).filter(
                Evidence.direction_id == d.id,
                Evidence.source_judgment_id == to_jid,
            ).first()

            if existing_ev:
                verdict_counts[existing_ev.verdict] = verdict_counts.get(existing_ev.verdict, 0) + 1
                continue

            # Classify using Gemini (or fallback) with verbatim verification
            v_res = classify_follow_up_with_gemini(d, later_j, db)
            verdict = v_res.get("verdict", "UNRELATED")
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

            ev = Evidence(
                direction_id=d.id,
                supporting_quote=v_res.get("supporting_quote"),
                source_judgment_id=to_jid,
                source_case_number=later_j.case_number,
                source_date=later_j.judgment_date,
                verdict=verdict,
                reasoning=v_res.get("reasoning"),
                verified=v_res.get("verified", False),
                model_used=v_res.get("model_used"),
                method=v_res.get("method", "gemini"),
            )
            db.add(ev)
            db.commit()
            evidence_created += 1

    # Step 3: Run deterministic status engine
    status_results = update_all_direction_statuses(db)

    total_duration = time.perf_counter() - total_start

    return {
        "status": "COMPLETED",
        "total_duration_seconds": round(total_duration, 3),
        "links": link_results,
        "evidence_created": evidence_created,
        "verdict_distribution": verdict_counts,
        "status_engine": status_results,
    }

