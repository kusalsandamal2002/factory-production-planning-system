from sqlalchemy import text

from app.database import engine
from app.services.operational_source_service import OperationalSourceService


def _safe_first(connection, sql):
    try:
        return connection.execute(text(sql)).mappings().first()
    except Exception as exc:
        return {'error': str(exc)}


def main():
    with engine.begin() as connection:
        source = OperationalSourceService.latest(connection)
        latest_import = _safe_first(
            connection,
            """
            SELECT id, plan_date, workbook_name, status
            FROM excel_import_runs
            WHERE rollback_at IS NULL AND plan_date IS NOT NULL
            ORDER BY plan_date DESC, id DESC LIMIT 1
            """,
        )
        latest_live_sync = _safe_first(
            connection,
            """
            SELECT id, import_run_id, plan_date, workbook_name, sync_mode, status
            FROM excel_shipment_sync_runs
            WHERE rollback_at IS NULL AND sync_mode='LIVE'
            ORDER BY plan_date DESC, id DESC LIMIT 1
            """,
        )

    print('MPPS SHIPMENT COMMAND CENTER V10.2 HEALTH CHECK: PASS')
    print('Operational plan date :', source.plan_date or '-')
    print('Operational authority :', source.authority)
    print('Sync confirmed        :', source.sync_confirmed)
    print('Workbook              :', source.workbook_name or '-')
    print('Import run            :', source.import_run_id or '-')
    print('Sync run              :', source.sync_run_id or '-')
    print('Confidence            :', f'{source.confidence_pct:.1f}%')
    print('Latest import row     :', dict(latest_import or {}))
    print('Latest LIVE sync row  :', dict(latest_live_sync or {}))


if __name__ == '__main__':
    main()
