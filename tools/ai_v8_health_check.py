from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.database import get_session
from app.services.ai_planning_service import AIPlanningService


def main() -> int:
    ai = AIPlanningService()
    with get_session() as session:
        ai.ensure_schema(session)
        readiness = ai.get_readiness(session)
        counts = {}
        for name in (
            "mpps_final_plan_history",
            "mpps_actual_production",
            "mpps_plan_actual_reconciliation",
            "mpps_ai_model_state",
            "mpps_ai_plan_runs",
            "mpps_ai_plan_items",
            "mpps_ai_plan_evaluation",
        ):
            counts[name] = int(session.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar() or 0)

    print("MPPS AI V8 HEALTH CHECK: PASS")
    print(f"Control mode: {readiness.mode}")
    print(f"Forward validated days: {readiness.validation_days}")
    print(f"Validation accuracy: {readiness.accuracy_pct:.2f}% ({readiness.accuracy_basis})")
    print(f"Actual-data coverage: {readiness.coverage_pct:.2f}%")
    print(f"High-confidence models: {readiness.high_confidence_items}/{readiness.total_models}")
    print(f"Eligible for supervised auto handover: {readiness.eligible_for_supervised_auto}")
    for name, value in counts.items():
        print(f"{name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
