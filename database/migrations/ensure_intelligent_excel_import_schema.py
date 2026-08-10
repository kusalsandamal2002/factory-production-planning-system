from __future__ import annotations

from app.database import get_session
from app.services.intelligent_excel_import_service import IntelligentExcelImportService


def main() -> int:
    with get_session() as session:
        IntelligentExcelImportService.ensure_schema(session)
    print("INTELLIGENT EXCEL IMPORT DATABASE SCHEMA READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
