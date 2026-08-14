from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.database import get_session
from app.services.ai_planning_service import AIPlanningService
from app.services.factory_intelligence_service import FactoryIntelligenceService
from app.services.operational_source_service import OperationalSourceService


def main() -> int:
    try:
        with get_session() as session:
            ai = AIPlanningService()
            fi = FactoryIntelligenceService()
            ai.ensure_schema(session)
            fi.ensure_schema(session)
            source = OperationalSourceService.latest(session)
            state = fi.refresh_state(session)
            readiness = ai.get_readiness(session)
            month = None
            if source.plan_date:
                month = source.plan_date.strftime('%Y-%m')
            opening = session.execute(text(
                """
                SELECT month_key, source_authority, source_plan_date, file_name, total_rows
                FROM monthly_stock_counts
                WHERE is_active = TRUE
                  AND (:month_key IS NULL OR month_key <= :month_key)
                ORDER BY month_key DESC, uploaded_at DESC LIMIT 1
                """
            ), {'month_key': month}).mappings().first()

        print('MPPS FACTORY INTELLIGENCE V10 HEALTH CHECK: PASS')
        print('Model version:', state.get('model_version'))
        print('Live OVEN date:', state.get('latest_operational_date') or '-')
        print('Historical workbooks:', state.get('workbooks', 0))
        print('Verified actual days:', state.get('actual_days', 0))
        print('Capacity models:', state.get('capacity_models', 0))
        print('Capacity confidence:', f"{state.get('capacity_confidence_pct', 0):.2f}%")
        print('Identity aliases:', state.get('aliases', 0))
        print('Identity reviews:', state.get('unresolved', 0))
        print('AI mode:', readiness.mode)
        print('AI validation days:', readiness.validation_days)
        print('AI validation accuracy:', f'{readiness.accuracy_pct:.2f}%')
        if opening:
            print('Opening stock authority:', opening.get('source_authority'))
            print('Opening stock month:', opening.get('month_key'))
            print('Opening source plan date:', opening.get('source_plan_date'))
            print('Opening source workbook:', opening.get('file_name'))
            print('Opening rows:', opening.get('total_rows'))
        else:
            print('Opening stock authority: not captured yet (import a LIVE OVEN workbook)')
        return 0
    except Exception as exc:
        print('MPPS FACTORY INTELLIGENCE V10 HEALTH CHECK: FAIL')
        print(type(exc).__name__ + ':', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
