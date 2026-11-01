"""Deterministic department name cleaner and normalization module.

Role: Cleans raw responsible party strings extracted from judgments by stripping articles,
      honorifics, counsel qualifiers, and normalising state and departmental department titles
      into canonical department categories while preserving the original string for tooltips.
Data flow: Raw Direction.responsible_party -> clean_department_name() -> Cleaned canonical department.
"""

import re
from typing import Optional


HONORIFICS_PATTERN = re.compile(
    r"^(?:the\s+|learned\s+|alleged\s+|aforesaid\s+|concerned\s+|mr\.?\s+|mrs\.?\s+|ms\.?\s+|dr\.?\s+|shri\s+|sri\s+|smt\.?\s+|hon(?:'|\b)ble\s+|justice\s+)+",
    re.IGNORECASE,
)


def clean_department_name(party_raw: Optional[str]) -> str:
    """Deterministically clean and canonicalise a responsible party or department string.
    
    Examples:
        'The Director of Pension, Provident Fund & Group Insurance, Government of West Bengal...'
        -> 'Director of Pension, Provident Fund & Group Insurance'
        
        'District Inspector of Schools (SE), Malda'
        -> 'District Inspector of Schools (SE)'
        
        'Superintendent of Police, Ranaghat Police District'
        -> 'Superintendent of Police'
        
        'State of West Bengal through Principal Secretary...'
        -> 'State of West Bengal'
    """
    if not party_raw or not isinstance(party_raw, str):
        return "Unspecified Authority"

    text = party_raw.strip()
    if not text:
        return "Unspecified Authority"

    # 1. Strip leading articles, honorifics, and qualifiers iteratively
    prev = ""
    while text != prev:
        prev = text
        text = HONORIFICS_PATTERN.sub("", text).strip()

    # 2. Canonical department normalisation patterns
    lower = text.lower()

    if "state of west bengal" in lower or lower.startswith("west bengal state"):
        return "State of West Bengal"

    if "director of pension" in lower or "provident fund" in lower:
        return "Director of Pension, Provident Fund & Group Insurance"

    if "commissioner of school education" in lower:
        return "Commissioner of School Education"

    if "district inspector of school" in lower or "d.i. of school" in lower or "d.i." in lower:
        if "(pe)" in lower or "(p.e.)" in lower or "primary" in lower:
            return "District Inspector of Schools (PE)"
        return "District Inspector of Schools (SE)"

    if "superintendent of police" in lower:
        return "Superintendent of Police"

    if "chief judicial magistrate" in lower:
        return "Chief Judicial Magistrate"

    if "public works department" in lower or "pwd" in lower:
        return "Public Works Department"

    if "cesc" in lower:
        return "CESC Limited"

    if "durgapur projects" in lower or "dpl" in lower:
        return "Durgapur Projects Limited"

    if "block development officer" in lower or "bdo" in lower:
        return "Block Development Officer"

    if "treasury officer" in lower:
        return "Treasury Officer"

    if "trial court" in lower or "court below" in lower:
        return "Trial Court"

    if "police station" in lower or "officer-in-charge" in lower or lower.startswith("o. c.") or lower.startswith("i. c."):
        # If specific police station like 'Baduria Police Station', extract station name
        m_ps = re.search(r"([A-Za-z\s]+Police Station)", text, re.IGNORECASE)
        if m_ps:
            return m_ps.group(1).strip()
        m_oc = re.search(r"(?:Officer-in-Charge|O\.\s*C\.|I\.\s*C\.)[,\s]+([A-Za-z\s]+)", text, re.IGNORECASE)
        if m_oc:
            return f"Officer-in-Charge, {m_oc.group(1).strip()}"
        return "Police Authority"

    if "municipality" in lower or "municipal corporation" in lower:
        m_mun = re.search(r"([A-Za-z\s\-]+(?:Municipality|Municipal Corporation))", text, re.IGNORECASE)
        if m_mun:
            return m_mun.group(1).strip()
        return "Municipal Authority"

    if "panchayat samiti" in lower or "gram panchayat" in lower:
        m_pan = re.search(r"([A-Za-z\s\-]+(?:Panchayat Samiti|Gram Panchayat))", text, re.IGNORECASE)
        if m_pan:
            return m_pan.group(1).strip()
        return "Panchayat Authority"

    if "advocate" in lower or "learned counsel" in lower:
        if "petitioner" in lower:
            return "Advocate for Petitioner"
        return "Learned Advocate"

    if lower in ("petitioner", "petitioners", "appellant", "applicant"):
        return "Petitioner"

    if lower in ("respondent", "respondents", "respondent no. 2", "respondent authorities", "respondent authority"):
        return "Respondent Authority"

    # Clean up trailing punctuation, commas, or conjunctions
    cleaned = re.sub(r"[\s,\-\–]+$", "", text).strip()
    # If string is entirely lowercase, capitalize title-style
    if cleaned.islower():
        cleaned = cleaned.title()

    return cleaned or "Unspecified Authority"

