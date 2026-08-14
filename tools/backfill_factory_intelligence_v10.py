from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import tempfile
import zipfile

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import get_session
from app.services.ai_planning_service import AIPlanningService
from app.services.factory_intelligence_service import FactoryIntelligenceService
from app.services.intelligent_excel_import_service import IntelligentExcelImportService




def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def _files_from_source(source: Path) -> tuple[list[Path], tempfile.TemporaryDirectory | None]:
    temp: tempfile.TemporaryDirectory | None = None
    if source.is_file() and source.suffix.lower() == '.zip':
        temp = tempfile.TemporaryDirectory(prefix='mpps_v10_backfill_')
        with zipfile.ZipFile(source) as zf:
            zf.extractall(temp.name)
        root = Path(temp.name)
        files = [p for p in root.rglob('*') if p.suffix.lower() in {'.xlsx', '.xlsm'} and not p.name.startswith('~$')]
        return sorted(files), temp
    if source.is_dir():
        files = [p for p in source.rglob('*') if p.suffix.lower() in {'.xlsx', '.xlsm'} and not p.name.startswith('~$')]
        return sorted(files), None
    if source.is_file() and source.suffix.lower() in {'.xlsx', '.xlsm'}:
        return [source], None
    return [], None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            'Bulk backfill historical OVEN workbooks into MPPS V10 Factory Intelligence. '
            'Historical files never move live operational truth backwards.'
        )
    )
    parser.add_argument('source', help='Folder, ZIP, .xlsx or .xlsm source')
    parser.add_argument('--dry-run', action='store_true', help='Analyze only; do not commit')
    parser.add_argument('--stop-on-error', action='store_true')
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    files, temp = _files_from_source(source)
    if not files:
        print(f'No OVEN workbooks found in: {source}')
        return 2

    importer = IntelligentExcelImportService(PROJECT_ROOT)
    success = 0
    skipped = 0
    failed = 0
    print(f'Found {len(files):,} workbook(s). Historical backfill mode is enforced.')

    # Load exact workbook hashes already committed.  A multi-year archive often
    # contains renamed/copy duplicates; skipping them before Excel analysis saves
    # substantial time and avoids duplicate training evidence.
    committed_hashes: set[str] = set()
    if not args.dry_run:
        try:
            with get_session() as session:
                importer.ensure_schema(session)
                committed_hashes = {
                    str(v) for v in session.execute(
                        text(
                            """
                            SELECT DISTINCT workbook_hash
                            FROM excel_import_runs
                            WHERE status IN ('COMMITTED','COMMITTED WITH WARNINGS')
                              AND rollback_at IS NULL
                            """
                        )
                    ).scalars().all() if v
                }
        except Exception as exc:
            print(f'Warning: could not pre-load committed hashes: {exc}')

    try:
        for index, path in enumerate(files, start=1):
            print(f'[{index}/{len(files)}] {path.name}')
            try:
                file_hash = _sha256_file(path)
                if file_hash in committed_hashes:
                    print('  SKIP exact duplicate already committed (SHA-256 match).')
                    skipped += 1
                    continue
                analysis = importer.analyze(
                    path,
                    progress=lambda pct, msg: print(f'  {pct:3d}% {msg}') if pct in {2, 38, 50, 58, 82, 96, 100} else None,
                )
                print(f"  Plan date: {analysis.plan_date or '-'} | confidence: {analysis.confidence_score*100:.1f}%")
                if args.dry_run:
                    success += 1
                    continue
                result = importer.commit(
                    analysis,
                    options={
                        'force_historical_snapshot': True,
                        'force_live_revision': False,
                        'sync_live_shipments': False,
                        'update_stock': False,
                        'update_daily_stock': False,
                        'update_blank_weights': False,
                        'overwrite_existing_weights': False,
                        'import_materials': False,
                        'import_shipment_snapshots': True,
                        'import_oven_plan': True,
                        'import_production_history': True,
                        'capture_learning_observations': True,
                        'rebuild_learning_models': False,
                    },
                    imported_by='V10 Historical Backfill',
                    progress=lambda pct, msg: print(f'  COMMIT {pct:3d}% {msg}') if pct in {2, 18, 38, 53, 82, 86, 96, 100} else None,
                )
                print(f"  committed run #{result.get('run_id')} as {result.get('shipment_sync', {}).get('sync_mode', 'HISTORICAL')}")
                committed_hashes.add(file_hash)
                success += 1
            except Exception as exc:
                message = str(exc)
                if 'already committed as import run' in message.lower():
                    print(f'  SKIP duplicate: {message}')
                    skipped += 1
                    continue
                print(f'  ERROR: {type(exc).__name__}: {exc}')
                failed += 1
                if args.stop_on_error:
                    break

        if not args.dry_run and success:
            print('Rebuilding V10 AI + capacity + human-planner policy models once after bulk ingestion...')
            with get_session() as session:
                ai = AIPlanningService()
                fi = FactoryIntelligenceService()
                ai.ensure_schema(session)
                fi.ensure_schema(session)
                result = {}
                result.update(ai.reconcile_plan_vs_actual(session))
                result.update(ai.train_models(session))
                result.update(fi.train_capacity_models(session))
                result.update(fi.train_planner_policy(session))
                result.update(ai.evaluate_ai_runs(session))
                result.update(fi.refresh_state(session))
                print('MODEL RESULT:', result)
    finally:
        if temp is not None:
            temp.cleanup()

    print(f'DONE: success={success}, skipped={skipped}, failed={failed}')
    print('Live OVEN authority was not moved backwards by historical backfill.')
    print('For overlapping actual-production dates, evidence from the newest workbook plan-date wins regardless of file/import order.')
    return 1 if failed and args.stop_on_error else 0


if __name__ == '__main__':
    raise SystemExit(main())
