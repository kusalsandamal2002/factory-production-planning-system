from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text


@dataclass(frozen=True)
class TyreMLModule:
    key: str
    name: str
    purpose: str
    data_source: str
    minimum_history_days: int
    training_mode: str


class TyreMasterIntelligenceService:
    """Training-ready AI/ML control layer for Tyre Item Master.

    This service does not invent model accuracy and does not modify official
    master data. It provides module registration, data-health profiling,
    readiness gates and a single orchestration entry point for future training.
    """

    MODEL_VERSION = "MPPS-TYRE-ML-V29"

    MODULES = (
        TyreMLModule(
            "MASTER_HEALTH",
            "Master Data Health",
            "Detect missing, inconsistent and weak master records.",
            "SMDS / Tyre Item Master",
            0,
            "RULE + STATISTICAL",
        ),
        TyreMLModule(
            "DUPLICATE_IDENTITY",
            "Duplicate & Identity Intelligence",
            "Find duplicate / near-duplicate SAP and tyre descriptions.",
            "SMDS + Historical OVEN",
            0,
            "SIMILARITY / CLUSTERING",
        ),
        TyreMLModule(
            "CURING_TIME",
            "Curing Time Intelligence",
            "Learn stable curing-time recommendations from verified history.",
            "Master + Production Actuals",
            90,
            "REGRESSION / ROBUST BASELINE",
        ),
        TyreMLModule(
            "LINE_COMPATIBILITY",
            "Line Compatibility Intelligence",
            "Rank compatible production lines from successful historical runs.",
            "Line Mapping + Production Actuals",
            180,
            "RANKING / CLASSIFICATION",
        ),
        TyreMLModule(
            "MOLD_CASING",
            "Mold & Casing Intelligence",
            "Recommend mold and casing relationships from validated history.",
            "SMDS + Mold/Casing + Actuals",
            180,
            "CLASSIFICATION",
        ),
        TyreMLModule(
            "GROUP_CLASSIFIER",
            "Tyre Group Intelligence",
            "Learn group-key / product-family assignment patterns.",
            "SMDS + Product Groups",
            0,
            "CLASSIFICATION",
        ),
        TyreMLModule(
            "WEIGHT_ANOMALY",
            "Weight & Process Anomaly",
            "Detect abnormal tyre weight and process-master values.",
            "SMDS + Historical Actuals",
            90,
            "ANOMALY DETECTION",
        ),
    )

    @staticmethod
    def ensure_schema(session) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS mpps_tyre_ml_model_registry (
                module_key VARCHAR(64) PRIMARY KEY,
                module_name TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT '',
                training_mode VARCHAR(80) NOT NULL DEFAULT '',
                status VARCHAR(40) NOT NULL DEFAULT 'NOT_TRAINED',
                model_version VARCHAR(64) NOT NULL DEFAULT 'MPPS-TYRE-ML-V29',
                training_rows INTEGER NOT NULL DEFAULT 0,
                validation_score NUMERIC(10,6),
                confidence_score NUMERIC(10,6),
                model_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                last_trained_at TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_tyre_ml_training_runs (
                id BIGSERIAL PRIMARY KEY,
                requested_mode VARCHAR(40) NOT NULL DEFAULT 'TRAIN_ALL',
                status VARCHAR(40) NOT NULL DEFAULT 'CREATED',
                module_count INTEGER NOT NULL DEFAULT 0,
                ready_module_count INTEGER NOT NULL DEFAULT 0,
                historical_days INTEGER NOT NULL DEFAULT 0,
                historical_workbooks INTEGER NOT NULL DEFAULT 0,
                summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_tyre_ml_suggestions (
                id BIGSERIAL PRIMARY KEY,
                module_key VARCHAR(64) NOT NULL,
                sap_code TEXT NOT NULL DEFAULT '',
                field_name TEXT NOT NULL DEFAULT '',
                current_value TEXT NOT NULL DEFAULT '',
                suggested_value TEXT NOT NULL DEFAULT '',
                confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0,
                status VARCHAR(30) NOT NULL DEFAULT 'ADVISORY',
                explanation TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP
            )
            """,
        ]
        for statement in statements:
            session.execute(text(statement))

        for module in TyreMasterIntelligenceService.MODULES:
            session.execute(
                text(
                    """
                    INSERT INTO mpps_tyre_ml_model_registry (
                        module_key, module_name, purpose, training_mode,
                        status, model_version
                    )
                    VALUES (
                        :key, :name, :purpose, :mode,
                        'NOT_TRAINED', :version
                    )
                    ON CONFLICT (module_key) DO UPDATE
                    SET module_name = EXCLUDED.module_name,
                        purpose = EXCLUDED.purpose,
                        training_mode = EXCLUDED.training_mode,
                        model_version = EXCLUDED.model_version,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "key": module.key,
                    "name": module.name,
                    "purpose": module.purpose,
                    "mode": module.training_mode,
                    "version": TyreMasterIntelligenceService.MODEL_VERSION,
                },
            )

    @staticmethod
    def _table_exists(session, table_name: str) -> bool:
        try:
            value = session.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                    )
                    """
                ),
                {"table_name": table_name},
            ).scalar()
            return bool(value)
        except Exception:
            return False

    @staticmethod
    def _columns(session, table_name: str) -> set[str]:
        try:
            rows = session.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                    """
                ),
                {"table_name": table_name},
            ).scalars().all()
            return {str(value) for value in rows}
        except Exception:
            return set()

    @staticmethod
    def _safe_scalar(session, sql: str, params: dict[str, Any] | None = None, default=0):
        try:
            value = session.execute(text(sql), params or {}).scalar()
            if value is None:
                return default
            return value
        except Exception:
            return default

    @classmethod
    def _master_source(cls, session) -> tuple[str, set[str]]:
        if cls._table_exists(session, "smds"):
            cols = cls._columns(session, "smds")
            if "sap_code" in cols:
                return "smds", cols

        if cls._table_exists(session, "tyre_item_master"):
            return "tyre_item_master", cls._columns(session, "tyre_item_master")

        return "", set()

    @classmethod
    def _coverage(cls, session, table_name: str, columns: set[str], candidates: tuple[str, ...]) -> tuple[int, str]:
        selected = next((name for name in candidates if name in columns), "")
        if not table_name or not selected:
            return 0, ""

        count = cls._safe_scalar(
            session,
            f"""
            SELECT COUNT(*)
            FROM {table_name}
            WHERE {selected} IS NOT NULL
              AND TRIM(CAST({selected} AS TEXT)) <> ''
              AND TRIM(CAST({selected} AS TEXT)) NOT IN ('0', '0.0', '0.00')
            """,
            default=0,
        )
        try:
            return int(count or 0), selected
        except Exception:
            return 0, selected

    @classmethod
    def master_profile(cls, session) -> dict[str, Any]:
        table_name, columns = cls._master_source(session)

        if not table_name:
            return {
                "source": "NONE",
                "items": 0,
                "missing_sap": 0,
                "missing_description": 0,
                "duplicate_sap": 0,
                "curing_rows": 0,
                "line_rows": 0,
                "mold_rows": 0,
                "casing_rows": 0,
                "group_rows": 0,
                "weight_rows": 0,
                "health_score": 0.0,
            }

        desc_col = next(
            (
                name
                for name in (
                    "material_description",
                    "tyre_description",
                    "description",
                    "item_description",
                )
                if name in columns
            ),
            "",
        )

        items = int(
            cls._safe_scalar(
                session,
                f"SELECT COUNT(*) FROM {table_name}",
                default=0,
            )
            or 0
        )

        missing_sap = 0
        if "sap_code" in columns:
            missing_sap = int(
                cls._safe_scalar(
                    session,
                    f"""
                    SELECT COUNT(*)
                    FROM {table_name}
                    WHERE sap_code IS NULL
                       OR TRIM(CAST(sap_code AS TEXT)) = ''
                    """,
                    default=0,
                )
                or 0
            )

        missing_description = 0
        if desc_col:
            missing_description = int(
                cls._safe_scalar(
                    session,
                    f"""
                    SELECT COUNT(*)
                    FROM {table_name}
                    WHERE {desc_col} IS NULL
                       OR TRIM(CAST({desc_col} AS TEXT)) = ''
                    """,
                    default=0,
                )
                or 0
            )

        duplicate_sap = 0
        if "sap_code" in columns:
            duplicate_sap = int(
                cls._safe_scalar(
                    session,
                    f"""
                    SELECT COALESCE(SUM(cnt - 1), 0)
                    FROM (
                        SELECT COUNT(*) AS cnt
                        FROM {table_name}
                        WHERE sap_code IS NOT NULL
                          AND TRIM(CAST(sap_code AS TEXT)) <> ''
                        GROUP BY TRIM(CAST(sap_code AS TEXT))
                        HAVING COUNT(*) > 1
                    ) d
                    """,
                    default=0,
                )
                or 0
            )

        curing_rows, curing_col = cls._coverage(
            session,
            table_name,
            columns,
            (
                "normal_curing_minutes",
                "curing_time_minutes",
                "curing_minutes",
                "curing_time",
            ),
        )
        line_rows, line_col = cls._coverage(
            session,
            table_name,
            columns,
            (
                "production_line",
                "line_name",
                "line_code",
                "line",
            ),
        )
        mold_rows, mold_col = cls._coverage(
            session,
            table_name,
            columns,
            ("mold_key_code", "mold_code", "mold", "mould"),
        )
        casing_rows, casing_col = cls._coverage(
            session,
            table_name,
            columns,
            ("casing_type", "casing_code", "casing"),
        )
        group_rows, group_col = cls._coverage(
            session,
            table_name,
            columns,
            (
                "group_key",
                "tyre_group_key",
                "product_group",
                "product_group_name",
            ),
        )
        weight_rows, weight_col = cls._coverage(
            session,
            table_name,
            columns,
            (
                "weight_per_tyre_kg",
                "weight_kg",
                "item_weight_kg",
                "weight",
            ),
        )

        denominator = max(1, items)
        issue_ratio = (
            missing_sap
            + missing_description
            + duplicate_sap
        ) / denominator
        health_score = max(0.0, min(100.0, 100.0 - issue_ratio * 100.0))

        return {
            "source": table_name.upper(),
            "items": items,
            "missing_sap": missing_sap,
            "missing_description": missing_description,
            "duplicate_sap": duplicate_sap,
            "curing_rows": curing_rows,
            "line_rows": line_rows,
            "mold_rows": mold_rows,
            "casing_rows": casing_rows,
            "group_rows": group_rows,
            "weight_rows": weight_rows,
            "health_score": health_score,
            "field_map": {
                "description": desc_col,
                "curing": curing_col,
                "line": line_col,
                "mold": mold_col,
                "casing": casing_col,
                "group": group_col,
                "weight": weight_col,
            },
        }

    @classmethod
    def history_profile(cls, session) -> dict[str, int]:
        historical_days = 0
        historical_workbooks = 0

        if cls._table_exists(session, "mpps_factory_intelligence_state"):
            row = None
            try:
                row = session.execute(
                    text(
                        """
                        SELECT actual_production_days,
                               historical_workbook_count
                        FROM mpps_factory_intelligence_state
                        WHERE id = 1
                        """
                    )
                ).mappings().first()
            except Exception:
                row = None

            if row:
                historical_days = int(row.get("actual_production_days") or 0)
                historical_workbooks = int(row.get("historical_workbook_count") or 0)

        if historical_days <= 0 and cls._table_exists(session, "mpps_factory_daily_capacity"):
            historical_days = int(
                cls._safe_scalar(
                    session,
                    "SELECT COUNT(*) FROM mpps_factory_daily_capacity",
                    default=0,
                )
                or 0
            )

        return {
            "historical_days": historical_days,
            "historical_workbooks": historical_workbooks,
        }

    @classmethod
    def module_readiness(
        cls,
        module: TyreMLModule,
        master: dict[str, Any],
        history: dict[str, int],
    ) -> tuple[bool, str]:
        items = int(master.get("items") or 0)
        days = int(history.get("historical_days") or 0)

        if module.key == "MASTER_HEALTH":
            ready = items > 0
            return ready, "Master rows available." if ready else "Waiting for master data."

        if module.key == "DUPLICATE_IDENTITY":
            ready = items >= 25
            return ready, "Enough master items for similarity analysis." if ready else "Need at least 25 master items."

        if module.key == "CURING_TIME":
            if int(master.get("curing_rows") or 0) < 25:
                return False, "Need at least 25 curing-time master rows."
            if days < module.minimum_history_days:
                return False, f"Need {module.minimum_history_days}+ verified production days."
            return True, "Curing fields and historical production coverage are ready."

        if module.key == "LINE_COMPATIBILITY":
            if int(master.get("line_rows") or 0) < 25:
                return False, "Need at least 25 line-mapped tyre rows."
            if days < module.minimum_history_days:
                return False, f"Need {module.minimum_history_days}+ verified production days."
            return True, "Line mapping and history are ready."

        if module.key == "MOLD_CASING":
            mapped = min(
                int(master.get("mold_rows") or 0),
                int(master.get("casing_rows") or 0),
            )
            if mapped < 25:
                return False, "Need at least 25 mold + casing mapped rows."
            if days < module.minimum_history_days:
                return False, f"Need {module.minimum_history_days}+ verified production days."
            return True, "Mold/casing mapping and history are ready."

        if module.key == "GROUP_CLASSIFIER":
            ready = int(master.get("group_rows") or 0) >= 25
            return ready, "Group-labelled master rows are ready." if ready else "Need at least 25 group-labelled rows."

        if module.key == "WEIGHT_ANOMALY":
            if int(master.get("weight_rows") or 0) < 25:
                return False, "Need at least 25 valid tyre-weight rows."
            if days < module.minimum_history_days:
                return False, f"Need {module.minimum_history_days}+ verified production days."
            return True, "Weight values and historical evidence are ready."

        return False, "Readiness rule is not configured."

    @classmethod
    def dashboard(cls, session) -> dict[str, Any]:
        cls.ensure_schema(session)
        master = cls.master_profile(session)
        history = cls.history_profile(session)

        registry_rows = {}
        try:
            rows = session.execute(
                text(
                    """
                    SELECT module_key, status, model_version,
                           training_rows, validation_score,
                           confidence_score, last_trained_at
                    FROM mpps_tyre_ml_model_registry
                    """
                )
            ).mappings().all()
            registry_rows = {str(row["module_key"]): dict(row) for row in rows}
        except Exception:
            registry_rows = {}

        modules = []
        ready_count = 0
        trained_count = 0

        for module in cls.MODULES:
            ready, explanation = cls.module_readiness(module, master, history)
            row = registry_rows.get(module.key, {})
            trained = str(row.get("status") or "").upper().startswith("TRAINED")

            if ready:
                ready_count += 1
            if trained:
                trained_count += 1

            modules.append(
                {
                    "key": module.key,
                    "name": module.name,
                    "purpose": module.purpose,
                    "data_source": module.data_source,
                    "minimum_history_days": module.minimum_history_days,
                    "training_mode": module.training_mode,
                    "ready": ready,
                    "readiness": "READY TO TRAIN" if ready else "WAITING DATA",
                    "explanation": explanation,
                    "status": row.get("status") or "NOT_TRAINED",
                    "validation_score": row.get("validation_score"),
                    "confidence_score": row.get("confidence_score"),
                    "last_trained_at": row.get("last_trained_at"),
                }
            )

        return {
            "model_version": cls.MODEL_VERSION,
            "master": master,
            "history": history,
            "modules": modules,
            "module_count": len(modules),
            "ready_count": ready_count,
            "trained_count": trained_count,
            "all_ready": ready_count == len(modules),
            "training_policy": "SINGLE_PIPELINE_ALL_MODULES",
        }

    @classmethod
    def request_train_all(cls, session) -> dict[str, Any]:
        """Single orchestration hook used by the UI.

        V29 intentionally blocks fake training. The run is accepted only when
        every module passes data-readiness gates. Trainer implementations can be
        plugged behind this one method without changing the UI workflow.
        """
        dashboard = cls.dashboard(session)
        all_ready = bool(dashboard.get("all_ready"))

        run_id = session.execute(
            text(
                """
                INSERT INTO mpps_tyre_ml_training_runs (
                    requested_mode, status, module_count,
                    ready_module_count, historical_days,
                    historical_workbooks, summary_json,
                    finished_at
                )
                VALUES (
                    'TRAIN_ALL', :status, :module_count,
                    :ready_count, :historical_days,
                    :historical_workbooks,
                    CAST(:summary AS JSONB),
                    CASE WHEN :status = 'BLOCKED_DATA' THEN CURRENT_TIMESTAMP ELSE NULL END
                )
                RETURNING id
                """
            ),
            {
                "status": "READY_FOR_TRAINERS" if all_ready else "BLOCKED_DATA",
                "module_count": int(dashboard.get("module_count") or 0),
                "ready_count": int(dashboard.get("ready_count") or 0),
                "historical_days": int(
                    dashboard.get("history", {}).get("historical_days") or 0
                ),
                "historical_workbooks": int(
                    dashboard.get("history", {}).get("historical_workbooks") or 0
                ),
                "summary": __import__("json").dumps(
                    {
                        "model_version": cls.MODEL_VERSION,
                        "all_ready": all_ready,
                        "modules": [
                            {
                                "key": row.get("key"),
                                "ready": row.get("ready"),
                                "explanation": row.get("explanation"),
                            }
                            for row in dashboard.get("modules", [])
                        ],
                    }
                ),
            },
        ).scalar()

        return {
            "run_id": int(run_id or 0),
            "status": "READY_FOR_TRAINERS" if all_ready else "BLOCKED_DATA",
            "all_ready": all_ready,
            "ready_count": int(dashboard.get("ready_count") or 0),
            "module_count": int(dashboard.get("module_count") or 0),
            "message": (
                "All tyre ML modules passed readiness gates. "
                "The single Train-All pipeline is ready for trainer execution."
                if all_ready
                else
                "Training was not started because one or more ML modules still "
                "need historical/master data. No fake models were created."
            ),
        }
