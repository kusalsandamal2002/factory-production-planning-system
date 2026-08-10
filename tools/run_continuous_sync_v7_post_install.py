from __future__ import annotations

from datetime import date

from app.database import get_session
from app.services.factory_planning_engine import (
    FactoryPlanningEngine,
)
from app.services.production_learning_service import (
    ProductionLearningService,
)


def main() -> int:
    planning_result = FactoryPlanningEngine(
        start_date=date.today()
    ).replan_all_open_shipments(
        trigger_reason="continuous_excel_sync_ml_v7_0_install",
        created_by="v7_0_installer",
    )

    with get_session() as session:
        learning_result = ProductionLearningService().rebuild_models(
            session
        )

    print("CONTINUOUS EXCEL SYNC V7.0 POST-INSTALL COMPLETED")
    print(f"planning_run_id: {planning_result.planning_run_id}")
    print(
        "active_shipments_planned: "
        f"{len(planning_result.shipments)}"
    )
    print(
        "advisory_models_rebuilt: "
        f"{learning_result.get('models_total', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
