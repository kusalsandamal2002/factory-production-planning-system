from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_session
from app.services.ai_planning_service import AIPlanningService
from app.services.factory_intelligence_service import FactoryIntelligenceService


def main() -> int:
    with get_session() as session:
        AIPlanningService().ensure_schema(session)
        FactoryIntelligenceService.ensure_schema(session)
    print("MPPS Factory Intelligence V10 schema: READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
