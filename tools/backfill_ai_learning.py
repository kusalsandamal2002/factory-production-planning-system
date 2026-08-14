from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_session
from app.services.ai_planning_service import AIPlanningService
from app.services.intelligent_excel_import_service import IntelligentExcelImportService


def _stable_backfill_run_id(path: Path) -> int:
    digest = sha256(path.read_bytes()).hexdigest()
    # Negative IDs are intentional: a later normal positive import run always
    # supersedes historical backfill when choosing the final plan revision.
    return -int(digest[:14], 16)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill MPPS AI learning from historical OVEN workbooks without "
            "changing live stock, shipments or the execution plan."
        )
    )
    parser.add_argument("files", nargs="+", help="Historical .xlsx/.xlsm workbooks")
    args = parser.parse_args()

    importer = IntelligentExcelImportService(PROJECT_ROOT)
    ai = AIPlanningService()
    latest_plan_date: date | None = None

    for raw in args.files:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            print(f"SKIP missing: {path}")
            continue
        print(f"ANALYZE: {path.name}")
        analysis = importer.analyze(path, progress=lambda p, m: print(f"  {p:3d}% {m}"))
        run_id = _stable_backfill_run_id(path)
        with get_session() as session:
            ai.ensure_schema(session)
            final_result = ai.capture_final_excel_plan(session, import_run_id=run_id, analysis=analysis)
            actual_result = ai.capture_actual_production(session, import_run_id=run_id, analysis=analysis)
            print("  ", final_result, actual_result)
        if analysis.plan_date:
            parsed = date.fromisoformat(analysis.plan_date)
            latest_plan_date = max(latest_plan_date, parsed) if latest_plan_date else parsed

    with get_session() as session:
        result = {}
        result.update(ai.reconcile_plan_vs_actual(session))
        result.update(ai.train_models(session))
        result.update(ai.evaluate_ai_runs(session))
        if latest_plan_date:
            result.update(ai.generate_candidate_plan(session, plan_date=latest_plan_date + timedelta(days=1)))
            result.update(ai.evaluate_ai_runs(session))
        readiness = ai.get_readiness(session)
    print("DONE:", result)
    print("READINESS:", readiness)
    print("Historical backfill did NOT change live shipments/stock/final execution schedule.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
