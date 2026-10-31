"""Phase 3 Acceptance Runner: Deterministic Deadline Resolution.

Role: Resolves all direction deadlines in SQLite compliance_radar.db using
      deterministic regex rules and dateutil window math, stores the results on Direction records,
      and prints 10 real directions with phrase -> window -> explanation.
Data flow: SQLite judgments & directions -> backend.pipeline.deadline -> SQLite directions updated -> CLI output.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.database import SessionLocal
from backend.app.models import Direction, Judgment
from backend.pipeline.deadline import resolve_all_directions, SERVICE_LAG_DAYS


def main():
    db = SessionLocal()
    try:
        print("=" * 70)
        print("=== PHASE 3: DETERMINISTIC DEADLINE RESOLUTION ACCEPTANCE RUN ===")
        print("=" * 70)
        print(f"Configured SERVICE_LAG_DAYS: {SERVICE_LAG_DAYS} days")

        # Resolve and update all directions in SQLite DB
        updated_count = resolve_all_directions(db, service_lag_days=SERVICE_LAG_DAYS)
        print(f"Successfully resolved and updated {updated_count} direction records in database.\n")

        # Query all directions joined with judgment metadata
        directions = (
            db.query(Direction)
            .join(Judgment, Direction.judgment_id == Judgment.id)
            .order_by(Direction.id.asc())
            .all()
        )

        # Print summary breakdown
        anchor_counts = {}
        status_counts = {}
        estimated_count = 0

        for d in directions:
            anchor = d.anchor_type or "none"
            anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1

            status = d.deadline_status or "NO_DEADLINE"
            status_counts[status] = status_counts.get(status, 0) + 1

            if d.is_estimated:
                estimated_count += 1

        print("--- RESOLUTION METRICS BREAKDOWN ---")
        print(f"Total Directions: {len(directions)}")
        print(f"Estimated Windows (Receipt/Communication): {estimated_count}")
        print(f"Anchor Type Distribution: {anchor_counts}")
        print(f"Status Bucket Distribution: {status_counts}")

        print("\n" + "=" * 70)
        print("=== 10 REAL DIRECTIONS: PHRASE -> WINDOW -> EXPLANATION ===")
        print("=" * 70)

        # Select 10 directions (prioritize diverse phrases with deadlines, followed by immediate/no-deadline)
        with_phrase = [d for d in directions if d.deadline_phrase is not None]
        without_phrase = [d for d in directions if d.deadline_phrase is None]
        sample_dirs = (with_phrase + without_phrase)[:10]

        for idx, d in enumerate(sample_dirs, 1):
            j = d.judgment
            clean_phrase = " ".join(d.deadline_phrase.split()) if d.deadline_phrase else "[NO DEADLINE SPECIFIED]"
            
            if d.deadline_window_start and d.deadline_window_end:
                window_str = f"[{d.deadline_window_start.isoformat()} to {d.deadline_window_end.isoformat()}]"
            elif d.deadline_window_start and not d.deadline_window_end:
                window_str = f"[{d.deadline_window_start.isoformat()} to OPEN/IMMEDIATE]"
            else:
                window_str = "[NONE]"

            print(f"\n[{idx:02d}/10] Direction ID: {d.id} | Judgment ID: {d.judgment_id} ({j.case_number if j else 'N/A'}, Pronounced: {j.judgment_date if j else 'N/A'})")
            print(f"  Party: {d.responsible_party} ({d.party_type})")
            print(f"  Action: {d.action[:100]}...")
            print(f"  Phrase: \"{clean_phrase}\"")
            print(f"  Anchor Type: {d.anchor_type} | Estimated: {d.is_estimated}")
            print(f"  Window: {window_str}")
            print(f"  Status: {d.deadline_status}")
            print(f"  Explanation: {d.explanation_text}")

        print("\n" + "=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()

