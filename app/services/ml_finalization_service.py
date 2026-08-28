from __future__ import annotations

from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Callable

from sqlalchemy import text

from app.database import engine, get_session
from app.services.current_stock_service import CurrentStockService
from app.services.historical_dataset_validation_service import (
    HistoricalDatasetValidationService,
)
from app.services.intelligent_excel_import_service import IntelligentExcelImportService
from app.services.ml_platform_service import MLPlatformService
from app.services.ml_training_engine import MLTrainingEngine
from app.services.ml_training_orchestrator import MLTrainingOrchestrator
from app.services.planning_authority_service import PlanningAuthorityService


ProgressCallback = Callable[[int, str], None]



def _r74_analyze_historical_worker(project_root: str, workbook_path: str) -> dict[str, Any]:
    """Analyze one historical workbook in an isolated process.

    Historical XLSX parsing is CPU-heavy and openpyxl does not scale a single
    workbook across all CPU cores. R7.4 safely pipelines multiple independent
    workbook analyses while all PostgreSQL commits remain serialized in the
    parent process.
    """
    importer = IntelligentExcelImportService(Path(project_root))
    analysis = importer.analyze(Path(workbook_path))
    return analysis.to_dict(include_rows=True)


@dataclass(frozen=True)
class TrainingWorkspace:
    project_root: Path
    ml_workspace: Path
    historical_inbox: Path
    reports_dir: Path
    models_dir: Path


class MLFinalizationService:
    """R7 final ML ingestion/training workflow.

    The workflow is deliberately conservative:
    - operational PostgreSQL facts remain authoritative;
    - historical workbooks are forced to HISTORICAL mode;
    - exact committed-workbook duplicates are skipped;
    - a same-date changed workbook is retained as a new revision;
    - live stock/shipment/material masters are not moved backwards by history;
    - leakage/time-split/champion gates remain owned by R6 services;
    - label-dependent models remain NOT READY until trustworthy labels exist.
    """

    RELEASE = "R7.4.2-TURBO-AI-DEFER-1"
    PREFERRED_HISTORY_DAYS = 730

    @classmethod
    def workspace(cls) -> TrainingWorkspace:
        root = Path(__file__).resolve().parents[2]
        ml_workspace = Path(
            os.environ.get("MPPS_ML_WORKSPACE") or (root / "ml_workspace")
        )
        inbox = Path(
            os.environ.get("MPPS_HISTORICAL_INBOX")
            or (ml_workspace / "historical_inbox")
        )
        reports = Path(
            os.environ.get("MPPS_REPORTS_DIR") or (root / "reports")
        )
        models = Path(
            os.environ.get("MPPS_MODELS_DIR") or (root / "models")
        )
        for path in (ml_workspace, inbox, reports, models):
            path.mkdir(parents=True, exist_ok=True)
        (models / "challengers").mkdir(parents=True, exist_ok=True)
        (models / "production").mkdir(parents=True, exist_ok=True)
        return TrainingWorkspace(
            project_root=root,
            ml_workspace=ml_workspace,
            historical_inbox=inbox,
            reports_dir=reports,
            models_dir=models,
        )

    @staticmethod
    def _progress(callback: ProgressCallback | None, value: int, message: str) -> None:
        if callback:
            callback(max(0, min(100, int(value))), str(message))

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _table_exists(connection, table_name: str) -> bool:
        return bool(
            connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": f"public.{table_name}"},
            ).scalar()
        )

    @classmethod
    def runtime_status(cls) -> dict[str, Any]:
        packages = {
            "numpy": "numpy",
            "scikit-learn": "sklearn",
            "joblib": "joblib",
            "xgboost": "xgboost",
            "psutil": "psutil",
        }
        result: dict[str, Any] = {
            "python": sys.executable,
            "required_ready": True,
            "packages": {},
            "gpu": {
                "nvidia_smi_available": False,
                "name": "",
                "driver": "",
            },
        }
        for display, module_name in packages.items():
            try:
                module = importlib.import_module(module_name)
                version = str(getattr(module, "__version__", "installed"))
                result["packages"][display] = {
                    "installed": True,
                    "version": version,
                }
            except Exception as exc:
                result["packages"][display] = {
                    "installed": False,
                    "version": "",
                    "error": str(exc),
                }
                if module_name in {"numpy", "sklearn", "joblib"}:
                    result["required_ready"] = False

        nvidia_smi = shutil.which("nvidia-smi")
        if nvidia_smi:
            creationflags = 0x08000000 if os.name == "nt" else 0
            try:
                proc = subprocess.run(
                    [
                        nvidia_smi,
                        "--query-gpu=name,driver_version",
                        "--format=csv,noheader",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                    creationflags=creationflags,
                )
                first = (proc.stdout or "").strip().splitlines()
                if proc.returncode == 0 and first:
                    pieces = [piece.strip() for piece in first[0].split(",", 1)]
                    result["gpu"]["nvidia_smi_available"] = True
                    result["gpu"]["name"] = pieces[0] if pieces else ""
                    result["gpu"]["driver"] = pieces[1] if len(pieces) > 1 else ""
            except Exception as exc:
                result["gpu"]["error"] = str(exc)
        return result

    @classmethod
    def install_ml_runtime(cls, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
        status_before = cls.runtime_status()
        if status_before.get("required_ready"):
            return {
                "attempted": False,
                "success": True,
                "before": status_before,
                "after": status_before,
                "message": "Required ML runtime is already installed.",
            }

        workspace = cls.workspace()
        requirements = workspace.project_root / "requirements-ml-optional.txt"
        if not requirements.exists():
            return {
                "attempted": False,
                "success": False,
                "before": status_before,
                "after": status_before,
                "message": f"ML requirements file is missing: {requirements}",
            }

        cls._progress(progress, 5, "Installing portable ML runtime packages")
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "-r",
            str(requirements),
        ]
        proc = subprocess.run(
            command,
            cwd=str(workspace.project_root),
            check=False,
        )
        importlib.invalidate_caches()
        after = cls.runtime_status()
        return {
            "attempted": True,
            "success": bool(proc.returncode == 0 and after.get("required_ready")),
            "return_code": int(proc.returncode),
            "before": status_before,
            "after": after,
            "message": (
                "Portable ML runtime installed."
                if proc.returncode == 0 and after.get("required_ready")
                else "Portable ML runtime installation did not complete successfully."
            ),
        }

    @classmethod
    def verify_or_rebuild_stock_authority(
        cls,
        *,
        repair: bool = True,
    ) -> dict[str, Any]:
        before = PlanningAuthorityService.load(persist_priority=True)
        before_verification = dict(before.get("stock_verification") or {})
        if before_verification.get("verified"):
            return {
                "verified": True,
                "repaired": False,
                "before": before_verification,
                "after": before_verification,
                "message": "Current stock authority already passes verification.",
            }
        if not repair:
            return {
                "verified": False,
                "repaired": False,
                "before": before_verification,
                "after": before_verification,
                "message": "Stock authority verification failed; repair was not requested.",
            }

        with get_session() as session:
            CurrentStockService.ensure_schema(session)
            source = CurrentStockService._latest_committed_source(session)
            if source is None:
                return {
                    "verified": False,
                    "repaired": False,
                    "before": before_verification,
                    "after": before_verification,
                    "message": "No committed OVEN workbook is available to rebuild Current Stock.",
                }

            source_path = Path(source.source_path)
            actual_hash = cls._sha256_file(source_path)
            expected_hash = str(source.workbook_hash or "").strip().lower()
            if expected_hash and actual_hash.lower() != expected_hash:
                return {
                    "verified": False,
                    "repaired": False,
                    "before": before_verification,
                    "after": before_verification,
                    "source_path": str(source_path),
                    "expected_hash": expected_hash,
                    "actual_hash": actual_hash,
                    "message": "Latest committed workbook hash does not match its archived file; stock rebuild was blocked.",
                }

            rows = CurrentStockService.extract_workbook(source_path)
            if not rows:
                return {
                    "verified": False,
                    "repaired": False,
                    "before": before_verification,
                    "after": before_verification,
                    "source_path": str(source_path),
                    "message": "Latest committed workbook contains no valid Current Stock rows.",
                }

            sap_codes = [str(row.get("sap_code") or "").strip().upper() for row in rows]
            if not sap_codes or len(sap_codes) != len(set(sap_codes)):
                return {
                    "verified": False,
                    "repaired": False,
                    "before": before_verification,
                    "after": before_verification,
                    "source_path": str(source_path),
                    "message": "Current Stock extraction contains duplicate/empty SAP identities; rebuild was blocked.",
                }

            session.execute(
                text(
                    "DELETE FROM mpps_current_stock_snapshots WHERE import_run_id=:run_id"
                ),
                {"run_id": source.import_run_id},
            )
            rebuilt = CurrentStockService.ensure_latest_snapshot(session)
            if rebuilt is None:
                raise RuntimeError("Current Stock snapshot rebuild returned no source.")

            count, duplicates, negative_raw_rows = session.execute(
                text(
                    """
                    SELECT
                        COUNT(*),
                        (SELECT COUNT(*) FROM (
                            SELECT UPPER(TRIM(sap_code))
                            FROM mpps_current_stock_snapshots
                            WHERE import_run_id=:run_id
                            GROUP BY UPPER(TRIM(sap_code))
                            HAVING COUNT(*)>1
                        ) d),
                        COUNT(*) FILTER (WHERE COALESCE(current_stock,0)<0)
                    FROM mpps_current_stock_snapshots
                    WHERE import_run_id=:run_id
                    """
                ),
                {"run_id": source.import_run_id},
            ).one()

            # HR/HS/HT/HU/HV are direct workbook facts. Some committed OVEN
            # workbooks legitimately contain negative HS values. Those raw
            # values must remain preserved for audit/anomaly learning, while
            # PlanningAuthorityService already clamps usable stock to >= 0.
            # Therefore negative raw HS rows are a warning, not source-integrity
            # corruption. Integrity is defined by exact row population and
            # unique SAP identity for the committed workbook.
            if int(count or 0) != len(rows) or int(duplicates or 0) > 0:
                raise RuntimeError(
                    "Rebuilt Current Stock snapshot failed transaction-local integrity checks."
                )

        after = PlanningAuthorityService.load(persist_priority=True)
        after_verification = dict(after.get("stock_verification") or {})
        return {
            "verified": bool(after_verification.get("verified")),
            "repaired": True,
            "before": before_verification,
            "after": after_verification,
            "source_path": str(source_path),
            "source_hash": actual_hash,
            "rebuild_rows": len(rows),
            "negative_raw_rows": int(negative_raw_rows or 0),
            "message": str(after_verification.get("message") or ""),
        }

    @classmethod
    def _committed_hashes(cls) -> dict[str, int]:
        with engine.connect() as connection:
            if not cls._table_exists(connection, "excel_import_runs"):
                return {}
            return {
                str(row[0]).strip().lower(): int(row[1])
                for row in connection.execute(
                    text(
                        """
                        SELECT workbook_hash,MAX(id)
                        FROM excel_import_runs
                        WHERE status LIKE 'COMMITTED%'
                          AND rollback_at IS NULL
                          AND COALESCE(workbook_hash,'')<>''
                        GROUP BY workbook_hash
                        """
                    )
                ).all()
            }

    @classmethod
    def discover_historical_workbooks(cls) -> list[Path]:
        inbox = cls.workspace().historical_inbox
        files = [
            path
            for path in inbox.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".xlsx", ".xlsm"}
            and not path.name.startswith("~$")
        ]
        return sorted(files, key=lambda path: (path.name.lower(), str(path).lower()))

    @classmethod
    def _pause_flag(cls) -> Path:
        workspace = cls.workspace()
        return Path(
            os.environ.get("MPPS_ML_PAUSE_FLAG")
            or (workspace.ml_workspace / "PAUSE_REQUESTED.flag")
        )

    @classmethod
    def _pause_requested(cls) -> bool:
        try:
            return cls._pause_flag().exists()
        except OSError:
            return False

    @classmethod
    def _resume_state_path(cls) -> Path:
        workspace = cls.workspace()
        return Path(
            os.environ.get("MPPS_ML_RESUME_STATE")
            or (workspace.ml_workspace / "R73_resume_state.json")
        )

    @classmethod
    def _load_resume_state(cls) -> dict[str, Any]:
        path = cls._resume_state_path()
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    @classmethod
    def _write_resume_state(cls, **updates: Any) -> None:
        path = cls._resume_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        state = cls._load_resume_state()
        state.update(updates)
        state["updated_at"] = datetime.now().isoformat()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def _rolling_cache_enabled(cls) -> bool:
        return str(os.environ.get("MPPS_NVME_ROLLING_DELETE") or "").strip().lower() in {
            "1", "true", "yes", "on"
        }

    @classmethod
    def _nvme_free_gb(cls) -> float:
        anchor = Path(
            os.environ.get("MPPS_NVME_ROOT")
            or cls.workspace().historical_inbox
        )
        anchor.mkdir(parents=True, exist_ok=True)
        return shutil.disk_usage(anchor).free / (1024 ** 3)

    @classmethod
    def _minimum_free_gb(cls) -> float:
        try:
            return max(5.0, float(os.environ.get("MPPS_NVME_MIN_FREE_GB") or "20"))
        except ValueError:
            return 20.0

    @classmethod
    def _cleanup_cached_workbook(cls, path: Path) -> bool:
        if not cls._rolling_cache_enabled():
            return False
        inbox = cls.workspace().historical_inbox.resolve()
        try:
            resolved = path.resolve()
            resolved.relative_to(inbox)
            resolved.unlink(missing_ok=True)
            parent = resolved.parent
            while parent != inbox:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
            return True
        except (OSError, ValueError):
            return False

    @classmethod
    def rebuild_deferred_intelligence(
        cls,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        cls._progress(progress, 77, "Rebuilding deferred learning, factory intelligence and AI evaluation once")
        from app.services.production_learning_service import ProductionLearningService
        from app.services.factory_intelligence_service import FactoryIntelligenceService
        from app.services.factory_resource_intelligence_service import (
            FactoryResourceIntelligenceService,
        )
        from app.services.ai_planning_service import AIPlanningService

        learning = ProductionLearningService()
        factory = FactoryIntelligenceService()
        resource = FactoryResourceIntelligenceService()

        # Keep factory-learning work in its own transaction. This avoids holding one
        # very long transaction open while the derived AI evaluation refresh runs.
        with get_session() as session:
            learning.ensure_schema(session)
            factory.ensure_schema(session)
            resource.ensure_schema(session)
            learning_models = learning.rebuild_models(session)
            capacity = factory.train_capacity_models(session)
            planner_policy = factory.train_planner_policy(session)
            # R7.4.1 defers whole-registry lifecycle scans during each old workbook.
            # Refresh once against the newest observed plan date before final model
            # training, preserving the learned lifecycle state without O(N workbooks)
            # repeated full-table updates.
            try:
                latest_resource_date = session.execute(
                    text("SELECT MAX(plan_date) FROM mpps_fi_plan_allocations")
                ).scalar()
                if latest_resource_date:
                    resource.refresh_resource_lifecycle(
                        session, latest_plan_date=latest_resource_date
                    )
            except Exception:
                pass
            resource_profiles = resource.train_profiles(session)
            state = factory.refresh_state(session)

        # R7.4.2: all historical workbooks already persisted their raw final-plan and
        # verified-actual evidence. Reconcile/train/evaluate/generate the global AI
        # state once, after ingestion, instead of rewriting the whole AI corpus after
        # every historical workbook.
        cls._progress(progress, 77, "Rebuilding deferred AI shadow evaluation once")
        ai = AIPlanningService()
        with get_session() as session:
            ai.ensure_schema(session)
            ai_result = ai.rebuild_after_historical_ingestion(session)

        return {
            "learning_models": learning_models,
            "capacity": capacity,
            "planner_policy": planner_policy,
            "resource_profiles": resource_profiles,
            "factory_state": state,
            "ai_planner": ai_result,
        }


    @classmethod
    def _persist_material_plan_history(
        cls,
        *,
        run_id: int,
        analysis,
    ) -> int:
        if isinstance(analysis, dict):
            rows = list(analysis.get("material_plan_rows") or [])
        else:
            rows = list(analysis.material_plan_rows or [])
        if not rows:
            return 0
        with engine.begin() as connection:
            if not cls._table_exists(connection, "excel_import_material_plans"):
                return 0
            existing = int(
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM excel_import_material_plans WHERE run_id=:run_id"
                    ),
                    {"run_id": run_id},
                ).scalar()
                or 0
            )
            if existing > 0:
                return existing
            connection.execute(
                text(
                    """
                    INSERT INTO excel_import_material_plans (
                        run_id, plan_date, material_type, material_key,
                        material_description, day_qty, night_qty, total_qty,
                        produced_qty, stock_qty, next_day_qty, unit,
                        source_sheet, source_row, source_json
                    ) VALUES (
                        :run_id, :plan_date, :material_type, :material_key,
                        :material_description, :day_qty, :night_qty, :total_qty,
                        :produced_qty, :stock_qty, :next_day_qty, :unit,
                        :source_sheet, :source_row, CAST(:source_json AS JSONB)
                    )
                    """
                ),
                [
                    {
                        "run_id": run_id,
                        **row,
                        "plan_date": date.fromisoformat(str(row["plan_date"])[:10]),
                        "source_json": json.dumps(row, default=str),
                    }
                    for row in rows
                ],
            )
        return len(rows)

    @classmethod
    def _historical_ingest_workers(cls) -> int:
        raw = str(os.environ.get("MPPS_R74_INGEST_WORKERS") or "1").strip()
        try:
            requested = int(raw)
        except ValueError:
            requested = 1
        # 16 GB laptops are memory-constrained while each OVEN workbook is opened
        # in both formula and cached-value streaming modes. Keep the pipeline
        # bounded; model training still uses MPPS_ML_THREADS separately.
        return max(1, min(3, requested))

    @classmethod
    def import_historical_inbox(
        cls,
        *,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        files = cls.discover_historical_workbooks()
        committed = cls._committed_hashes()
        importer = IntelligentExcelImportService(cls.workspace().project_root)

        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        state = cls._load_resume_state()
        if not files and str(state.get("status") or "").upper() == "INGESTION_COMPLETE":
            return {
                "inbox": str(cls.workspace().historical_inbox),
                "discovered": int(state.get("total") or 0),
                "imported": 0,
                "skipped_exact_duplicates": 0,
                "failed": 0,
                "results": [],
                "skipped": [],
                "failures": [],
                "paused": False,
                "low_space": False,
                "completed_total": int(state.get("completed") or 0),
                "remaining_cache_files": 0,
                "deferred_intelligence": {"already_completed": True},
                "data_validation": {},
            }

        completed_before = max(0, int(state.get("completed") or 0))
        total_known = max(
            int(state.get("total") or 0),
            completed_before + len(files),
        )
        if total_known <= 0:
            total_known = len(files)

        completed_this_run = 0
        paused = False
        low_space = False
        pause_reason = ""
        ingest_workers = cls._historical_ingest_workers()

        cls._write_resume_state(
            total=total_known,
            completed=completed_before,
            remaining_cache_files=len(files),
            status="RUNNING",
        )
        cls._progress(
            progress,
            int((completed_before / max(1, total_known)) * 75),
            (
                f"R7.4 pipelined historical ingestion enabled: "
                f"{ingest_workers} analyzer process(es), serialized safe DB commits"
            ),
        )

        def request_pause_if_needed() -> bool:
            nonlocal paused, low_space, pause_reason
            if cls._pause_requested():
                paused = True
                pause_reason = "USER_REQUESTED"
                return True
            free_gb = cls._nvme_free_gb()
            if free_gb < cls._minimum_free_gb():
                paused = True
                low_space = True
                pause_reason = f"LOW_SPACE_{free_gb:.2f}_GB"
                return True
            return False

        def record_duplicate(path: Path, digest: str) -> None:
            nonlocal completed_this_run
            skipped.append(
                {
                    "file": str(path),
                    "reason": "EXACT_COMMITTED_DUPLICATE",
                    "existing_run_id": committed[digest],
                    "workbook_hash": digest,
                }
            )
            cls._cleanup_cached_workbook(path)
            completed_this_run += 1
            cls._write_resume_state(
                total=total_known,
                completed=completed_before + completed_this_run,
                last_file=str(path),
                last_result="EXACT_COMMITTED_DUPLICATE",
                free_gb=round(cls._nvme_free_gb(), 3),
            )

        def commit_analysis(path: Path, digest: str, analysis_payload: dict[str, Any]) -> None:
            nonlocal completed_this_run
            # A duplicate may have become committed while this workbook was being
            # analyzed in parallel. Re-check before opening a DB transaction.
            if digest in committed:
                record_duplicate(path, digest)
                return

            if not analysis_payload.get("plan_date"):
                raise ValueError(
                    "Workbook has no reliable plan date; historical import is blocked."
                )
            if float(analysis_payload.get("confidence_score") or 0) < 0.55:
                raise ValueError(
                    "Workbook confidence "
                    f"{float(analysis_payload.get('confidence_score') or 0):.3f} "
                    "is below 0.55."
                )

            commit_started = time.perf_counter()
            result = importer.commit(
                analysis_payload,
                options={
                    "archive_source": True,
                    "update_stock": False,
                    "update_daily_stock": False,
                    "update_blank_weights": False,
                    "overwrite_existing_weights": False,
                    "import_oven_plan": True,
                    "import_materials": False,
                    "import_shipment_snapshots": True,
                    "sync_live_shipments": False,
                    "create_draft_shipments": False,
                    "auto_detect_import_mode": False,
                    "force_historical_snapshot": True,
                    "force_live_revision": False,
                    "mark_missing_shipments": False,
                    "sync_deferred_shipments": False,
                    "authoritative_latest_shipments": False,
                    "protect_manual_fields": True,
                    "capture_learning_observations": True,
                    "rebuild_learning_models": False,
                    "defer_factory_intelligence_training": True,
                    "import_production_history": True,
                },
                imported_by="R7.4.2 Turbo AI-Deferred Historical Pipeline",
            )
            commit_seconds = time.perf_counter() - commit_started
            print(
                f"[R7.4.2 DB TURBO] {path.name}: safe commit {commit_seconds:.1f}s",
                flush=True,
            )
            run_id = int(result.get("run_id") or 0)
            material_rows = cls._persist_material_plan_history(
                run_id=run_id,
                analysis=analysis_payload,
            )
            result = {
                **dict(result),
                "source_file": str(path),
                "workbook_hash": digest,
                "historical_safety_mode": True,
                "r74_pipelined_analysis": True,
                "material_history_rows": material_rows,
                "rolling_cache_deleted": cls._cleanup_cached_workbook(path),
            }
            results.append(result)
            committed[digest] = run_id
            completed_this_run += 1
            cls._write_resume_state(
                total=total_known,
                completed=completed_before + completed_this_run,
                last_file=str(path),
                last_result="COMMITTED",
                last_run_id=run_id,
                free_gb=round(cls._nvme_free_gb(), 3),
            )

        # Preserve the original conservative path when R7.4 is not explicitly
        # enabled. This keeps ordinary app imports unchanged.
        if ingest_workers <= 1:
            for file_index, path in enumerate(files):
                if request_pause_if_needed():
                    break

                display_index = min(total_known, completed_before + file_index + 1)
                base = int(((max(1, display_index) - 1) / max(1, total_known)) * 75)
                cls._progress(
                    progress,
                    base,
                    f"Historical workbook {display_index}/{total_known}: {path.name}",
                )
                try:
                    digest = cls._sha256_file(path).lower()
                    if digest in committed:
                        record_duplicate(path, digest)
                        continue
                    analysis_payload = importer.analyze(path).to_dict(include_rows=True)
                    commit_analysis(path, digest, analysis_payload)
                except Exception as exc:
                    failures.append({"file": str(path), "error": str(exc)})
                    cls._write_resume_state(
                        total=total_known,
                        completed=completed_before + completed_this_run,
                        last_file=str(path),
                        last_result="FAILED_RETAINED_FOR_RETRY",
                        last_error=str(exc),
                        free_gb=round(cls._nvme_free_gb(), 3),
                    )
        else:
            executor = ProcessPoolExecutor(max_workers=ingest_workers)
            pending = deque()
            next_file_index = 0
            try:
                while next_file_index < len(files) or pending:
                    # Keep only a small bounded analysis window in memory.
                    while (
                        not paused
                        and next_file_index < len(files)
                        and len(pending) < ingest_workers
                    ):
                        if request_pause_if_needed():
                            break

                        file_index = next_file_index
                        path = files[file_index]
                        next_file_index += 1
                        display_index = min(
                            total_known,
                            completed_before + file_index + 1,
                        )
                        base = int(
                            ((max(1, display_index) - 1) / max(1, total_known)) * 75
                        )
                        cls._progress(
                            progress,
                            base,
                            (
                                f"Historical workbook {display_index}/{total_known}: "
                                f"{path.name} [R7.4 analyze queue]"
                            ),
                        )
                        try:
                            digest = cls._sha256_file(path).lower()
                            if digest in committed:
                                record_duplicate(path, digest)
                                continue
                            future = executor.submit(
                                _r74_analyze_historical_worker,
                                str(cls.workspace().project_root),
                                str(path),
                            )
                            pending.append(
                                (file_index, display_index, path, digest, future)
                            )
                        except Exception as exc:
                            failures.append({"file": str(path), "error": str(exc)})
                            cls._write_resume_state(
                                total=total_known,
                                completed=completed_before + completed_this_run,
                                last_file=str(path),
                                last_result="FAILED_RETAINED_FOR_RETRY",
                                last_error=str(exc),
                                free_gb=round(cls._nvme_free_gb(), 3),
                            )

                    if paused:
                        break
                    if not pending:
                        continue

                    _file_index, display_index, path, digest, future = pending.popleft()
                    try:
                        analysis_payload = future.result()
                        # Pause only at a safe boundary: an analyzed workbook is not
                        # committed after a pause request; its C: cache remains for resume.
                        if request_pause_if_needed():
                            break
                        cls._progress(
                            progress,
                            int(
                                ((max(1, display_index) - 1) / max(1, total_known))
                                * 75
                            ),
                            (
                                f"Historical workbook {display_index}/{total_known}: "
                                f"{path.name} [R7.4 safe DB commit]"
                            ),
                        )
                        commit_analysis(path, digest, analysis_payload)
                    except Exception as exc:
                        failures.append({"file": str(path), "error": str(exc)})
                        cls._write_resume_state(
                            total=total_known,
                            completed=completed_before + completed_this_run,
                            last_file=str(path),
                            last_result="FAILED_RETAINED_FOR_RETRY",
                            last_error=str(exc),
                            free_gb=round(cls._nvme_free_gb(), 3),
                        )
            finally:
                # On pause, queued futures are discarded and running analyzers are
                # allowed to finish without touching PostgreSQL. No partial workbook
                # transaction is left behind.
                executor.shutdown(wait=True, cancel_futures=True)

        remaining_files = cls.discover_historical_workbooks()
        completed_total = completed_before + completed_this_run
        if paused:
            cls._write_resume_state(
                total=total_known,
                completed=completed_total,
                remaining_cache_files=len(remaining_files),
                status="PAUSED_LOW_SPACE" if low_space else "PAUSED_SAFE",
                pause_reason=pause_reason,
                free_gb=round(cls._nvme_free_gb(), 3),
            )
            return {
                "inbox": str(cls.workspace().historical_inbox),
                "discovered": total_known,
                "imported": len(results),
                "skipped_exact_duplicates": len(skipped),
                "failed": len(failures),
                "results": results,
                "skipped": skipped,
                "failures": failures,
                "paused": True,
                "low_space": low_space,
                "pause_reason": pause_reason,
                "completed_total": completed_total,
                "remaining_cache_files": len(remaining_files),
                "data_validation": {},
            }

        cls._progress(progress, 76, "Historical ingestion complete; rebuilding deferred intelligence")
        deferred = cls.rebuild_deferred_intelligence(progress=progress)
        cls._progress(progress, 78, "Normalizing imported history")
        data_validation = HistoricalDatasetValidationService.validate(
            normalize=True,
            persist=True,
        )
        cls._write_resume_state(
            total=total_known,
            completed=completed_total,
            remaining_cache_files=len(remaining_files),
            status="INGESTION_COMPLETE",
            free_gb=round(cls._nvme_free_gb(), 3),
        )
        return {
            "inbox": str(cls.workspace().historical_inbox),
            "discovered": total_known,
            "imported": len(results),
            "skipped_exact_duplicates": len(skipped),
            "failed": len(failures),
            "results": results,
            "skipped": skipped,
            "failures": failures,
            "paused": False,
            "low_space": False,
            "completed_total": completed_total,
            "remaining_cache_files": len(remaining_files),
            "deferred_intelligence": deferred,
            "data_validation": data_validation,
        }

    @classmethod
    def training_readiness(cls) -> dict[str, Any]:
        readiness = MLTrainingOrchestrator.readiness_report()
        dataset = dict(readiness.get("dataset") or {})
        readiness["preferred_history_days"] = cls.PREFERRED_HISTORY_DAYS
        readiness["preferred_two_year_history_met"] = bool(
            int(dataset.get("history_days") or 0) >= cls.PREFERRED_HISTORY_DAYS
        )
        return readiness

    @classmethod
    def train_eligible_models(
        cls,
        *,
        progress: ProgressCallback | None = None,
        auto_promote: bool = True,
    ) -> dict[str, Any]:
        readiness = cls.training_readiness()
        dataset = dict(readiness.get("dataset") or {})
        if int(dataset.get("critical_issue_count") or 0) > 0:
            raise RuntimeError(
                "Historical dataset contains CRITICAL issues. Training is blocked."
            )

        runtime = cls.runtime_status()
        if not runtime.get("required_ready"):
            raise RuntimeError(
                "Required ML runtime is missing. Run the final ML launcher with runtime installation enabled."
            )

        ready = [
            row
            for row in readiness.get("models") or []
            if row.get("ready_to_train")
        ]
        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        total = max(1, len(ready))
        paused = False
        for index, row in enumerate(ready, start=1):
            if cls._pause_requested():
                paused = True
                break
            model_key = str(row.get("model_key") or "")
            cls._progress(
                progress,
                80 + int((index - 1) / total * 18),
                f"Training {index}/{len(ready)}: {model_key}",
            )
            try:
                result = MLTrainingEngine.train_model(
                    model_key,
                    auto_promote=auto_promote,
                )
                results.append(result)
            except Exception as exc:
                failures.append(
                    {
                        "model_key": model_key,
                        "error": str(exc),
                    }
                )

        platform = MLPlatformService.snapshot()
        return {
            "attempted": len(ready),
            "trained": len(results),
            "promoted": sum(bool(row.get("promoted")) for row in results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
            "paused": paused,
            "readiness_before_training": readiness,
            "platform_after_training": platform,
        }

    @classmethod
    def _champion_count(cls) -> int:
        with engine.connect() as connection:
            if not cls._table_exists(connection, "mpps_ml_model_versions_v2"):
                return 0
            return int(
                connection.execute(
                    text(
                        "SELECT COUNT(*) FROM mpps_ml_model_versions_v2 WHERE status='CHAMPION'"
                    )
                ).scalar()
                or 0
            )

    @classmethod
    def _write_report(cls, report: dict[str, Any]) -> tuple[str, str]:
        workspace = cls.workspace()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = workspace.reports_dir / f"R7_FINAL_ML_TRAINING_{stamp}.json"
        txt_path = workspace.reports_dir / f"R7_FINAL_ML_TRAINING_{stamp}.txt"
        json_path.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )

        readiness = dict(report.get("readiness_after") or {})
        dataset = dict(readiness.get("dataset") or {})
        training = dict(report.get("training") or {})
        stock = dict(report.get("stock_authority") or {})
        runtime = dict(report.get("runtime") or {})
        lines = [
            "MPPS R7 FINAL ML TRAINING REPORT",
            "=================================",
            f"Release: {cls.RELEASE}",
            f"Generated: {report.get('generated_at')}",
            "",
            f"Stock authority verified: {stock.get('verified')}",
            f"Stock authority repaired: {stock.get('repaired')}",
            f"ML runtime ready: {runtime.get('required_ready')}",
            f"Historical first date: {dataset.get('first_date')}",
            f"Historical last date: {dataset.get('last_date')}",
            f"Historical span: {dataset.get('history_days')} days",
            f"Observation days: {dataset.get('observation_days')}",
            f"Observation rows: {dataset.get('total_rows')}",
            f"Critical data issues: {dataset.get('critical_issue_count')}",
            f"Warnings: {dataset.get('warning_count')}",
            f"Two-year preferred target met: {readiness.get('preferred_two_year_history_met')}",
            f"Models data-ready: {readiness.get('ready_models')}/{readiness.get('total_models')}",
            f"Models trained this run: {training.get('trained', 0)}",
            f"Champions promoted this run: {training.get('promoted', 0)}",
            f"Training failures: {training.get('failed', 0)}",
            f"Total champion models: {report.get('champion_count')}",
            "",
            f"Historical inbox: {workspace.historical_inbox}",
            "",
            "IMPORTANT:",
            "Models with no trustworthy target label remain NOT READY by design.",
            "Operational shipment/stock/capacity/plan facts remain deterministic PostgreSQL authority.",
        ]
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(txt_path), str(json_path)

    @classmethod
    def run_final_pipeline(
        cls,
        *,
        import_inbox: bool = True,
        train: bool = True,
        install_runtime: bool = False,
        repair_stock: bool = True,
        auto_promote: bool = True,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        workspace = cls.workspace()
        cls._progress(progress, 1, "Verifying canonical Current Stock authority")
        stock = cls.verify_or_rebuild_stock_authority(repair=repair_stock)

        runtime = cls.runtime_status()
        runtime_install = None
        if install_runtime and not runtime.get("required_ready"):
            runtime_install = cls.install_ml_runtime(progress=progress)
            runtime = dict(runtime_install.get("after") or cls.runtime_status())

        import_result = {
            "inbox": str(workspace.historical_inbox),
            "discovered": 0,
            "imported": 0,
            "skipped_exact_duplicates": 0,
            "failed": 0,
            "results": [],
            "skipped": [],
            "failures": [],
        }
        if import_inbox:
            cls._progress(progress, 10, "Scanning Historical Training Inbox")
            import_result = cls.import_historical_inbox(progress=progress)

        pipeline_paused = bool(import_result.get("paused"))
        cls._progress(progress, 79, "Validating chronological training readiness")
        readiness = cls.training_readiness()

        training = {
            "attempted": 0,
            "trained": 0,
            "promoted": 0,
            "failed": 0,
            "results": [],
            "failures": [],
        }
        training_block_reason = ""
        if pipeline_paused:
            training_block_reason = str(import_result.get("pause_reason") or "SAFE_PAUSE_REQUESTED")
        elif train:
            if not stock.get("verified"):
                training_block_reason = "Canonical Current Stock authority is not verified."
            elif not runtime.get("required_ready"):
                training_block_reason = "Required ML runtime is not installed."
            elif int((readiness.get("dataset") or {}).get("critical_issue_count") or 0) > 0:
                training_block_reason = "Historical dataset contains CRITICAL validation issues."
            elif int(readiness.get("ready_models") or 0) <= 0:
                training_block_reason = "No model dataset currently passes the training gates."
            else:
                training = cls.train_eligible_models(
                    progress=progress,
                    auto_promote=auto_promote,
                )
                if training.get("paused"):
                    pipeline_paused = True
                    training_block_reason = "SAFE_PAUSE_REQUESTED_BETWEEN_MODELS"

        cls._progress(progress, 99, "Refreshing final ML readiness")
        readiness_after = cls.training_readiness()
        champion_count = cls._champion_count()

        status = "COMPLETED"
        if pipeline_paused:
            status = (
                "PAUSED_LOW_SPACE"
                if import_result.get("low_space")
                else "PAUSED_SAFE"
            )
        elif training_block_reason:
            status = "WAITING_FOR_DATA_OR_RUNTIME"
        if not pipeline_paused and (import_result.get("failed") or training.get("failed")):
            status = "COMPLETED_WITH_WARNINGS"

        report = {
            "release": cls.RELEASE,
            "status": status,
            "generated_at": datetime.now().isoformat(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "workspace": {
                "project_root": str(workspace.project_root),
                "historical_inbox": str(workspace.historical_inbox),
                "models_dir": str(workspace.models_dir),
                "reports_dir": str(workspace.reports_dir),
            },
            "stock_authority": stock,
            "runtime": runtime,
            "runtime_install": runtime_install,
            "historical_import": import_result,
            "readiness_after": readiness_after,
            "training": training,
            "training_block_reason": training_block_reason,
            "champion_count": champion_count,
            "operational_authority": "POSTGRESQL_DETERMINISTIC",
            "ml_role": "ADVISORY_PREDICTION_RECOMMENDATION",
        }
        txt_path, json_path = cls._write_report(report)
        report["report_text"] = txt_path
        report["report_json"] = json_path
        cls._progress(progress, 100, "R7 Final ML pipeline complete")
        return report
