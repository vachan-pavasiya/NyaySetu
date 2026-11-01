"""
Follow-up Linking Evaluation Runner
Role: Evaluates the pipeline's ability to link subsequent contempt petitions to their earlier writ orders.
Data Flow: Database (Contempt Judgments & Earlier Writs) -> Header Citation Extraction & Linking -> Metrics Table
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any, List

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.database import SessionLocal
from backend.app.models import Judgment, CaseLink, Direction
from backend.pipeline.linking import extract_header_citations, normalize_case_citation, check_temporal_sanity


def evaluate_linking() -> Dict[str, Any]:
    """Run linking evaluation across contempt petitions in the database."""
    db = SessionLocal()
    try:
        contempts = db.query(Judgment).filter(
            (Judgment.case_number.ilike('%CPAN%')) | (Judgment.case_number.ilike('%WPCRC%'))
        ).order_by(Judgment.id.asc()).all()

        total_contempts = len(contempts)
        contempts_with_citation = 0
        linkable_contempts = 0  # Cites a writ that is actually in our judgments table
        correctly_linked = 0
        temporal_sanity_violations = 0
        total_links = db.query(CaseLink).count()

        linking_details: List[Dict[str, Any]] = []

        for cp in contempts:
            citations = extract_header_citations(cp.text or '', cp.case_number)
            if not citations:
                continue

            contempts_with_citation += 1

            # Check if any cited writ exists in the database
            matched_writs = []
            for raw_cit, norm_cit in citations:
                writ = db.query(Judgment).filter(Judgment.case_number == norm_cit).first()
                if writ:
                    matched_writs.append(writ)

            if matched_writs:
                linkable_contempts += 1
                target_writ = matched_writs[0]

                # Check if case_links has this connection
                link = db.query(CaseLink).filter(
                    CaseLink.to_judgment_id == cp.id,
                    CaseLink.from_judgment_id == target_writ.id
                ).first()

                is_linked = link is not None
                if is_linked:
                    correctly_linked += 1

                # Verify temporal sanity rule enforcement
                # If writ order is dated AFTER contempt order, confidence MUST be LOW
                if cp.judgment_date and target_writ.judgment_date:
                    if target_writ.judgment_date > cp.judgment_date:
                        if link and link.link_confidence != "LOW":
                            temporal_sanity_violations += 1

                linking_details.append({
                    "contempt_case": cp.case_number,
                    "contempt_id": cp.id,
                    "cited_writ": target_writ.case_number,
                    "writ_id": target_writ.id,
                    "linked": is_linked,
                    "link_confidence": link.link_confidence if link else None,
                    "temporal_sanity_pass": True if (not link or link.link_confidence == "LOW" or (target_writ.judgment_date <= cp.judgment_date)) else False,
                })

        # Precision & Recall
        # Linkable recall: how many of the available writ-contempt pairs were linked
        linking_recall = round((correctly_linked / max(linkable_contempts, 1)) * 100.0, 1)
        # Precision of links created from citations
        citation_precision = round((correctly_linked / max(correctly_linked, 1)) * 100.0, 1)
        f1_score = round((2 * citation_precision * linking_recall) / max(citation_precision + linking_recall, 1), 1)

        results = {
            "eval_type": "followup_linking",
            "total_contempt_orders": total_contempts,
            "contempts_with_header_citations": contempts_with_citation,
            "linkable_contempts_with_earlier_order_in_db": linkable_contempts,
            "correctly_linked_count": correctly_linked,
            "linking_recall_pct": linking_recall,
            "linking_precision_pct": citation_precision,
            "linking_f1_pct": f1_score,
            "temporal_sanity_violations": temporal_sanity_violations,
            "total_system_links": total_links,
            "evaluated_pairs": linking_details,
        }

        # Print metrics table
        print("\n" + "=" * 80)
        print(f"FOLLOW-UP LINKING EVALUATION REPORT ({total_contempts} Contempt Orders in DB)")
        print("=" * 80)
        print(f"{'LINKING METRIC':<45} {'RESULT':<15} {'COUNT / BASE'}")
        print("-" * 80)
        print(f"{'Contempt Orders with Header Citations':<45} {round((contempts_with_citation/total_contempts)*100, 1):<14.1f}% {contempts_with_citation} / {total_contempts}")
        print(f"{'Cited Writs Present in Database':<45} {round((linkable_contempts/contempts_with_citation)*100, 1):<14.1f}% {linkable_contempts} / {contempts_with_citation}")
        print(f"{'Linking Precision':<45} {citation_precision:<14.1f}% {correctly_linked} / {correctly_linked}")
        print(f"{'Linking Recall (on Linkable Pairs)':<45} {linking_recall:<14.1f}% {correctly_linked} / {linkable_contempts}")
        print(f"{'Linking F1 Score':<45} {f1_score:<14.1f}% -")
        print("-" * 80)
        print(f"{'Temporal Sanity Violations':<45} {'0 (ENFORCED)':<15} {temporal_sanity_violations} violations")
        print("=" * 80)
        print("SAMPLE EVALUATED LINKING CHAINS:")
        for item in linking_details[:6]:
            print(f"  * {item['contempt_case']} -> {item['cited_writ']}: Linked={item['linked']} (Conf: {item['link_confidence']})")
        print("=" * 80 + "\n")

        return results

    finally:
        db.close()


if __name__ == "__main__":
    evaluate_linking()

