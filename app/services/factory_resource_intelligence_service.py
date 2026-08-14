from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
from statistics import mean, median
from typing import Any, Iterable, Callable
from types import SimpleNamespace

from sqlalchemy import text

from app.services.master_data_normalization import clean_text, normalize_sap_code


# FACTORY RESOURCE & CAPACITY INTELLIGENCE V11
# ------------------------------------------------------------
# This service is deliberately independent from the legacy manual-capacity page.
# It stores lossless resource observations from OVEN workbooks, joins them to
# verified PROD actuals, learns real capacity envelopes and exposes ONE resolver
# for operational callers. Manual/SMDS capacity remains a labelled fallback.
# ------------------------------------------------------------


def _code(value: Any) -> str:
    value = normalize_sap_code(value)
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    return value.upper().strip()


def _text(value: Any) -> str:
    return clean_text(value).strip()


def _norm(value: Any) -> str:
    return " ".join(_text(value).upper().replace("_", " ").split())


_NO_CASING_ALIASES = {"-", "--", "NO CASING", "NO-CASING", "NONE", "N/A", "NA", "NOT REQUIRED"}


def _canonical_casing(value: Any) -> str:
    """Return one operator-facing casing identity without inventing missing data.

    A literal '-' in legacy Excel/master data means the same thing as 'No Casing'.
    Blank/unknown values stay blank so missing evidence is not silently promoted to a
    technical fact.
    """
    raw = _text(value)
    if not raw:
        return ""
    if _norm(raw) in _NO_CASING_ALIASES:
        return "No Casing"
    return raw


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value if value is not None else default)))
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _quantile(values: Iterable[float], q: float, default: float = 0.0) -> float:
    cleaned = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not cleaned:
        return default
    q = _clamp(q, 0.0, 1.0)
    pos = (len(cleaned) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return cleaned[lo]
    w = pos - lo
    return cleaned[lo] * (1.0 - w) + cleaned[hi] * w


def _stable_max(values: list[int]) -> int:
    """Return a repeatable maximum, not a one-off historical peak."""
    clean = [max(0, int(v)) for v in values if int(v) > 0]
    if not clean:
        return 0
    counts = Counter(clean)
    n = len(clean)
    # A stable configuration should appear at least three times once history is
    # mature, otherwise at least twice.  The threshold prevents a single extreme
    # day from becoming the normal planning maximum.
    threshold = 3 if n >= 10 else 2
    candidates = [v for v, c in counts.items() if c >= threshold]
    if candidates:
        return max(candidates)
    # Cold-start: use median configuration rather than observed maximum.
    return max(1, int(round(median(clean))))


@dataclass(frozen=True)
class CapacityResolution:
    sap_code: str
    safe_capacity: int
    expected_capacity: int
    stretch_capacity: int
    available_capacity: int
    source: str
    confidence_score: float
    confidence_band: str
    stable_cavity_count: int
    observed_max_cavity_count: int
    sample_days: int
    mold_key: str
    casing_type: str
    technical_capacity: int
    constraint_reason: str
    model_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sap_code": self.sap_code,
            "safe_capacity": self.safe_capacity,
            "expected_capacity": self.expected_capacity,
            "stretch_capacity": self.stretch_capacity,
            "available_capacity": self.available_capacity,
            "source": self.source,
            "confidence_score": self.confidence_score,
            "confidence_band": self.confidence_band,
            "stable_cavity_count": self.stable_cavity_count,
            "observed_max_cavity_count": self.observed_max_cavity_count,
            "sample_days": self.sample_days,
            "mold_key": self.mold_key,
            "casing_type": self.casing_type,
            "technical_capacity": self.technical_capacity,
            "constraint_reason": self.constraint_reason,
            "model_key": self.model_key,
        }


@dataclass(frozen=True)
class AccelerationInfo:
    cpu_count: int
    worker_count: int
    numpy_available: bool
    sklearn_available: bool
    xgboost_available: bool
    gpu_available: bool
    gpu_name: str
    preferred_device: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_count": self.cpu_count,
            "worker_count": self.worker_count,
            "numpy_available": self.numpy_available,
            "sklearn_available": self.sklearn_available,
            "xgboost_available": self.xgboost_available,
            "gpu_available": self.gpu_available,
            "gpu_name": self.gpu_name,
            "preferred_device": self.preferred_device,
            "note": self.note,
        }


class FactoryResourceIntelligenceService:
    MODEL_VERSION = "MPPS-FRCI-V11.3"
    FEATURE_VERSION = "FRCI-FEATURES-3"

    @staticmethod
    def runtime_acceleration() -> AccelerationInfo:
        cpu = max(1, int(os.cpu_count() or 1))
        # Keep one logical core for the UI/OS on larger machines. For smaller PCs
        # use everything available so batch/backfill work remains practical.
        workers = cpu if cpu <= 4 else max(2, cpu - 1)

        numpy_ok = sklearn_ok = xgb_ok = False
        try:
            import numpy  # noqa: F401
            numpy_ok = True
        except Exception:
            pass
        try:
            import sklearn  # noqa: F401
            sklearn_ok = True
        except Exception:
            pass
        try:
            import xgboost  # noqa: F401
            xgb_ok = True
        except Exception:
            pass

        gpu_name = ""
        gpu_ok = False
        # NVIDIA detection is intentionally dependency-free. XGBoost GPU use is
        # attempted only when xgboost exists; otherwise CPU remains authoritative.
        try:
            if shutil.which("nvidia-smi"):
                proc = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    gpu_name = proc.stdout.strip().splitlines()[0].strip()
                    gpu_ok = True
        except Exception:
            pass

        device = "cuda" if gpu_ok and xgb_ok else "cpu"
        if device == "cuda":
            note = "GPU accelerator detected; supported global ML challengers may use CUDA."
        elif gpu_ok:
            note = "GPU detected, but optional XGBoost accelerator is not installed; CPU ML is active."
        else:
            note = "CPU-optimized ML active; deterministic SQL/import work remains CPU/RAM bound."
        return AccelerationInfo(
            cpu_count=cpu,
            worker_count=workers,
            numpy_available=numpy_ok,
            sklearn_available=sklearn_ok,
            xgboost_available=xgb_ok,
            gpu_available=gpu_ok,
            gpu_name=gpu_name,
            preferred_device=device,
            note=note,
        )

    @staticmethod
    def _safe_rows(session, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        try:
            with session.begin_nested():
                rows = session.execute(text(sql), params or {}).mappings().all()
            return [dict(r) for r in rows]
        except Exception:
            return []

    @staticmethod
    def _safe_row(session, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = FactoryResourceIntelligenceService._safe_rows(session, sql, params)
        return rows[0] if rows else {}

    @classmethod
    def ensure_schema(cls, session) -> None:
        # Normal tab navigation must not replay dozens of transactional DDL
        # statements.  A complete V11/V11.3 schema gets a cheap preflight fast path;
        # the full additive migration still runs automatically on a fresh/partial DB.
        try:
            preflight = session.execute(text(
                "SELECT to_regclass('public.mpps_fi_resource_registry') AS registry, "
                "to_regclass('public.mpps_fi_plan_allocations') AS allocations, "
                "to_regclass('public.mpps_fi_mold_profiles') AS molds, "
                "to_regclass('public.mpps_fi_state') AS state"
            )).mappings().first()
            if preflight and all(preflight.get(k) for k in ("registry", "allocations", "molds", "state")):
                return
        except Exception:
            # Fresh DB / non-PostgreSQL test context: fall through to additive DDL.
            pass

        statements = [
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_resource_registry (
                id BIGSERIAL PRIMARY KEY,
                resource_type VARCHAR(24) NOT NULL,
                resource_key TEXT NOT NULL,
                canonical_name TEXT NOT NULL DEFAULT '',
                parent_key TEXT NOT NULL DEFAULT '',
                lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                source_authority VARCHAR(30) NOT NULL DEFAULT 'OVEN_LEARNING',
                first_seen_date DATE,
                last_seen_date DATE,
                observed_workbooks INTEGER NOT NULL DEFAULT 0,
                observed_days INTEGER NOT NULL DEFAULT 0,
                confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0,
                aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                last_import_run_id BIGINT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(resource_type, resource_key)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_resource_registry_type_status
            ON mpps_fi_resource_registry(resource_type, lifecycle_status, last_seen_date DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_plan_allocations (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT NOT NULL,
                plan_date DATE NOT NULL,
                source_workbook TEXT NOT NULL DEFAULT '',
                source_sheet TEXT NOT NULL DEFAULT 'OVEN',
                source_row INTEGER NOT NULL,
                allocation_slot INTEGER NOT NULL DEFAULT 1,
                line_name TEXT NOT NULL DEFAULT '',
                cavity_code TEXT NOT NULL DEFAULT '',
                sap_code TEXT NOT NULL,
                item_description TEXT NOT NULL DEFAULT '',
                shift_name VARCHAR(16) NOT NULL,
                planned_qty INTEGER NOT NULL DEFAULT 0,
                today_qty INTEGER NOT NULL DEFAULT 0,
                total_to_produce_qty INTEGER NOT NULL DEFAULT 0,
                next_day_qty INTEGER NOT NULL DEFAULT 0,
                unit_weight_kg NUMERIC(18,5) NOT NULL DEFAULT 0,
                mold_key TEXT NOT NULL DEFAULT '',
                mold_code TEXT NOT NULL DEFAULT '',
                casing_type TEXT NOT NULL DEFAULT '',
                casing_evidence TEXT NOT NULL DEFAULT '',
                evidence_confidence NUMERIC(10,6) NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(import_run_id, plan_date, source_row, shift_name)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_plan_allocations_date_sap
            ON mpps_fi_plan_allocations(plan_date, sap_code, cavity_code, line_name)
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_plan_allocations_resource
            ON mpps_fi_plan_allocations(cavity_code, plan_date, sap_code)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_daily_sap_resource_plan (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT NOT NULL,
                plan_date DATE NOT NULL,
                sap_code TEXT NOT NULL,
                item_description TEXT NOT NULL DEFAULT '',
                day_plan_qty INTEGER NOT NULL DEFAULT 0,
                night_plan_qty INTEGER NOT NULL DEFAULT 0,
                total_plan_qty INTEGER NOT NULL DEFAULT 0,
                today_qty_evidence INTEGER NOT NULL DEFAULT 0,
                distinct_cavity_count INTEGER NOT NULL DEFAULT 0,
                allocation_slot_count INTEGER NOT NULL DEFAULT 0,
                distinct_line_count INTEGER NOT NULL DEFAULT 0,
                primary_line TEXT NOT NULL DEFAULT '',
                mold_key TEXT NOT NULL DEFAULT '',
                mold_code TEXT NOT NULL DEFAULT '',
                casing_type TEXT NOT NULL DEFAULT '',
                lines_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                cavities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                source_workbook TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(import_run_id, plan_date, sap_code)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_daily_sap_resource_plan_date_sap
            ON mpps_fi_daily_sap_resource_plan(plan_date, sap_code, import_run_id DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_execution_observations (
                production_date DATE NOT NULL,
                sap_code TEXT NOT NULL,
                item_description TEXT NOT NULL DEFAULT '',
                plan_import_run_id BIGINT,
                actual_import_run_id BIGINT,
                planned_day_qty INTEGER NOT NULL DEFAULT 0,
                planned_night_qty INTEGER NOT NULL DEFAULT 0,
                planned_total_qty INTEGER NOT NULL DEFAULT 0,
                actual_day_qty INTEGER NOT NULL DEFAULT 0,
                actual_night_qty INTEGER NOT NULL DEFAULT 0,
                actual_total_qty INTEGER NOT NULL DEFAULT 0,
                completion_ratio NUMERIC(12,6) NOT NULL DEFAULT 0,
                distinct_cavity_count INTEGER NOT NULL DEFAULT 0,
                allocation_slot_count INTEGER NOT NULL DEFAULT 0,
                distinct_line_count INTEGER NOT NULL DEFAULT 0,
                primary_line TEXT NOT NULL DEFAULT '',
                mold_key TEXT NOT NULL DEFAULT '',
                mold_code TEXT NOT NULL DEFAULT '',
                casing_type TEXT NOT NULL DEFAULT '',
                plan_source_workbook TEXT NOT NULL DEFAULT '',
                actual_source_workbook TEXT NOT NULL DEFAULT '',
                evidence_confidence NUMERIC(10,6) NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(production_date, sap_code)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_execution_obs_sap_date
            ON mpps_fi_execution_observations(sap_code, production_date)
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_execution_obs_mold_date
            ON mpps_fi_execution_observations(mold_key, production_date)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_capacity_profiles (
                id BIGSERIAL PRIMARY KEY,
                profile_key TEXT NOT NULL UNIQUE,
                model_level VARCHAR(30) NOT NULL,
                entity_key TEXT NOT NULL,
                sample_days INTEGER NOT NULL DEFAULT 0,
                safe_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                expected_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                stretch_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                recent_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                median_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                day_share NUMERIC(10,6) NOT NULL DEFAULT 0.5,
                stable_cavity_count INTEGER NOT NULL DEFAULT 0,
                observed_max_cavity_count INTEGER NOT NULL DEFAULT 0,
                typical_allocation_slots NUMERIC(10,4) NOT NULL DEFAULT 0,
                validation_wape_pct NUMERIC(10,4) NOT NULL DEFAULT 100,
                stability_score NUMERIC(10,6) NOT NULL DEFAULT 0,
                trend_score NUMERIC(10,6) NOT NULL DEFAULT 0,
                confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0,
                confidence_band VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                model_kind VARCHAR(50) NOT NULL DEFAULT 'ROBUST_ENSEMBLE',
                feature_version VARCHAR(40) NOT NULL DEFAULT '',
                model_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                last_trained_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_capacity_profiles_level
            ON mpps_fi_capacity_profiles(model_level, confidence_score DESC, sample_days DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_resource_compatibility (
                id BIGSERIAL PRIMARY KEY,
                relation_type VARCHAR(40) NOT NULL,
                left_key TEXT NOT NULL,
                right_key TEXT NOT NULL,
                observed_days INTEGER NOT NULL DEFAULT 0,
                total_actual_qty INTEGER NOT NULL DEFAULT 0,
                avg_actual_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                first_seen_date DATE,
                last_seen_date DATE,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(relation_type, left_key, right_key)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_resource_compatibility_lookup
            ON mpps_fi_resource_compatibility(relation_type, left_key, confidence_score DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_mold_shift_usage (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT NOT NULL,
                plan_date DATE NOT NULL,
                shift_name VARCHAR(16) NOT NULL,
                mold_code TEXT NOT NULL,
                distinct_cavity_count INTEGER NOT NULL DEFAULT 0,
                planned_qty INTEGER NOT NULL DEFAULT 0,
                sap_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                source_workbook TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(import_run_id, plan_date, shift_name, mold_code)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_fi_mold_shift_usage_code_date
            ON mpps_fi_mold_shift_usage(mold_code, plan_date, shift_name)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_mold_profiles (
                mold_code TEXT PRIMARY KEY,
                max_mold INTEGER NOT NULL DEFAULT 0,
                average_use NUMERIC(12,4) NOT NULL DEFAULT 0,
                normal_production_average NUMERIC(18,4) NOT NULL DEFAULT 0,
                active_shift_count INTEGER NOT NULL DEFAULT 0,
                actual_shift_samples INTEGER NOT NULL DEFAULT 0,
                related_saps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                status VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                last_seen_date DATE,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_model_runs (
                id BIGSERIAL PRIMARY KEY,
                model_version TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                model_family TEXT NOT NULL,
                device TEXT NOT NULL DEFAULT 'cpu',
                training_start DATE,
                training_end DATE,
                sample_count INTEGER NOT NULL DEFAULT 0,
                validation_wape_pct NUMERIC(10,4) NOT NULL DEFAULT 100,
                validation_mae NUMERIC(18,5) NOT NULL DEFAULT 0,
                promoted BOOLEAN NOT NULL DEFAULT FALSE,
                metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_fi_state (
                id INTEGER PRIMARY KEY,
                model_version TEXT NOT NULL DEFAULT 'MPPS-FRCI-V11.3',
                latest_plan_date DATE,
                resource_observations INTEGER NOT NULL DEFAULT 0,
                execution_observations INTEGER NOT NULL DEFAULT 0,
                capacity_profiles INTEGER NOT NULL DEFAULT 0,
                high_confidence_profiles INTEGER NOT NULL DEFAULT 0,
                last_training_device TEXT NOT NULL DEFAULT 'cpu',
                last_training_at TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            INSERT INTO mpps_fi_state(id, model_version)
            VALUES (1, 'MPPS-FRCI-V11.3')
            ON CONFLICT (id) DO NOTHING
            """,
            # First-class line name in the operational oven table. Old databases
            # keep source_note for audit but new planning logic no longer has to
            # parse line=... from free text.
            "ALTER TABLE mpps_oven_plan ADD COLUMN IF NOT EXISTS line_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_oven_plan ADD COLUMN IF NOT EXISTS cavity_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_oven_plan ADD COLUMN IF NOT EXISTS allocation_slot INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE mpps_oven_plan ADD COLUMN IF NOT EXISTS mold_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_fi_plan_allocations ADD COLUMN IF NOT EXISTS mold_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_fi_daily_sap_resource_plan ADD COLUMN IF NOT EXISTS mold_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_fi_execution_observations ADD COLUMN IF NOT EXISTS mold_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_fi_resource_compatibility ADD COLUMN IF NOT EXISTS first_seen_date DATE",
            "ALTER TABLE mpps_fi_resource_compatibility ADD COLUMN IF NOT EXISTS evidence_count INTEGER NOT NULL DEFAULT 0",
            "CREATE INDEX IF NOT EXISTS ix_mpps_oven_plan_line_date ON mpps_oven_plan(plan_date, line_name)",
        ]
        for statement in statements:
            session.execute(text(statement))

    @staticmethod
    def _smds_map(session, sap_codes: Iterable[str]) -> dict[str, dict[str, Any]]:
        codes = sorted({_code(x) for x in sap_codes if _code(x)})
        if not codes:
            return {}
        # Query all SMDS rows once; SAP master is only a few thousand rows and this
        # avoids driver-specific ARRAY binds on older factory PCs.
        rows = FactoryResourceIntelligenceService._safe_rows(
            session,
            """
            SELECT TRIM(sap_code) AS sap_code,
                   COALESCE(material_description,'') AS material_description,
                   COALESCE(key_code,'') AS key_code,
                   COALESCE(casing_type,'') AS casing_type,
                   COALESCE(total_plan,0) AS total_plan
            FROM smds
            WHERE TRIM(COALESCE(sap_code,'')) <> ''
            """,
        )
        wanted = set(codes)
        return {_code(r["sap_code"]): r for r in rows if _code(r.get("sap_code")) in wanted}

    @classmethod
    def seed_technical_registry(cls, session) -> dict[str, int]:
        """Seed the learning registry from the current non-destructive technical masters.

        This makes the V11 UI complete immediately after upgrade (including free
        cavity positions that have no SAP in today's plan) while OVEN history is
        still the authority that raises learning confidence over time.
        """
        cls.ensure_schema(session)
        latest = cls._safe_row(
            session,
            "SELECT MAX(plan_date) AS d FROM mpps_oven_plan",
        ).get("d")
        latest = latest or date.today()

        resources: list[tuple[str, str, str, str, str, dict[str, Any]]] = []
        for row in cls._safe_rows(session, "SELECT line_name, status, remarks FROM production_lines"):
            name = _text(row.get("line_name"))
            if not name:
                continue
            status = _norm(row.get("status"))
            lifecycle = "RETIRED" if status == "RETIRED" else ("DORMANT" if status in {"INACTIVE","DORMANT"} else "ACTIVE")
            resources.append(("LINE", _norm(name), name, "", lifecycle, {"technical_status": row.get("status") or "Active"}))

        for row in cls._safe_rows(session, "SELECT line_name, cavity_no, cavity_code, status FROM production_line_cavities"):
            line = _text(row.get("line_name"))
            code = _text(row.get("cavity_code")) or f"CAVITY-{_i(row.get('cavity_no'))}"
            if not line or not code:
                continue
            status = _norm(row.get("status"))
            lifecycle = "RETIRED" if status == "RETIRED" else ("DORMANT" if status in {"INACTIVE","DORMANT"} else "ACTIVE")
            resources.append(("CAVITY", f"{_norm(line)}|{_norm(code)}", code, _norm(line), lifecycle, {"line_name": line, "technical_status": row.get("status") or "Active"}))

        for row in cls._safe_rows(session, "SELECT mold_key_code, status, mold_count FROM mold_master"):
            key = _text(row.get("mold_key_code"))
            if not key:
                continue
            status = _norm(row.get("status"))
            lifecycle = "RETIRED" if status == "RETIRED" else ("DORMANT" if status in {"INACTIVE","DORMANT"} else "ACTIVE")
            resources.append(("MOLD", _norm(key), key, "", lifecycle, {"physical_count": _i(row.get("mold_count")), "technical_status": row.get("status") or "Active"}))

        for row in cls._safe_rows(session, "SELECT casing_type, status, casing_count, total_casing_count, available_casing_count FROM casing_master"):
            raw_key = _text(row.get("casing_type"))
            key = _canonical_casing(raw_key)
            if not key:
                continue
            status = _norm(row.get("status"))
            lifecycle = "RETIRED" if status == "RETIRED" else ("DORMANT" if status in {"INACTIVE","DORMANT"} else "ACTIVE")
            physical = max(_i(row.get("total_casing_count")), _i(row.get("casing_count")), _i(row.get("available_casing_count")))
            resources.append((
                "CASING", _norm(key), key, "", lifecycle,
                {
                    "physical_count": physical,
                    "technical_status": row.get("status") or "Active",
                    "source_alias": raw_key,
                    "virtual_no_casing": key == "No Casing",
                },
            ))

        for rtype, rkey, name, parent, lifecycle, metadata in resources:
            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_resource_registry(
                        resource_type, resource_key, canonical_name, parent_key,
                        lifecycle_status, source_authority, first_seen_date, last_seen_date,
                        observed_workbooks, observed_days, confidence_score, metadata_json,
                        updated_at
                    ) VALUES(
                        :rtype,:rkey,:name,:parent,:lifecycle,'TECHNICAL_REGISTER',
                        :d,:d,0,0,0.65,CAST(:metadata AS JSONB),CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(resource_type, resource_key) DO UPDATE SET
                        metadata_json=mpps_fi_resource_registry.metadata_json || EXCLUDED.metadata_json,
                        canonical_name=CASE WHEN BTRIM(mpps_fi_resource_registry.canonical_name)='' THEN EXCLUDED.canonical_name ELSE mpps_fi_resource_registry.canonical_name END,
                        parent_key=CASE WHEN BTRIM(mpps_fi_resource_registry.parent_key)='' THEN EXCLUDED.parent_key ELSE mpps_fi_resource_registry.parent_key END,
                        lifecycle_status=CASE WHEN mpps_fi_resource_registry.lifecycle_status='RETIRED' THEN 'RETIRED' ELSE mpps_fi_resource_registry.lifecycle_status END,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {"rtype": rtype, "rkey": rkey, "name": name, "parent": parent, "lifecycle": lifecycle, "d": latest, "metadata": json.dumps(metadata)},
            )
        return {"fi_technical_resources_seeded": len(resources)}

    @classmethod
    def capture_workbook_resources(
        cls,
        session,
        *,
        import_run_id: int,
        analysis,
        import_mode: str,
    ) -> dict[str, int]:
        """Persist OVEN allocation evidence before any aggregation."""
        cls.ensure_schema(session)
        oven_rows = list(getattr(analysis, "oven_rows", []) or [])
        if not oven_rows:
            return {"fi_plan_allocations": 0, "fi_daily_sap_plans": 0, "fi_resources_seen": 0}

        sap_map = cls._smds_map(session, [r.get("sap_code") for r in oven_rows])
        plan_date_text = str(getattr(analysis, "plan_date", "") or "")
        try:
            workbook_plan_date = date.fromisoformat(plan_date_text)
        except Exception:
            workbook_plan_date = None

        # Allocation slot numbers are source-row based. Repeated rows inside the
        # same physical cavity are preserved, but are not automatically promoted
        # to "physical mold count".
        slot_by_row: dict[tuple[str, str, int], int] = {}
        per_cavity_rows: dict[tuple[str, str], list[int]] = defaultdict(list)
        for row in oven_rows:
            line = _text(row.get("line_name"))
            cavity = _text(row.get("oven_code"))
            source_row = _i(row.get("source_row"))
            if source_row and source_row not in per_cavity_rows[(line, cavity)]:
                per_cavity_rows[(line, cavity)].append(source_row)
        for (line, cavity), rows in per_cavity_rows.items():
            for idx, source_row in enumerate(sorted(rows), start=1):
                slot_by_row[(line, cavity, source_row)] = idx

        inserted = 0
        structure_rows = list(getattr(analysis, "oven_resource_rows", []) or [])
        line_days: set[str] = {
            _text(r.get("line_name")) for r in structure_rows if _text(r.get("line_name"))
        }
        cavity_days: set[str] = {
            f"{_text(r.get('line_name'))}|{_text(r.get('cavity_code'))}"
            for r in structure_rows
            if _text(r.get("line_name")) and _text(r.get("cavity_code"))
        }
        sap_group: dict[tuple[date, str], dict[str, Any]] = {}
        mold_shift_group: dict[tuple[date, str, str], dict[str, Any]] = {}

        for row in oven_rows:
            sap = _code(row.get("sap_code"))
            if not sap:
                continue
            try:
                row_date = date.fromisoformat(str(row.get("plan_date")))
            except Exception:
                continue
            line = _text(row.get("line_name"))
            cavity = _text(row.get("oven_code"))
            source_row = _i(row.get("source_row"))
            shift = _norm(row.get("shift_name"))
            if shift not in {"DAY", "NIGHT", "NEXT DAY"}:
                continue
            slot = slot_by_row.get((line, cavity, source_row), 1)
            smds = sap_map.get(sap, {})
            mold_key = _text(smds.get("key_code"))
            mold_code = _text(row.get("mold_code"))
            casing_type = _canonical_casing(smds.get("casing_type"))
            casing_evidence = _canonical_casing(row.get("casing_evidence"))
            if not casing_type and casing_evidence:
                casing_type = casing_evidence

            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_plan_allocations (
                        import_run_id, plan_date, source_workbook, source_sheet,
                        source_row, allocation_slot, line_name, cavity_code,
                        sap_code, item_description, shift_name, planned_qty,
                        today_qty, total_to_produce_qty, next_day_qty,
                        unit_weight_kg, mold_key, mold_code, casing_type, casing_evidence,
                        evidence_confidence
                    ) VALUES (
                        :import_run_id, :plan_date, :source_workbook, :source_sheet,
                        :source_row, :allocation_slot, :line_name, :cavity_code,
                        :sap_code, :item_description, :shift_name, :planned_qty,
                        :today_qty, :total_to_produce_qty, :next_day_qty,
                        :unit_weight_kg, :mold_key, :mold_code, :casing_type, :casing_evidence,
                        :evidence_confidence
                    )
                    ON CONFLICT (import_run_id, plan_date, source_row, shift_name)
                    DO UPDATE SET
                        line_name=EXCLUDED.line_name,
                        cavity_code=EXCLUDED.cavity_code,
                        sap_code=EXCLUDED.sap_code,
                        item_description=EXCLUDED.item_description,
                        planned_qty=EXCLUDED.planned_qty,
                        today_qty=EXCLUDED.today_qty,
                        total_to_produce_qty=EXCLUDED.total_to_produce_qty,
                        next_day_qty=EXCLUDED.next_day_qty,
                        unit_weight_kg=EXCLUDED.unit_weight_kg,
                        mold_key=EXCLUDED.mold_key,
                        mold_code=EXCLUDED.mold_code,
                        casing_type=EXCLUDED.casing_type,
                        casing_evidence=EXCLUDED.casing_evidence,
                        allocation_slot=EXCLUDED.allocation_slot,
                        evidence_confidence=EXCLUDED.evidence_confidence
                    """
                ),
                {
                    "import_run_id": int(import_run_id),
                    "plan_date": row_date,
                    "source_workbook": str(getattr(analysis, "workbook_name", "") or ""),
                    "source_sheet": str(row.get("source_sheet") or "OVEN"),
                    "source_row": source_row,
                    "allocation_slot": slot,
                    "line_name": line,
                    "cavity_code": cavity,
                    "sap_code": sap,
                    "item_description": _text(row.get("description")),
                    "shift_name": shift,
                    "planned_qty": max(0, _i(row.get("planned_qty"))),
                    "today_qty": max(0, _i(row.get("today_qty"))),
                    "total_to_produce_qty": max(0, _i(row.get("total_to_produce_qty"))),
                    "next_day_qty": max(0, _i(row.get("next_day_qty"))),
                    "unit_weight_kg": max(0.0, _f(row.get("unit_weight_kg"))),
                    "mold_key": mold_key,
                    "mold_code": mold_code,
                    "casing_type": casing_type,
                    "casing_evidence": casing_evidence,
                    "evidence_confidence": 1.0 if smds else 0.82,
                },
            )
            inserted += 1
            if line:
                line_days.add(line)
            if cavity:
                cavity_days.add(f"{line}|{cavity}")

            if shift in {"DAY", "NIGHT"}:
                key = (row_date, sap)
                rec = sap_group.setdefault(
                    key,
                    {
                        "day": 0,
                        "night": 0,
                        "today_rows": {},
                        "description": _text(row.get("description")),
                        "cavities": set(),
                        "lines": Counter(),
                        "slots": set(),
                        "mold_key": mold_key,
                        "mold_codes": Counter(),
                        "casing_type": casing_type,
                    },
                )
                qty = max(0, _i(row.get("planned_qty")))
                rec["day" if shift == "DAY" else "night"] += qty
                rec["cavities"].add(cavity)
                rec["lines"][line] += qty
                rec["slots"].add((line, cavity, source_row))
                # TODAY is row-level evidence and must not be double-counted across
                # DAY/NIGHT records generated from the same source row.
                rec["today_rows"][source_row] = max(0, _i(row.get("today_qty")))
                if not rec["mold_key"] and mold_key:
                    rec["mold_key"] = mold_key
                if mold_code:
                    rec["mold_codes"][mold_code] += qty
                    mg = mold_shift_group.setdefault(
                        (row_date, shift, mold_code),
                        {"cavities": set(), "saps": set(), "planned_qty": 0},
                    )
                    if cavity:
                        mg["cavities"].add(cavity)
                    mg["saps"].add(sap)
                    mg["planned_qty"] += qty
                if not rec["casing_type"] and casing_type:
                    rec["casing_type"] = casing_type

        for (row_date, sap), rec in sap_group.items():
            primary_line = rec["lines"].most_common(1)[0][0] if rec["lines"] else ""
            lines = sorted(k for k in rec["lines"] if k)
            cavities = sorted(c for c in rec["cavities"] if c)
            day_qty = int(rec["day"])
            night_qty = int(rec["night"])
            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_daily_sap_resource_plan (
                        import_run_id, plan_date, sap_code, item_description,
                        day_plan_qty, night_plan_qty, total_plan_qty,
                        today_qty_evidence, distinct_cavity_count,
                        allocation_slot_count, distinct_line_count, primary_line,
                        mold_key, mold_code, casing_type, lines_json, cavities_json,
                        source_workbook, updated_at
                    ) VALUES (
                        :import_run_id, :plan_date, :sap_code, :item_description,
                        :day_plan_qty, :night_plan_qty, :total_plan_qty,
                        :today_qty_evidence, :distinct_cavity_count,
                        :allocation_slot_count, :distinct_line_count, :primary_line,
                        :mold_key, :mold_code, :casing_type, CAST(:lines_json AS JSONB),
                        CAST(:cavities_json AS JSONB), :source_workbook, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (import_run_id, plan_date, sap_code)
                    DO UPDATE SET
                        item_description=EXCLUDED.item_description,
                        day_plan_qty=EXCLUDED.day_plan_qty,
                        night_plan_qty=EXCLUDED.night_plan_qty,
                        total_plan_qty=EXCLUDED.total_plan_qty,
                        today_qty_evidence=EXCLUDED.today_qty_evidence,
                        distinct_cavity_count=EXCLUDED.distinct_cavity_count,
                        allocation_slot_count=EXCLUDED.allocation_slot_count,
                        distinct_line_count=EXCLUDED.distinct_line_count,
                        primary_line=EXCLUDED.primary_line,
                        mold_key=EXCLUDED.mold_key,
                        mold_code=EXCLUDED.mold_code,
                        casing_type=EXCLUDED.casing_type,
                        lines_json=EXCLUDED.lines_json,
                        cavities_json=EXCLUDED.cavities_json,
                        source_workbook=EXCLUDED.source_workbook,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {
                    "import_run_id": int(import_run_id),
                    "plan_date": row_date,
                    "sap_code": sap,
                    "item_description": rec["description"],
                    "day_plan_qty": day_qty,
                    "night_plan_qty": night_qty,
                    "total_plan_qty": day_qty + night_qty,
                    "today_qty_evidence": sum(rec["today_rows"].values()),
                    "distinct_cavity_count": len(cavities),
                    "allocation_slot_count": len(rec["slots"]),
                    "distinct_line_count": len(lines),
                    "primary_line": primary_line,
                    "mold_key": rec["mold_key"],
                    "mold_code": (rec["mold_codes"].most_common(1)[0][0] if rec["mold_codes"] else ""),
                    "casing_type": rec["casing_type"],
                    "lines_json": json.dumps(lines),
                    "cavities_json": json.dumps(cavities),
                    "source_workbook": str(getattr(analysis, "workbook_name", "") or ""),
                },
            )

        # BAND mold-code shift usage. One unique row per workbook/date/shift/mold
        # prevents duplicate master memory while retaining dated observations.
        for (usage_date, usage_shift, mold_code), usage in mold_shift_group.items():
            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_mold_shift_usage(
                        import_run_id, plan_date, shift_name, mold_code,
                        distinct_cavity_count, planned_qty, sap_codes_json,
                        source_workbook, updated_at
                    ) VALUES(
                        :run_id,:plan_date,:shift_name,:mold_code,
                        :cavity_count,:planned_qty,CAST(:saps AS JSONB),
                        :source_workbook,CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(import_run_id, plan_date, shift_name, mold_code)
                    DO UPDATE SET
                        distinct_cavity_count=EXCLUDED.distinct_cavity_count,
                        planned_qty=EXCLUDED.planned_qty,
                        sap_codes_json=EXCLUDED.sap_codes_json,
                        source_workbook=EXCLUDED.source_workbook,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {
                    "run_id": int(import_run_id),
                    "plan_date": usage_date,
                    "shift_name": usage_shift,
                    "mold_code": mold_code,
                    "cavity_count": len(usage["cavities"]),
                    "planned_qty": int(usage["planned_qty"]),
                    "saps": json.dumps(sorted(usage["saps"])),
                    "source_workbook": str(getattr(analysis, "workbook_name", "") or ""),
                },
            )

        # Self-learning resource registry.
        if workbook_plan_date:
            reference_molds = {
                _text(r.get("mold_code"))
                for r in (getattr(analysis, "band_rows", []) or [])
                if _text(r.get("mold_code"))
            }
            reference_molds.update(
                _text(r.get("mold_code")) for r in oven_rows if _text(r.get("mold_code"))
            )
            cls._update_resource_registry(
                session,
                import_run_id=import_run_id,
                plan_date=workbook_plan_date,
                lines=line_days,
                cavities=cavity_days,
                sap_map=sap_map,
                import_mode=import_mode,
                reference_molds=reference_molds,
            )
            cls._sync_discovered_technical_resources(
                session, lines=line_days, cavities=cavity_days
            )
            cls.refresh_resource_lifecycle(session, latest_plan_date=workbook_plan_date)
        return {
            "fi_plan_allocations": inserted,
            "fi_daily_sap_plans": len(sap_group),
            "fi_resources_seen": len(line_days) + len(cavity_days),
            "fi_mold_shift_usage": len(mold_shift_group),
        }

    @classmethod
    def _update_resource_registry(
        cls,
        session,
        *,
        import_run_id: int,
        plan_date: date,
        lines: set[str],
        cavities: set[str],
        sap_map: dict[str, dict[str, Any]],
        import_mode: str,
        reference_molds: set[str] | None = None,
    ) -> None:
        resources: list[tuple[str, str, str, str, dict[str, Any]]] = []
        for line in lines:
            resources.append(("LINE", _norm(line), line, "", {}))
        for pair in cavities:
            line, cavity = pair.split("|", 1)
            resources.append(("CAVITY", f"{_norm(line)}|{_norm(cavity)}", cavity, _norm(line), {"line_name": line}))
        for mold in sorted(reference_molds or set()):
            if mold:
                resources.append(("MOLD", _norm(mold), mold, "", {"authority": "BAND_MATERIAL_DESCRIPTION"}))
        for sap, row in sap_map.items():
            mold = _text(row.get("key_code"))
            casing = _canonical_casing(row.get("casing_type"))
            if mold:
                resources.append(("MOLD", _norm(mold), mold, "", {"sap_example": sap}))
            if casing:
                resources.append((
                    "CASING", _norm(casing), casing, "",
                    {"sap_example": sap, "virtual_no_casing": casing == "No Casing"},
                ))

        for resource_type, resource_key, canonical_name, parent_key, metadata in resources:
            if not resource_key:
                continue
            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_resource_registry (
                        resource_type, resource_key, canonical_name, parent_key,
                        lifecycle_status, source_authority, first_seen_date,
                        last_seen_date, observed_workbooks, observed_days,
                        confidence_score, metadata_json, last_import_run_id,
                        updated_at
                    ) VALUES (
                        :resource_type, :resource_key, :canonical_name, :parent_key,
                        'LEARNING', :source_authority, :plan_date, :plan_date,
                        1, 1, :confidence_score, CAST(:metadata_json AS JSONB),
                        :last_import_run_id, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (resource_type, resource_key)
                    DO UPDATE SET
                        canonical_name = CASE
                            WHEN BTRIM(mpps_fi_resource_registry.canonical_name) = ''
                            THEN EXCLUDED.canonical_name
                            ELSE mpps_fi_resource_registry.canonical_name END,
                        parent_key = CASE
                            WHEN BTRIM(mpps_fi_resource_registry.parent_key) = ''
                            THEN EXCLUDED.parent_key
                            ELSE mpps_fi_resource_registry.parent_key END,
                        last_seen_date = GREATEST(
                            COALESCE(mpps_fi_resource_registry.last_seen_date, EXCLUDED.last_seen_date),
                            EXCLUDED.last_seen_date
                        ),
                        observed_workbooks = CASE
                            WHEN mpps_fi_resource_registry.last_import_run_id IS DISTINCT FROM EXCLUDED.last_import_run_id
                            THEN mpps_fi_resource_registry.observed_workbooks + 1
                            ELSE mpps_fi_resource_registry.observed_workbooks END,
                        observed_days = CASE
                            WHEN mpps_fi_resource_registry.last_seen_date IS DISTINCT FROM EXCLUDED.last_seen_date
                            THEN mpps_fi_resource_registry.observed_days + 1
                            ELSE mpps_fi_resource_registry.observed_days END,
                        lifecycle_status = CASE
                            -- A future OVEN plan is stronger evidence than an old
                            -- ML retirement state: learned resources auto-reactivate.
                            WHEN GREATEST(mpps_fi_resource_registry.observed_workbooks, 1) + 1 >= 3
                            THEN 'ACTIVE'
                            ELSE 'LEARNING' END,
                        confidence_score = LEAST(
                            0.99,
                            0.45 + 0.07 * (
                                CASE
                                WHEN mpps_fi_resource_registry.last_import_run_id IS DISTINCT FROM EXCLUDED.last_import_run_id
                                THEN mpps_fi_resource_registry.observed_workbooks + 1
                                ELSE mpps_fi_resource_registry.observed_workbooks END
                            )
                        ),
                        metadata_json = mpps_fi_resource_registry.metadata_json || EXCLUDED.metadata_json,
                        last_import_run_id = EXCLUDED.last_import_run_id,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    "resource_type": resource_type,
                    "resource_key": resource_key,
                    "canonical_name": canonical_name,
                    "parent_key": parent_key,
                    "source_authority": "LIVE_OVEN" if _norm(import_mode) == "LIVE" else "HISTORICAL_OVEN",
                    "plan_date": plan_date,
                    "confidence_score": 0.52,
                    "metadata_json": json.dumps(metadata),
                    "last_import_run_id": int(import_run_id),
                },
            )

    @classmethod
    def refresh_resource_lifecycle(
        cls, session, *, latest_plan_date: date, stale_days: int = 45
    ) -> None:
        """Age learned registry entries without deleting historical evidence.

        A resource not observed recently becomes DORMANT in the learning registry.
        We intentionally do not hard-disable the physical technical register here:
        an unused cavity can simply have no plan today.
        """
        cls.ensure_schema(session)
        # Evidence-based lifecycle aging. Nothing is deleted; a later OVEN
        # allocation automatically reactivates the resource in _update_resource_registry.
        session.execute(
            text(
                """
                UPDATE mpps_fi_resource_registry
                SET lifecycle_status = CASE
                    WHEN (:latest_plan_date - last_seen_date) > 365
                         AND observed_days >= 20 THEN 'RETIRED'
                    WHEN (:latest_plan_date - last_seen_date) > 180
                         AND observed_days >= 10 THEN 'RETIREMENT CANDIDATE'
                    WHEN (:latest_plan_date - last_seen_date) > :stale_days
                         THEN 'DORMANT'
                    ELSE lifecycle_status
                END,
                updated_at=CURRENT_TIMESTAMP
                WHERE last_seen_date IS NOT NULL
                  AND lifecycle_status NOT IN ('REVIEW')
                """
            ),
            {"latest_plan_date": latest_plan_date, "stale_days": int(stale_days)},
        )

    @classmethod
    def _sync_discovered_technical_resources(
        cls, session, *, lines: set[str], cavities: set[str]
    ) -> None:
        """Project learned OVEN resources into the existing technical registers.

        First sighting is LEARNING.  After the registry reaches ACTIVE confidence,
        the resource becomes available to operational planning automatically.
        Existing Retired/Breakdown technical decisions are never overwritten.
        """
        session.execute(text(
            """
            CREATE TABLE IF NOT EXISTS production_lines (
                id VARCHAR(64) PRIMARY KEY,
                line_name VARCHAR(255) NOT NULL UNIQUE,
                status VARCHAR(32) NOT NULL DEFAULT 'Active',
                remarks TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))
        session.execute(text(
            """
            CREATE TABLE IF NOT EXISTS production_line_cavities (
                id BIGSERIAL PRIMARY KEY,
                line_name VARCHAR(255) NOT NULL,
                cavity_no INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'Active',
                assigned_tyre_item VARCHAR(255) NOT NULL DEFAULT '',
                remarks TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(line_name, cavity_no)
            )
            """
        ))
        session.execute(text("ALTER TABLE production_line_cavities ADD COLUMN IF NOT EXISTS cavity_code VARCHAR(255) NOT NULL DEFAULT ''"))
        session.execute(text("ALTER TABLE production_line_cavities ADD COLUMN IF NOT EXISTS display_order INTEGER NOT NULL DEFAULT 0"))

        registry = cls._safe_rows(
            session,
            """
            SELECT resource_type, resource_key, canonical_name, parent_key,
                   lifecycle_status, observed_workbooks, confidence_score
            FROM mpps_fi_resource_registry
            WHERE resource_type IN ('LINE','CAVITY')
            """,
        )
        reg_map = {(r['resource_type'], r['resource_key']): r for r in registry}

        for line in sorted(lines):
            key = _norm(line)
            reg = reg_map.get(('LINE', key), {})
            learned_status = 'Active' if _norm(reg.get('lifecycle_status')) == 'ACTIVE' else 'Learning'
            existing = cls._safe_row(
                session,
                "SELECT id, status FROM production_lines WHERE LOWER(TRIM(line_name))=LOWER(TRIM(:line)) LIMIT 1",
                {'line': line},
            )
            if not existing:
                stable_id = 'FI-LINE-' + hashlib.sha1(key.encode('utf-8')).hexdigest()[:24]
                session.execute(
                    text(
                        """
                        INSERT INTO production_lines(id,line_name,status,remarks)
                        VALUES(:id,:line,:status,'Auto-discovered from OVEN workbook; managed by Factory Intelligence.')
                        ON CONFLICT (line_name) DO NOTHING
                        """
                    ),
                    {'id': stable_id, 'line': line, 'status': learned_status},
                )
            elif _norm(existing.get('status')) in {'LEARNING','DORMANT'} and learned_status == 'Active':
                session.execute(
                    text("UPDATE production_lines SET status='Active', updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                    {'id': existing['id']},
                )

        for pair in sorted(cavities):
            if '|' not in pair:
                continue
            line, cavity = pair.split('|', 1)
            reg_key = f"{_norm(line)}|{_norm(cavity)}"
            reg = reg_map.get(('CAVITY', reg_key), {})
            learned_status = 'Active' if _norm(reg.get('lifecycle_status')) == 'ACTIVE' else 'Learning'
            existing = cls._safe_row(
                session,
                """
                SELECT id, status FROM production_line_cavities
                WHERE LOWER(TRIM(line_name))=LOWER(TRIM(:line))
                  AND LOWER(TRIM(COALESCE(cavity_code,'')))=LOWER(TRIM(:cavity))
                LIMIT 1
                """,
                {'line': line, 'cavity': cavity},
            )
            if not existing:
                max_row = cls._safe_row(
                    session,
                    "SELECT COALESCE(MAX(cavity_no),0) AS max_no FROM production_line_cavities WHERE LOWER(TRIM(line_name))=LOWER(TRIM(:line))",
                    {'line': line},
                )
                cavity_no = max(1, _i(max_row.get('max_no')) + 1)
                session.execute(
                    text(
                        """
                        INSERT INTO production_line_cavities(
                            line_name,cavity_no,cavity_code,display_order,status,remarks
                        ) VALUES(
                            :line,:cavity_no,:cavity,:display_order,:status,
                            'Auto-discovered from OVEN workbook; learned resource evidence retained.'
                        )
                        ON CONFLICT (line_name,cavity_no) DO NOTHING
                        """
                    ),
                    {
                        'line': line, 'cavity_no': cavity_no, 'cavity': cavity,
                        'display_order': cavity_no, 'status': learned_status,
                    },
                )
            elif _norm(existing.get('status')) in {'LEARNING','DORMANT'} and learned_status == 'Active':
                session.execute(
                    text("UPDATE production_line_cavities SET status='Active', updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                    {'id': existing['id']},
                )

    @classmethod
    def sync_operational_oven_columns(cls, session, *, import_run_id: int) -> None:
        """Backfill first-class line/cavity columns in mpps_oven_plan."""
        cls.ensure_schema(session)
        session.execute(
            text(
                """
                UPDATE mpps_oven_plan op
                SET line_name = src.line_name,
                    cavity_code = src.cavity_code,
                    allocation_slot = src.allocation_slot,
                    mold_code = src.mold_code
                FROM (
                    SELECT DISTINCT ON (plan_date, source_row)
                           plan_date, source_row, line_name, cavity_code, allocation_slot, mold_code
                    FROM mpps_fi_plan_allocations
                    WHERE import_run_id = :run_id
                    ORDER BY plan_date, source_row, id
                ) src
                WHERE op.plan_date = src.plan_date
                  AND op.source_row = src.source_row
                  AND op.source_workbook = (
                      SELECT workbook_name FROM excel_import_runs WHERE id = :run_id
                  )
                """
            ),
            {"run_id": int(import_run_id)},
        )

    @classmethod
    def bootstrap_existing_history(cls, session) -> dict[str, int]:
        """Migrate already-imported V10 OVEN history into the V11 observation layer.

        This is intentionally one-way and non-destructive. It lets the new
        intelligence pages become useful immediately after upgrade instead of
        waiting for the next daily workbook.
        """
        cls.ensure_schema(session)
        count = cls._safe_row(session, "SELECT COUNT(*) AS c FROM mpps_fi_plan_allocations")
        if _i(count.get("c")) > 0:
            return {"fi_bootstrap_runs": 0, "fi_bootstrap_rows": 0}

        run_rows = cls._safe_rows(
            session,
            """
            SELECT id, workbook_name, plan_date, confidence_score, status
            FROM excel_import_runs
            WHERE status IN ('COMMITTED','COMMITTED WITH WARNINGS')
              AND rollback_at IS NULL
              AND TRIM(COALESCE(workbook_name,'')) <> ''
            ORDER BY plan_date, id
            """,
        )
        if not run_rows:
            return {"fi_bootstrap_runs": 0, "fi_bootstrap_rows": 0}

        oven_rows = cls._safe_rows(
            session,
            """
            SELECT plan_date, oven_code, shift_name, material_code,
                   item_description, planned_qty, planned_weight_kg,
                   source_workbook, source_sheet, source_row, source_note,
                   line_name, cavity_code, allocation_slot, mold_code
            FROM mpps_oven_plan
            WHERE planned_qty > 0
            ORDER BY source_workbook, plan_date, source_row, shift_name
            """,
        )
        by_book: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in oven_rows:
            by_book[str(row.get("source_workbook") or "")].append(row)

        migrated_runs = 0
        migrated_rows = 0
        for run in run_rows:
            workbook_name = str(run.get("workbook_name") or "")
            rows = by_book.get(workbook_name, [])
            if not rows:
                continue
            reconstructed = []
            for row in rows:
                line = _text(row.get("line_name"))
                if not line:
                    note = str(row.get("source_note") or "")
                    match = re.search(r"(?:^|;)\\s*line=([^;]+)", note, re.I)
                    if match:
                        line = _text(match.group(1))
                cavity = _text(row.get("cavity_code") or row.get("oven_code"))
                planned = max(0, _i(row.get("planned_qty")))
                unit_weight = (
                    max(0.0, _f(row.get("planned_weight_kg"))) / planned
                    if planned > 0 else 0.0
                )
                reconstructed.append({
                    "plan_date": row.get("plan_date").isoformat()
                        if hasattr(row.get("plan_date"), "isoformat")
                        else str(row.get("plan_date") or ""),
                    "line_name": line,
                    "oven_code": cavity,
                    "shift_name": row.get("shift_name") or "",
                    "sap_code": row.get("material_code") or "",
                    "description": row.get("item_description") or "",
                    "planned_qty": planned,
                    "today_qty": 0,
                    "total_to_produce_qty": 0,
                    "next_day_qty": planned if _norm(row.get("shift_name")) == "NEXT DAY" else 0,
                    "planned_weight_kg": _f(row.get("planned_weight_kg")),
                    "unit_weight_kg": unit_weight,
                    "casing_evidence": "",
                    "mold_code": row.get("mold_code") or "",
                    "source_sheet": row.get("source_sheet") or "OVEN",
                    "source_row": _i(row.get("source_row")),
                })
            if not reconstructed:
                continue
            plan_date_value = run.get("plan_date")
            analysis = SimpleNamespace(
                oven_rows=reconstructed,
                workbook_name=workbook_name,
                plan_date=(
                    plan_date_value.isoformat()
                    if hasattr(plan_date_value, "isoformat")
                    else str(plan_date_value or "")
                ),
            )
            result = cls.capture_workbook_resources(
                session,
                import_run_id=_i(run.get("id")),
                analysis=analysis,
                import_mode="HISTORICAL",
            )
            migrated_runs += 1
            migrated_rows += _i(result.get("fi_plan_allocations"))

        return {
            "fi_bootstrap_runs": migrated_runs,
            "fi_bootstrap_rows": migrated_rows,
        }

    @classmethod
    def rebuild_execution_observations(cls, session) -> dict[str, int]:
        """Join latest resource plan for a date/SAP to verified actual PROD."""
        cls.ensure_schema(session)
        session.execute(
            text(
                """
                WITH latest_plan AS (
                    SELECT DISTINCT ON (p.plan_date, p.sap_code)
                           p.*
                    FROM mpps_fi_daily_sap_resource_plan p
                    JOIN excel_import_runs r ON r.id = p.import_run_id
                    WHERE r.status IN ('COMMITTED','COMMITTED WITH WARNINGS')
                      AND r.rollback_at IS NULL
                    ORDER BY p.plan_date, p.sap_code, p.import_run_id DESC
                ),
                latest_actual AS (
                    SELECT a.*
                    FROM mpps_actual_production a
                    JOIN mpps_actual_production_dates d
                      ON d.production_date = a.production_date
                     AND d.source_import_run_id = a.source_import_run_id
                    WHERE d.is_complete = TRUE
                )
                INSERT INTO mpps_fi_execution_observations (
                    production_date, sap_code, item_description,
                    plan_import_run_id, actual_import_run_id,
                    planned_day_qty, planned_night_qty, planned_total_qty,
                    actual_day_qty, actual_night_qty, actual_total_qty,
                    completion_ratio, distinct_cavity_count,
                    allocation_slot_count, distinct_line_count, primary_line,
                    mold_key, mold_code, casing_type, plan_source_workbook,
                    actual_source_workbook, evidence_confidence, updated_at
                )
                SELECT
                    p.plan_date,
                    p.sap_code,
                    COALESCE(NULLIF(p.item_description,''), a.item_description, ''),
                    p.import_run_id,
                    a.source_import_run_id,
                    p.day_plan_qty,
                    p.night_plan_qty,
                    p.total_plan_qty,
                    a.day_actual_qty,
                    a.night_actual_qty,
                    a.total_actual_qty,
                    CASE WHEN p.total_plan_qty > 0
                         THEN a.total_actual_qty::numeric / p.total_plan_qty
                         ELSE 0 END,
                    p.distinct_cavity_count,
                    p.allocation_slot_count,
                    p.distinct_line_count,
                    p.primary_line,
                    p.mold_key,
                    p.mold_code,
                    p.casing_type,
                    p.source_workbook,
                    a.source_workbook,
                    CASE
                        WHEN p.total_plan_qty > 0 AND a.total_actual_qty >= 0 THEN 1.0
                        ELSE 0.7 END,
                    CURRENT_TIMESTAMP
                FROM latest_plan p
                JOIN latest_actual a
                  ON a.production_date = p.plan_date
                 AND a.sap_code = p.sap_code
                ON CONFLICT (production_date, sap_code)
                DO UPDATE SET
                    item_description=EXCLUDED.item_description,
                    plan_import_run_id=EXCLUDED.plan_import_run_id,
                    actual_import_run_id=EXCLUDED.actual_import_run_id,
                    planned_day_qty=EXCLUDED.planned_day_qty,
                    planned_night_qty=EXCLUDED.planned_night_qty,
                    planned_total_qty=EXCLUDED.planned_total_qty,
                    actual_day_qty=EXCLUDED.actual_day_qty,
                    actual_night_qty=EXCLUDED.actual_night_qty,
                    actual_total_qty=EXCLUDED.actual_total_qty,
                    completion_ratio=EXCLUDED.completion_ratio,
                    distinct_cavity_count=EXCLUDED.distinct_cavity_count,
                    allocation_slot_count=EXCLUDED.allocation_slot_count,
                    distinct_line_count=EXCLUDED.distinct_line_count,
                    primary_line=EXCLUDED.primary_line,
                    mold_key=EXCLUDED.mold_key,
                    mold_code=EXCLUDED.mold_code,
                    casing_type=EXCLUDED.casing_type,
                    plan_source_workbook=EXCLUDED.plan_source_workbook,
                    actual_source_workbook=EXCLUDED.actual_source_workbook,
                    evidence_confidence=EXCLUDED.evidence_confidence,
                    updated_at=CURRENT_TIMESTAMP
                """
            )
        )
        row = cls._safe_row(session, "SELECT COUNT(*) AS c FROM mpps_fi_execution_observations")
        return {"fi_execution_observations": _i(row.get("c"))}

    @staticmethod
    def _fit_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
        rows = sorted(rows, key=lambda r: r["production_date"])
        totals = [max(0.0, _f(r.get("actual_total_qty"))) for r in rows]
        totals = [x for x in totals if x >= 0]
        sample_days = len(totals)
        if not totals:
            return {
                "sample_days": 0,
                "safe": 0.0,
                "expected": 0.0,
                "stretch": 0.0,
                "recent": 0.0,
                "median": 0.0,
                "day_share": 0.5,
                "stable_cavities": 0,
                "observed_max_cavities": 0,
                "typical_slots": 0.0,
                "wape": 100.0,
                "stability": 0.0,
                "trend": 0.0,
                "confidence": 0.0,
                "band": "COLD START",
                "weekday": {},
            }

        # Leakage-safe rolling validation. Prediction for each day is formed only
        # from earlier observations.
        history: list[float] = []
        weekday_hist: dict[int, list[float]] = defaultdict(list)
        ewma: float | None = None
        predictions: list[tuple[float, float]] = []
        alpha = 0.30
        for row in rows:
            d = row["production_date"]
            actual = max(0.0, _f(row.get("actual_total_qty")))
            if history:
                robust = median(history[-60:])
                recent = ewma if ewma is not None else robust
                wd = weekday_hist.get(d.weekday(), [])
                wd_est = median(wd[-12:]) if len(wd) >= 2 else robust
                pred = 0.45 * robust + 0.35 * recent + 0.20 * wd_est
                predictions.append((pred, actual))
            history.append(actual)
            weekday_hist[d.weekday()].append(actual)
            ewma = actual if ewma is None else alpha * actual + (1.0 - alpha) * ewma

        window = history[-90:]
        med = median(window)
        recent = ewma if ewma is not None else med
        expected = 0.55 * med + 0.45 * recent
        safe = min(expected, _quantile(window, 0.25, expected) if sample_days >= 5 else expected * 0.88)
        stretch = max(expected, _quantile(window, 0.85, expected))

        actual_total = sum(abs(a) for _, a in predictions)
        wape = (
            sum(abs(p - a) for p, a in predictions) / max(1.0, actual_total) * 100.0
            if predictions else 100.0
        )
        center = max(mean(window), 1.0)
        mad = mean(abs(v - center) for v in window) if len(window) >= 2 else center
        stability = _clamp(1.0 - mad / center, 0.0, 1.0)
        trend = 0.0
        if len(window) >= 8:
            old = mean(window[-8:-4])
            new = mean(window[-4:])
            trend = _clamp((new - old) / max(old, 1.0), -0.5, 0.5)
        validation = _clamp((100.0 - min(wape, 100.0)) / 100.0, 0.0, 1.0)
        sample_score = _clamp(sample_days / 45.0, 0.0, 1.0)
        confidence = _clamp(0.45 * sample_score + 0.35 * validation + 0.20 * stability, 0.0, 1.0)
        if sample_days < 5:
            band = "COLD START"
        elif confidence >= 0.82:
            band = "HIGH"
        elif confidence >= 0.62:
            band = "MEDIUM"
        else:
            band = "LOW"

        cavity_counts = [max(0, _i(r.get("distinct_cavity_count"))) for r in rows]
        slot_counts = [max(0, _i(r.get("allocation_slot_count"))) for r in rows]
        day_shares = [
            _clamp(_f(r.get("actual_day_qty")) / max(1.0, _f(r.get("actual_total_qty"))), 0.0, 1.0)
            for r in rows if _f(r.get("actual_total_qty")) > 0
        ]
        weekday = {
            str(k): {"median": round(median(v[-12:]), 3), "samples": len(v)}
            for k, v in weekday_hist.items() if v
        }
        return {
            "sample_days": sample_days,
            "safe": round(max(0.0, safe), 4),
            "expected": round(max(0.0, expected), 4),
            "stretch": round(max(0.0, stretch), 4),
            "recent": round(max(0.0, recent), 4),
            "median": round(max(0.0, med), 4),
            "day_share": round(mean(day_shares[-90:]), 6) if day_shares else 0.5,
            "stable_cavities": _stable_max(cavity_counts),
            "observed_max_cavities": max(cavity_counts or [0]),
            "typical_slots": round(median([v for v in slot_counts if v > 0]), 3) if any(slot_counts) else 0.0,
            "wape": round(wape, 4),
            "stability": round(stability, 6),
            "trend": round(trend, 6),
            "confidence": round(confidence, 6),
            "band": band,
            "weekday": weekday,
        }

    @classmethod
    def _upsert_profile(
        cls,
        session,
        *,
        model_level: str,
        entity_key: str,
        rows: list[dict[str, Any]],
        extra_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        model = cls._fit_profile(rows)
        model_key = f"{model_level}|{entity_key}"
        payload = {
            "model_version": cls.MODEL_VERSION,
            "feature_version": cls.FEATURE_VERSION,
            "algorithm": "robust quantile + EWMA + weekday leakage-safe ensemble",
            "weekday": model["weekday"],
            **(extra_json or {}),
        }
        session.execute(
            text(
                """
                INSERT INTO mpps_fi_capacity_profiles (
                    profile_key, model_level, entity_key, sample_days,
                    safe_capacity_qty, expected_capacity_qty, stretch_capacity_qty,
                    recent_capacity_qty, median_capacity_qty, day_share,
                    stable_cavity_count, observed_max_cavity_count,
                    typical_allocation_slots, validation_wape_pct,
                    stability_score, trend_score, confidence_score,
                    confidence_band, model_kind, feature_version, model_json,
                    last_trained_at, updated_at
                ) VALUES (
                    :profile_key, :model_level, :entity_key, :sample_days,
                    :safe, :expected, :stretch, :recent, :median, :day_share,
                    :stable_cavities, :observed_max_cavities, :typical_slots, :wape,
                    :stability, :trend, :confidence, :band,
                    'ROBUST_ENSEMBLE', :feature_version, CAST(:model_json AS JSONB),
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (profile_key)
                DO UPDATE SET
                    sample_days=EXCLUDED.sample_days,
                    safe_capacity_qty=EXCLUDED.safe_capacity_qty,
                    expected_capacity_qty=EXCLUDED.expected_capacity_qty,
                    stretch_capacity_qty=EXCLUDED.stretch_capacity_qty,
                    recent_capacity_qty=EXCLUDED.recent_capacity_qty,
                    median_capacity_qty=EXCLUDED.median_capacity_qty,
                    day_share=EXCLUDED.day_share,
                    stable_cavity_count=EXCLUDED.stable_cavity_count,
                    observed_max_cavity_count=EXCLUDED.observed_max_cavity_count,
                    typical_allocation_slots=EXCLUDED.typical_allocation_slots,
                    validation_wape_pct=EXCLUDED.validation_wape_pct,
                    stability_score=EXCLUDED.stability_score,
                    trend_score=EXCLUDED.trend_score,
                    confidence_score=EXCLUDED.confidence_score,
                    confidence_band=EXCLUDED.confidence_band,
                    model_kind=EXCLUDED.model_kind,
                    feature_version=EXCLUDED.feature_version,
                    model_json=EXCLUDED.model_json,
                    last_trained_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP
                """
            ),
            {
                "profile_key": model_key,
                "model_level": model_level,
                "entity_key": entity_key,
                "feature_version": cls.FEATURE_VERSION,
                "model_json": json.dumps(payload, default=str),
                **model,
            },
        )
        return {"profile_key": model_key, **model}

    @classmethod
    def train_profiles(cls, session) -> dict[str, Any]:
        cls.ensure_schema(session)
        seeded = cls.seed_technical_registry(session)
        bootstrap = cls.bootstrap_existing_history(session)
        rebuild = cls.rebuild_execution_observations(session)
        mold_profiles = cls.rebuild_mold_profiles(session)
        memory = cls.rebuild_resource_memory(session)
        rows = cls._safe_rows(
            session,
            """
            SELECT *
            FROM mpps_fi_execution_observations
            WHERE actual_total_qty >= 0
            ORDER BY production_date, sap_code
            """,
        )
        if not rows:
            return {**seeded, **bootstrap, **rebuild, **mold_profiles, **memory, "fi_capacity_profiles_trained": 0, "fi_high_confidence_profiles": 0}

        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        groups[("FACTORY", "FACTORY")] = rows
        for row in rows:
            sap = _code(row.get("sap_code"))
            if sap:
                groups[("SAP", sap)].append(row)
            mold = _norm(row.get("mold_key"))
            if mold:
                groups[("MOLD", mold)].append(row)
            casing = _norm(row.get("casing_type"))
            if casing and casing not in {"NO CASING", "-", "NONE", "N/A"}:
                groups[("CASING", casing)].append(row)
            line = _norm(row.get("primary_line"))
            if line:
                groups[("LINE", line)].append(row)
            cavity_count = _i(row.get("distinct_cavity_count"))
            if sap and cavity_count > 0:
                groups[("SAP_CAVITY", f"{sap}|{cavity_count}")].append(row)

        trained = 0
        high = 0
        for (level, key), subset in groups.items():
            extra = {}
            if level == "SAP":
                line_counts = Counter(_norm(r.get("primary_line")) for r in subset if _norm(r.get("primary_line")))
                extra["best_line"] = line_counts.most_common(1)[0][0] if line_counts else ""
                molds = Counter(_norm(r.get("mold_key")) for r in subset if _norm(r.get("mold_key")))
                extra["mold_key"] = molds.most_common(1)[0][0] if molds else ""
                casings = Counter(_canonical_casing(r.get("casing_type")) for r in subset if _canonical_casing(r.get("casing_type")))
                extra["casing_type"] = casings.most_common(1)[0][0] if casings else ""
                output_by_cavity: dict[int, list[int]] = defaultdict(list)
                for r in subset:
                    c = _i(r.get("distinct_cavity_count"))
                    if c > 0:
                        output_by_cavity[c].append(_i(r.get("actual_total_qty")))
                extra["cavity_output_curve"] = {
                    str(c): {
                        "samples": len(v),
                        "median_actual": round(median(v), 3),
                        "avg_actual": round(mean(v), 3),
                    }
                    for c, v in sorted(output_by_cavity.items())
                }
            model = cls._upsert_profile(
                session,
                model_level=level,
                entity_key=key,
                rows=subset,
                extra_json=extra,
            )
            trained += 1
            if model["band"] == "HIGH":
                high += 1

        compat = cls.rebuild_compatibility(session)
        acceleration = cls.runtime_acceleration()
        start_date = min(r["production_date"] for r in rows)
        end_date = max(r["production_date"] for r in rows)
        factory_model = cls._fit_profile(rows)

        # Optional nonlinear challenger. It uses time-ordered validation and is
        # promoted only when it beats the robust ensemble on later unseen data.
        try:
            from app.services.advanced_capacity_ml import AdvancedCapacityML
            advanced_result = AdvancedCapacityML().train(
                session,
                robust_wape=factory_model["wape"],
            )
        except Exception as exc:
            advanced_result = None
            advanced_error = str(exc)

        session.execute(
            text(
                """
                INSERT INTO mpps_fi_model_runs (
                    model_version, feature_version, model_family, device,
                    training_start, training_end, sample_count,
                    validation_wape_pct, validation_mae, promoted, metrics_json
                ) VALUES (
                    :model_version, :feature_version, 'ROBUST_RESOURCE_ENSEMBLE', :device,
                    :training_start, :training_end, :sample_count,
                    :wape, :mae, TRUE, CAST(:metrics AS JSONB)
                )
                """
            ),
            {
                "model_version": cls.MODEL_VERSION,
                "feature_version": cls.FEATURE_VERSION,
                "device": acceleration.preferred_device,
                "training_start": start_date,
                "training_end": end_date,
                "sample_count": len(rows),
                "wape": factory_model["wape"],
                "mae": round(
                    mean(abs(_f(r.get("actual_total_qty")) - factory_model["expected"]) for r in rows),
                    4,
                ),
                "metrics": json.dumps({
                    "confidence": factory_model["confidence"],
                    "band": factory_model["band"],
                    "acceleration": acceleration.to_dict(),
                }),
            },
        )
        if advanced_result is not None and advanced_result.trained:
            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_model_runs (
                        model_version, feature_version, model_family, device,
                        training_start, training_end, sample_count,
                        validation_wape_pct, validation_mae, promoted, metrics_json
                    ) VALUES (
                        :model_version, :feature_version, :model_family, :device,
                        :training_start, :training_end, :sample_count,
                        :wape, :mae, :promoted, CAST(:metrics AS JSONB)
                    )
                    """
                ),
                {
                    "model_version": cls.MODEL_VERSION,
                    "feature_version": "FRCI-GLOBAL-EXEC-1",
                    "model_family": advanced_result.model_family,
                    "device": advanced_result.device,
                    "training_start": start_date,
                    "training_end": end_date,
                    "sample_count": advanced_result.sample_count,
                    "wape": advanced_result.validation_wape_pct,
                    "mae": advanced_result.validation_mae,
                    "promoted": advanced_result.promoted,
                    "metrics": json.dumps({
                        "reason": advanced_result.reason,
                        "model_path": advanced_result.model_path,
                    }),
                },
            )
            training_device = advanced_result.device if advanced_result.promoted else acceleration.preferred_device
        else:
            training_device = acceleration.preferred_device

        cls.refresh_state(session, training_device=training_device)
        return {
            **seeded,
            **bootstrap,
            **rebuild,
            **compat,
            **mold_profiles,
            **memory,
            "fi_capacity_profiles_trained": trained,
            "fi_high_confidence_profiles": high,
            "fi_training_device": training_device,
            "fi_advanced_ml_trained": 1 if advanced_result is not None and advanced_result.trained else 0,
            "fi_advanced_ml_promoted": 1 if advanced_result is not None and advanced_result.promoted else 0,
            "fi_advanced_ml_family": advanced_result.model_family if advanced_result is not None else "ROBUST_ENSEMBLE",
            "fi_advanced_ml_wape_pct": advanced_result.validation_wape_pct if advanced_result is not None else 100.0,
            "fi_advanced_ml_note": advanced_result.reason if advanced_result is not None else locals().get("advanced_error", "Not available"),
        }

    @classmethod
    def rebuild_compatibility(cls, session) -> dict[str, int]:
        rows = cls._safe_rows(
            session,
            """
            SELECT *
            FROM mpps_fi_execution_observations
            ORDER BY production_date
            """,
        )
        relations: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            sap = _code(r.get("sap_code"))
            if not sap:
                continue
            for relation, right in (
                ("SAP_LINE", _norm(r.get("primary_line"))),
                ("SAP_MOLD", _norm(r.get("mold_key"))),
                ("SAP_CASING", _norm(_canonical_casing(r.get("casing_type")))),
            ):
                # "No Casing" is still a valuable technical compatibility fact for
                # future shipment planning, so it is preserved in learned memory.
                if right:
                    relations[(relation, sap, right)].append(r)
            c = _i(r.get("distinct_cavity_count"))
            if c > 0:
                relations[("SAP_CAVITY_COUNT", sap, str(c))].append(r)

        for (relation, left, right), subset in relations.items():
            observed_days = len({r["production_date"] for r in subset})
            totals = [max(0, _i(r.get("actual_total_qty"))) for r in subset]
            avg_actual = mean(totals) if totals else 0.0
            confidence = _clamp(observed_days / 20.0, 0.0, 1.0)
            if observed_days >= 8:
                status = "VERIFIED"
            elif observed_days >= 3:
                status = "LIKELY"
            else:
                status = "LEARNING"
            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_resource_compatibility (
                        relation_type, left_key, right_key, observed_days,
                        total_actual_qty, avg_actual_qty, last_seen_date,
                        confidence_score, status, updated_at
                    ) VALUES (
                        :relation_type, :left_key, :right_key, :observed_days,
                        :total_actual_qty, :avg_actual_qty, :last_seen_date,
                        :confidence_score, :status, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (relation_type, left_key, right_key)
                    DO UPDATE SET
                        observed_days=EXCLUDED.observed_days,
                        total_actual_qty=EXCLUDED.total_actual_qty,
                        avg_actual_qty=EXCLUDED.avg_actual_qty,
                        last_seen_date=EXCLUDED.last_seen_date,
                        confidence_score=EXCLUDED.confidence_score,
                        status=EXCLUDED.status,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {
                    "relation_type": relation,
                    "left_key": left,
                    "right_key": right,
                    "observed_days": observed_days,
                    "total_actual_qty": sum(totals),
                    "avg_actual_qty": avg_actual,
                    "last_seen_date": max(r["production_date"] for r in subset),
                    "confidence_score": confidence,
                    "status": status,
                },
            )
        return {"fi_compatibility_links": len(relations)}

    @classmethod
    def _legacy_technical_capacity(cls, session, sap: str, mold_key: str = "") -> int:
        # Manual capacity is now a labelled fallback only.
        rows = cls._safe_rows(
            session,
            """
            SELECT item_code, available_capacity_per_day
            FROM mpps_capacity_master
            WHERE is_active=TRUE
            """,
        )
        for candidate in (sap, mold_key):
            key = _norm(candidate)
            if not key:
                continue
            for row in rows:
                if _norm(row.get("item_code")) == key:
                    return max(0, _i(row.get("available_capacity_per_day")))
        smds = cls._safe_row(
            session,
            """
            SELECT COALESCE(total_plan,0) AS total_plan
            FROM smds WHERE TRIM(sap_code)=:sap
            """,
            {"sap": sap},
        )
        return max(0, _i(smds.get("total_plan")))

    @classmethod
    def _resource_availability(
        cls,
        session,
        *,
        sap: str,
        mold_key: str,
        casing_type: str,
        line_name: str = "",
    ) -> dict[str, Any]:
        mold_available: int | None = None
        if mold_key:
            row = cls._safe_row(
                session,
                """
                SELECT GREATEST(
                    COALESCE(mold_count,0)
                    - COALESCE(production_mold_count,0)
                    - COALESCE(breakdown_mold_count,0)
                    - COALESCE(planning_reserved_mold_count,0),
                    0
                ) AS available
                FROM mold_master
                WHERE LOWER(TRIM(mold_key_code))=LOWER(TRIM(:key))
                LIMIT 1
                """,
                {"key": mold_key},
            )
            if row:
                mold_available = max(0, _i(row.get("available")))

        casing_available: int | None = None
        casing_norm = _norm(casing_type)
        if casing_norm and casing_norm not in {"NO CASING", "-", "NONE", "N/A"}:
            row = cls._safe_row(
                session,
                """
                SELECT COUNT(*) FILTER (
                    WHERE LOWER(COALESCE(condition_status,'active')) NOT IN ('breakdown','retired','inactive')
                      AND LOWER(COALESCE(stock_status,'free')) = 'free'
                ) AS available
                FROM casing_units
                WHERE LOWER(TRIM(casing_type))=LOWER(TRIM(:type))
                """,
                {"type": casing_type},
            )
            if row:
                casing_available = max(0, _i(row.get("available")))
            else:
                master = cls._safe_row(
                    session,
                    """
                    SELECT GREATEST(
                        GREATEST(COALESCE(total_casing_count,0), COALESCE(casing_count,0), COALESCE(available_casing_count,0))
                        - COALESCE(production_casing_count,0)
                        - COALESCE(breakdown_casing_count,0)
                        - COALESCE(planning_reserved_casing_count,0),
                        0
                    ) AS available
                    FROM casing_master
                    WHERE LOWER(TRIM(casing_type))=LOWER(TRIM(:type))
                    LIMIT 1
                    """,
                    {"type": casing_type},
                )
                if master:
                    casing_available = max(0, _i(master.get("available")))

        cavity_rows = cls._safe_rows(
            session,
            """
            SELECT c.cavity_code, c.status, c.line_name
            FROM production_line_cavities c
            JOIN production_lines l ON LOWER(TRIM(l.line_name))=LOWER(TRIM(c.line_name))
            WHERE LOWER(COALESCE(c.status,'active')) NOT IN ('breakdown','retired','inactive')
              AND LOWER(COALESCE(l.status,'active')) NOT IN ('retired','inactive')
            """,
        )
        if line_name:
            cavity_rows = [r for r in cavity_rows if _norm(r.get("line_name")) == _norm(line_name)]
        cavity_available = len(cavity_rows)

        return {
            "mold_available": mold_available,
            "casing_available": casing_available,
            "cavity_available": cavity_available,
        }

    @classmethod
    def resolve_capacity(
        cls,
        session,
        sap_code: str,
        *,
        on_date: date | None = None,
        line_name: str = "",
        requested_cavities: int | None = None,
        ensure_schema: bool = True,
    ) -> CapacityResolution:
        if ensure_schema:
            cls.ensure_schema(session)
        sap = _code(sap_code)
        smds = cls._safe_row(
            session,
            """
            SELECT COALESCE(key_code,'') AS mold_key,
                   COALESCE(casing_type,'') AS casing_type,
                   COALESCE(total_plan,0) AS total_plan
            FROM smds WHERE TRIM(sap_code)=:sap
            """,
            {"sap": sap},
        )
        mold_key = _text(smds.get("mold_key"))
        casing_type = _canonical_casing(smds.get("casing_type"))

        candidates = [("SAP", sap)]
        if mold_key:
            candidates.append(("MOLD", _norm(mold_key)))
        if line_name:
            candidates.append(("LINE", _norm(line_name)))
        candidates.append(("FACTORY", "FACTORY"))

        profile = {}
        used_level = ""
        for level, key in candidates:
            row = cls._safe_row(
                session,
                "SELECT * FROM mpps_fi_capacity_profiles WHERE profile_key=:key",
                {"key": f"{level}|{key}"},
            )
            if row and _f(row.get("expected_capacity_qty")) > 0:
                # Prefer entity-level learned evidence. Sparse SAP profiles remain
                # valid but are clearly labelled by confidence.
                profile = row
                used_level = level
                break

        technical = cls._legacy_technical_capacity(session, sap, mold_key)
        if profile:
            safe = max(0, _i(profile.get("safe_capacity_qty")))
            expected = max(safe, _i(profile.get("expected_capacity_qty")))
            stretch = max(expected, _i(profile.get("stretch_capacity_qty")))
            confidence = _clamp(_f(profile.get("confidence_score")), 0.0, 1.0)
            band = str(profile.get("confidence_band") or "LEARNING")
            stable_cavities = max(0, _i(profile.get("stable_cavity_count")))
            observed_max = max(stable_cavities, _i(profile.get("observed_max_cavity_count")))
            sample_days = max(0, _i(profile.get("sample_days")))
            source = f"LEARNED_{used_level}"
            model_key = str(profile.get("profile_key") or "")
        elif technical > 0:
            safe = max(1, int(round(technical * 0.85)))
            expected = technical
            stretch = technical
            confidence = 0.30
            band = "TECHNICAL BASELINE"
            stable_cavities = 0
            observed_max = 0
            sample_days = 0
            source = "LEGACY_TECHNICAL"
            model_key = ""
        else:
            safe = expected = stretch = 0
            confidence = 0.0
            band = "COLD START"
            stable_cavities = observed_max = 0
            sample_days = 0
            source = "NO_EVIDENCE"
            model_key = ""

        # If a nonlinear challenger has earned promotion on future-period
        # validation, use it as a correction layer over the robust SAP/resource
        # envelope. The robust safe value remains the conservative floor/guardrail.
        if expected > 0 and profile:
            try:
                from app.services.advanced_capacity_ml import AdvancedCapacityML
                advanced = AdvancedCapacityML().predict({
                    "production_date": on_date or date.today(),
                    "sap_code": sap,
                    "planned_total_qty": expected,
                    "planned_day_qty": int(round(expected * _f(profile.get("day_share"), 0.5))),
                    "distinct_cavity_count": requested_cavities or stable_cavities or 1,
                    "allocation_slot_count": max(
                        1,
                        _i(profile.get("typical_allocation_slots"))
                        or requested_cavities
                        or stable_cavities
                        or 1,
                    ),
                    "distinct_line_count": 1 if line_name else max(1, _i(profile.get("distinct_line_count"), 1)),
                    "primary_line": line_name,
                    "mold_key": mold_key,
                    "casing_type": casing_type,
                })
            except Exception:
                advanced = {}
            advanced_expected = max(0, _i(advanced.get("expected_actual_qty")))
            if advanced_expected > 0:
                robust_expected = expected
                # The challenger corrects the point estimate, but safe capacity is
                # never increased aggressively by a black-box model.
                expected = max(1, int(round(0.65 * advanced_expected + 0.35 * robust_expected)))
                safe = min(expected, max(1, int(round(0.90 * advanced_expected))), safe if safe > 0 else expected)
                stretch = max(expected, stretch, advanced_expected)
                source = f"{advanced.get('model_family','ADVANCED_ML')}+{source}"
                confidence = max(confidence, _clamp(1.0 - _f(advanced.get("validation_wape_pct"), 100.0) / 100.0, 0.0, 0.95))

        resources = cls._resource_availability(
            session,
            sap=sap,
            mold_key=mold_key,
            casing_type=casing_type,
            line_name=line_name,
        )
        available = safe
        reasons: list[str] = []
        target_cavities = (
            max(1, int(requested_cavities))
            if requested_cavities
            else max(1, stable_cavities or 1)
        )

        mold_avail = resources.get("mold_available")
        if mold_avail is not None:
            if mold_avail <= 0:
                available = 0
                reasons.append("No usable mold is currently available.")
            elif target_cavities > 1 and mold_avail < target_cavities:
                available = min(available, int(round(safe * mold_avail / target_cavities)))
                reasons.append(f"Mold availability limits normal setup to {mold_avail}/{target_cavities}.")

        casing_avail = resources.get("casing_available")
        casing_norm = _norm(casing_type)
        if casing_norm and casing_norm not in {"NO CASING", "-", "NONE", "N/A"}:
            if casing_avail is not None and casing_avail <= 0:
                available = 0
                reasons.append(f"Shared casing {casing_type} has no free unit.")
            elif casing_avail is not None and target_cavities > 1 and casing_avail < target_cavities:
                available = min(available, int(round(safe * casing_avail / target_cavities)))
                reasons.append(f"Casing {casing_type} limits concurrent production to {casing_avail}.")

        cavity_avail = max(0, _i(resources.get("cavity_available")))
        if cavity_avail <= 0:
            available = 0
            reasons.append("No active cavity/press position is available for the selected scope.")
        elif target_cavities > 1 and cavity_avail < target_cavities:
            available = min(available, int(round(safe * cavity_avail / target_cavities)))
            reasons.append(f"Available cavity positions limit the normal {target_cavities}-cavity setup.")

        return CapacityResolution(
            sap_code=sap,
            safe_capacity=safe,
            expected_capacity=expected,
            stretch_capacity=stretch,
            available_capacity=max(0, available),
            source=source,
            confidence_score=confidence,
            confidence_band=band,
            stable_cavity_count=stable_cavities,
            observed_max_cavity_count=observed_max,
            sample_days=sample_days,
            mold_key=mold_key,
            casing_type=casing_type,
            technical_capacity=technical,
            constraint_reason=" ".join(reasons) if reasons else "No active physical constraint reduced the learned safe capacity.",
            model_key=model_key,
        )

    @classmethod
    def casing_pressure(cls, session) -> list[dict[str, Any]]:
        """Show shared-casing pressure from current SAP demand."""
        rows = cls._safe_rows(
            session,
            """
            WITH demand AS (
                SELECT i.sap_code,
                       SUM(GREATEST(COALESCE(i.quantity,0)-COALESCE(i.stock_allocated_qty,0)-COALESCE(i.completed_qty,0),0)) AS gap
                FROM mpps_shipment_items i
                JOIN mpps_shipments s ON s.id=i.shipment_id
                WHERE UPPER(COALESCE(s.status,'')) NOT IN ('DISPATCHED','CANCELLED','ARCHIVED','COMPLETED','SHIPPED','CLOSED')
                GROUP BY i.sap_code
            )
            SELECT CASE
                       WHEN UPPER(TRIM(COALESCE(s.casing_type,''))) IN ('','-','--','NO CASING','NO-CASING','NONE','N/A','NA','NOT REQUIRED')
                       THEN 'No Casing'
                       ELSE TRIM(s.casing_type)
                   END AS casing_type,
                   COUNT(*) FILTER (WHERE d.gap > 0) AS sap_count,
                   COALESCE(SUM(d.gap),0) AS production_gap
            FROM demand d
            JOIN smds s ON TRIM(s.sap_code)=TRIM(d.sap_code)
            GROUP BY CASE
                       WHEN UPPER(TRIM(COALESCE(s.casing_type,''))) IN ('','-','--','NO CASING','NO-CASING','NONE','N/A','NA','NOT REQUIRED')
                       THEN 'No Casing'
                       ELSE TRIM(s.casing_type)
                   END
            ORDER BY production_gap DESC
            """,
        )
        for row in rows:
            casing = _canonical_casing(row.get("casing_type"))
            if casing == "No Casing":
                row["available_units"] = None
                row["pressure_ratio"] = 0.0
                continue
            master = cls._resource_availability(
                session, sap="", mold_key="", casing_type=casing
            )
            available = master.get("casing_available")
            row["available_units"] = available
            row["pressure_ratio"] = round(_f(row.get("production_gap")) / max(1, _i(available)), 2) if available is not None else None
        return rows

    @classmethod
    def refresh_state(cls, session, *, training_device: str | None = None) -> dict[str, Any]:
        cls.ensure_schema(session)
        counts = cls._safe_row(
            session,
            """
            SELECT
                (SELECT MAX(plan_date) FROM mpps_fi_daily_sap_resource_plan) AS latest_plan_date,
                (SELECT COUNT(*) FROM mpps_fi_plan_allocations) AS allocations,
                (SELECT COUNT(*) FROM mpps_fi_execution_observations) AS executions,
                (SELECT COUNT(*) FROM mpps_fi_capacity_profiles) AS profiles,
                (SELECT COUNT(*) FROM mpps_fi_capacity_profiles WHERE confidence_band='HIGH') AS high_profiles
            """,
        )
        session.execute(
            text(
                """
                UPDATE mpps_fi_state
                SET model_version=:model_version,
                    latest_plan_date=:latest_plan_date,
                    resource_observations=:allocations,
                    execution_observations=:executions,
                    capacity_profiles=:profiles,
                    high_confidence_profiles=:high_profiles,
                    last_training_device=COALESCE(:training_device,last_training_device),
                    last_training_at=CASE WHEN :training_device IS NULL THEN last_training_at ELSE CURRENT_TIMESTAMP END,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=1
                """
            ),
            {
                "model_version": cls.MODEL_VERSION,
                "latest_plan_date": counts.get("latest_plan_date"),
                "allocations": _i(counts.get("allocations")),
                "executions": _i(counts.get("executions")),
                "profiles": _i(counts.get("profiles")),
                "high_profiles": _i(counts.get("high_profiles")),
                "training_device": training_device,
            },
        )
        return {
            "latest_plan_date": counts.get("latest_plan_date"),
            "resource_observations": _i(counts.get("allocations")),
            "execution_observations": _i(counts.get("executions")),
            "capacity_profiles": _i(counts.get("profiles")),
            "high_confidence_profiles": _i(counts.get("high_profiles")),
        }

    @staticmethod
    def _progress(
        callback: Callable[[int, str, str], None] | None,
        percent: int,
        stage: str,
        detail: str = "",
    ) -> None:
        if callback is None:
            return
        try:
            callback(max(0, min(100, int(percent))), stage, detail)
        except Exception:
            # UI progress reporting must never break factory data loading.
            pass

    @classmethod
    def rebuild_resource_memory(cls, session) -> dict[str, int]:
        """Build unique SQL memory for line/cavity/mold-to-SAP relationships.

        Daily evidence stays in mpps_fi_plan_allocations. This table stores one
        canonical relationship row and updates its evidence counters instead of
        inserting duplicates every day.
        """
        cls.ensure_schema(session)
        rows = cls._safe_rows(
            session,
            """
            SELECT plan_date, shift_name, line_name, cavity_code, mold_code, casing_type,
                   sap_code, planned_qty
            FROM mpps_fi_plan_allocations
            WHERE shift_name IN ('DAY','NIGHT') AND planned_qty > 0
            ORDER BY plan_date, id
            """,
        )
        actual_rows = cls._safe_rows(
            session,
            """
            SELECT production_date, sap_code, total_actual_qty
            FROM mpps_actual_production
            """,
        )
        actual = {
            (r.get("production_date"), _code(r.get("sap_code"))): _i(r.get("total_actual_qty"))
            for r in actual_rows
        }
        rel: dict[tuple[str, str, str], dict[str, Any]] = {}
        for r in rows:
            sap = _code(r.get("sap_code"))
            d = r.get("plan_date")
            line = _text(r.get("line_name"))
            cavity = _text(r.get("cavity_code"))
            mold = _text(r.get("mold_code"))
            casing = _canonical_casing(r.get("casing_type"))
            candidates = []
            if line:
                candidates.append(("LINE_SAP", _norm(line), sap))
            if cavity:
                candidates.append(("CAVITY_SAP", f"{_norm(line)}|{_norm(cavity)}", sap))
            if mold:
                candidates.append(("MOLD_SAP", _norm(mold), sap))
            if casing:
                casing_key = _norm(casing)
                candidates.append(("CASING_SAP", casing_key, sap))
                if mold:
                    candidates.append(("CASING_MOLD", casing_key, _norm(mold)))
                if line:
                    candidates.append(("CASING_LINE", casing_key, _norm(line)))
                if cavity:
                    candidates.append(("CASING_CAVITY", casing_key, f"{_norm(line)}|{_norm(cavity)}"))
            if mold and line:
                candidates.append(("MOLD_LINE", _norm(mold), _norm(line)))
            if mold and cavity:
                candidates.append(("MOLD_CAVITY", _norm(mold), f"{_norm(line)}|{_norm(cavity)}"))
            for relation, left, right in candidates:
                if not left or not right:
                    continue
                bucket = rel.setdefault(
                    (relation, left, right),
                    {"dates": set(), "events": 0, "actual": []},
                )
                bucket["dates"].add(d)
                bucket["events"] += 1
                a = actual.get((d, sap))
                if a is not None:
                    bucket["actual"].append(a)

        for (relation, left, right), bucket in rel.items():
            dates = sorted(d for d in bucket["dates"] if d is not None)
            observed_days = len(dates)
            values = bucket["actual"]
            confidence = _clamp(observed_days / 20.0, 0.0, 1.0)
            status = "VERIFIED" if observed_days >= 8 else ("LIKELY" if observed_days >= 3 else "LEARNING")
            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_resource_compatibility(
                        relation_type,left_key,right_key,observed_days,total_actual_qty,
                        avg_actual_qty,first_seen_date,last_seen_date,evidence_count,
                        confidence_score,status,updated_at
                    ) VALUES(
                        :relation,:left_key,:right_key,:observed_days,:total_actual,
                        :avg_actual,:first_seen,:last_seen,:evidence_count,
                        :confidence,:status,CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(relation_type,left_key,right_key) DO UPDATE SET
                        observed_days=EXCLUDED.observed_days,
                        total_actual_qty=EXCLUDED.total_actual_qty,
                        avg_actual_qty=EXCLUDED.avg_actual_qty,
                        first_seen_date=COALESCE(mpps_fi_resource_compatibility.first_seen_date, EXCLUDED.first_seen_date),
                        last_seen_date=EXCLUDED.last_seen_date,
                        evidence_count=EXCLUDED.evidence_count,
                        confidence_score=EXCLUDED.confidence_score,
                        status=EXCLUDED.status,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {
                    "relation": relation,
                    "left_key": left,
                    "right_key": right,
                    "observed_days": observed_days,
                    "total_actual": sum(values),
                    "avg_actual": mean(values) if values else 0.0,
                    "first_seen": dates[0] if dates else None,
                    "last_seen": dates[-1] if dates else None,
                    "evidence_count": int(bucket["events"]),
                    "confidence": confidence,
                    "status": status,
                },
            )
        return {"fi_resource_memory_links": len(rel)}

    @classmethod
    def rebuild_mold_profiles(cls, session) -> dict[str, int]:
        """Learn BAND mold-code max use, average use and normal production.

        Max Mold = maximum distinct OVEN/cavity positions used by that mold in
        one DAY or NIGHT shift. Average Use excludes shifts where the mold was not
        used. Normal Production Average uses verified shift actuals and allocates
        SAP actual proportionally when a SAP is split across more than one mold.
        """
        cls.ensure_schema(session)
        usage = cls._safe_rows(
            session,
            """
            SELECT import_run_id, plan_date, shift_name, mold_code,
                   distinct_cavity_count, planned_qty, sap_codes_json
            FROM mpps_fi_mold_shift_usage
            WHERE shift_name IN ('DAY','NIGHT') AND TRIM(mold_code) <> ''
            ORDER BY plan_date, shift_name, mold_code
            """,
        )
        allocations = cls._safe_rows(
            session,
            """
            SELECT plan_date, shift_name, mold_code, sap_code, SUM(planned_qty) AS planned_qty
            FROM mpps_fi_plan_allocations
            WHERE shift_name IN ('DAY','NIGHT') AND planned_qty > 0 AND TRIM(mold_code) <> ''
            GROUP BY plan_date, shift_name, mold_code, sap_code
            """,
        )
        actual_rows = cls._safe_rows(
            session,
            """
            SELECT a.production_date, a.sap_code, a.day_actual_qty, a.night_actual_qty
            FROM mpps_actual_production a
            JOIN mpps_actual_production_dates d
              ON d.production_date=a.production_date
             AND d.source_import_run_id=a.source_import_run_id
            WHERE d.is_complete=TRUE
            """,
        )
        actual_shift: dict[tuple[Any, str, str], int] = {}
        for r in actual_rows:
            d = r.get("production_date")
            sap = _code(r.get("sap_code"))
            actual_shift[(d, "DAY", sap)] = max(0, _i(r.get("day_actual_qty")))
            actual_shift[(d, "NIGHT", sap)] = max(0, _i(r.get("night_actual_qty")))

        planned_by_sap_shift: dict[tuple[Any, str, str], float] = defaultdict(float)
        planned_by_mold_sap_shift: dict[tuple[Any, str, str, str], float] = defaultdict(float)
        related: dict[str, set[str]] = defaultdict(set)
        for r in allocations:
            d = r.get("plan_date")
            shift = _norm(r.get("shift_name"))
            mold = _text(r.get("mold_code"))
            sap = _code(r.get("sap_code"))
            qty = max(0.0, _f(r.get("planned_qty")))
            if not mold or not sap or qty <= 0:
                continue
            planned_by_sap_shift[(d, shift, sap)] += qty
            planned_by_mold_sap_shift[(d, shift, mold, sap)] += qty
            related[mold].add(sap)

        allocated_actual: dict[tuple[Any, str, str], float] = defaultdict(float)
        for (d, shift, mold, sap), qty in planned_by_mold_sap_shift.items():
            total = planned_by_sap_shift.get((d, shift, sap), 0.0)
            actual = actual_shift.get((d, shift, sap))
            if total > 0 and actual is not None:
                allocated_actual[(d, shift, mold)] += actual * (qty / total)

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in usage:
            mold = _text(r.get("mold_code"))
            if mold:
                grouped[mold].append(r)
                raw_saps = r.get("sap_codes_json") or []
                if isinstance(raw_saps, str):
                    try:
                        raw_saps = json.loads(raw_saps)
                    except Exception:
                        raw_saps = []
                for sap in raw_saps if isinstance(raw_saps, list) else []:
                    if _code(sap):
                        related[mold].add(_code(sap))

        # Include BAND master identities that have not yet been scheduled.
        registry = cls._safe_rows(
            session,
            """
            SELECT canonical_name, lifecycle_status, last_seen_date, metadata_json
            FROM mpps_fi_resource_registry
            WHERE resource_type='MOLD'
            """,
        )
        band_codes: set[str] = set(grouped)
        registry_status: dict[str, str] = {}
        registry_last: dict[str, Any] = {}
        for r in registry:
            meta = r.get("metadata_json") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if str((meta or {}).get("authority") or "").upper() != "BAND_MATERIAL_DESCRIPTION":
                continue
            code = _text(r.get("canonical_name"))
            if code:
                band_codes.add(code)
                registry_status[code] = str(r.get("lifecycle_status") or "LEARNING")
                registry_last[code] = r.get("last_seen_date")

        for mold in sorted(band_codes):
            subset = grouped.get(mold, [])
            counts = [max(0, _i(r.get("distinct_cavity_count"))) for r in subset if _i(r.get("distinct_cavity_count")) > 0]
            actual_samples: list[float] = []
            for r in subset:
                key = (r.get("plan_date"), _norm(r.get("shift_name")), mold)
                if key in allocated_actual:
                    actual_samples.append(float(allocated_actual[key]))
            last_seen = max((r.get("plan_date") for r in subset if r.get("plan_date") is not None), default=registry_last.get(mold))
            status = registry_status.get(mold) or ("ACTIVE" if subset else "LEARNING")
            session.execute(
                text(
                    """
                    INSERT INTO mpps_fi_mold_profiles(
                        mold_code,max_mold,average_use,normal_production_average,
                        active_shift_count,actual_shift_samples,related_saps_json,
                        status,last_seen_date,updated_at
                    ) VALUES(
                        :mold_code,:max_mold,:average_use,:normal_avg,
                        :active_shifts,:actual_samples,CAST(:saps AS JSONB),
                        :status,:last_seen,CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(mold_code) DO UPDATE SET
                        max_mold=EXCLUDED.max_mold,
                        average_use=EXCLUDED.average_use,
                        normal_production_average=EXCLUDED.normal_production_average,
                        active_shift_count=EXCLUDED.active_shift_count,
                        actual_shift_samples=EXCLUDED.actual_shift_samples,
                        related_saps_json=EXCLUDED.related_saps_json,
                        status=EXCLUDED.status,
                        last_seen_date=EXCLUDED.last_seen_date,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {
                    "mold_code": mold,
                    "max_mold": max(counts) if counts else 0,
                    "average_use": mean(counts) if counts else 0.0,
                    "normal_avg": mean(actual_samples) if actual_samples else 0.0,
                    "active_shifts": len(counts),
                    "actual_samples": len(actual_samples),
                    "saps": json.dumps(sorted(related.get(mold, set()))),
                    "status": status,
                    "last_seen": last_seen,
                },
            )
        return {"fi_mold_profiles": len(band_codes)}

    @classmethod
    def _latest_live_context(cls, session) -> dict[str, Any]:
        row = cls._safe_row(
            session,
            """
            SELECT r.id AS import_run_id, r.plan_date, r.workbook_name
            FROM excel_import_runs r
            WHERE r.status IN ('COMMITTED','COMMITTED WITH WARNINGS')
              AND r.rollback_at IS NULL AND r.plan_date IS NOT NULL
            ORDER BY r.plan_date DESC, r.id DESC
            LIMIT 1
            """,
        )
        if row:
            return row
        row = cls._safe_row(
            session,
            """
            SELECT import_run_id, MIN(plan_date) AS plan_date, MAX(source_workbook) AS workbook_name
            FROM mpps_fi_plan_allocations
            WHERE import_run_id=(SELECT MAX(import_run_id) FROM mpps_fi_plan_allocations)
            GROUP BY import_run_id
            """,
        )
        return row

    @classmethod
    def header_snapshot(cls, session) -> dict[str, Any]:
        cls.ensure_schema(session)
        ctx = cls._latest_live_context(session)
        state = cls._safe_row(session, "SELECT * FROM mpps_fi_state WHERE id=1")
        return {
            "latest_plan_date": ctx.get("plan_date") or state.get("latest_plan_date"),
            "import_run_id": ctx.get("import_run_id"),
            "workbook_name": ctx.get("workbook_name") or "",
        }

    @staticmethod
    def _resource_meta(row: dict[str, Any]) -> dict[str, Any]:
        meta = row.get("metadata_json") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return meta if isinstance(meta, dict) else {}

    @classmethod
    def production_lines_snapshot(cls, session) -> dict[str, Any]:
        """Compact operator view of physical line/cavity condition.

        Active Cavities is deliberately a *technical working-condition* count, not
        a current-plan allocation count.  OVEN/ML lifecycle remains available for
        the line Status and More Details views.
        """
        cls.ensure_schema(session)
        ctx = cls._latest_live_context(session)

        line_rows = cls._safe_rows(
            session,
            "SELECT line_name, COALESCE(status,'Active') AS status FROM production_lines ORDER BY line_name",
        )
        cavity_rows = cls._safe_rows(
            session,
            """
            SELECT line_name, cavity_code, cavity_no, COALESCE(status,'Active') AS status
            FROM production_line_cavities
            ORDER BY line_name, cavity_no
            """,
        )
        registry = cls._safe_rows(
            session,
            "SELECT resource_type, resource_key, canonical_name, parent_key, lifecycle_status, metadata_json FROM mpps_fi_resource_registry WHERE resource_type IN ('LINE','CAVITY')",
        )

        lifecycle_by_line: dict[str, str] = {}
        cavity_registry: dict[tuple[str, str], dict[str, Any]] = {}
        for r in registry:
            if r.get("resource_type") == "LINE":
                name = _text(r.get("canonical_name") or r.get("resource_key"))
                if name:
                    lifecycle_by_line[_norm(name)] = _norm(r.get("lifecycle_status")) or "LEARNING"
            elif r.get("resource_type") == "CAVITY":
                meta = cls._resource_meta(r)
                line = _text(r.get("parent_key") or meta.get("line_name"))
                cavity = _text(r.get("canonical_name") or r.get("resource_key"))
                if line and cavity:
                    cavity_registry[(_norm(line), _norm(cavity))] = r

        lines: dict[str, dict[str, Any]] = {}
        for r in line_rows:
            name = _text(r.get("line_name"))
            if name:
                lines[_norm(name)] = {"line": name, "technical_status": _norm(r.get("status")) or "ACTIVE"}
        for key, lifecycle in lifecycle_by_line.items():
            if key not in lines:
                reg = next((r for r in registry if r.get("resource_type") == "LINE" and _norm(r.get("canonical_name") or r.get("resource_key")) == key), None)
                name = _text((reg or {}).get("canonical_name") or (reg or {}).get("resource_key"))
                if name:
                    lines[key] = {"line": name, "technical_status": "ACTIVE"}

        counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "active": 0, "breakdown": 0})
        seen_cavities: set[tuple[str, str]] = set()
        for r in cavity_rows:
            line = _text(r.get("line_name"))
            cavity = _text(r.get("cavity_code")) or f"CAVITY-{_i(r.get('cavity_no'))}"
            if not line or not cavity:
                continue
            pair = (_norm(line), _norm(cavity))
            if pair in seen_cavities:
                continue
            seen_cavities.add(pair)
            if pair[0] not in lines:
                lines[pair[0]] = {"line": line, "technical_status": "ACTIVE"}
            status = _norm(r.get("status")) or "ACTIVE"
            counts[pair[0]]["total"] += 1
            if status == "ACTIVE":
                counts[pair[0]]["active"] += 1
            elif status == "BREAKDOWN":
                counts[pair[0]]["breakdown"] += 1

        # Fallback for older DBs where technical projection has not yet run.
        if not cavity_rows:
            for (line_key, cavity_key), r in cavity_registry.items():
                pair = (line_key, cavity_key)
                if pair in seen_cavities:
                    continue
                seen_cavities.add(pair)
                meta = cls._resource_meta(r)
                status = _norm(meta.get("technical_status")) or "ACTIVE"
                counts[line_key]["total"] += 1
                if status == "ACTIVE":
                    counts[line_key]["active"] += 1
                elif status == "BREAKDOWN":
                    counts[line_key]["breakdown"] += 1

        out: list[dict[str, Any]] = []
        for key, base in sorted(lines.items(), key=lambda kv: kv[1]["line"].upper()):
            c = counts.get(key, {"total": 0, "active": 0, "breakdown": 0})
            lifecycle = lifecycle_by_line.get(key, "")
            technical = base.get("technical_status") or "ACTIVE"
            if lifecycle in {"RETIRED", "RETIREMENT CANDIDATE", "DORMANT", "REVIEW"}:
                status = lifecycle
            elif technical in {"RETIRED", "INACTIVE"}:
                status = "RETIRED" if technical == "RETIRED" else "DORMANT"
            elif c["total"] > 0 and c["breakdown"] >= c["total"]:
                status = "NEED ATTENTION"
            elif c["breakdown"] > 0:
                status = "PARTIAL"
            else:
                status = "ACTIVE"
            out.append({
                "line": base["line"],
                "total_cavities": int(c["total"]),
                "active_cavities": int(c["active"]),
                "breakdown_cavities": int(c["breakdown"]),
                "status": status,
            })
        return {"latest_plan_date": ctx.get("plan_date"), "rows": out}

    @classmethod
    def cavities_snapshot(cls, session) -> dict[str, Any]:
        """Return one canonical row per physical cavity/oven position."""
        cls.ensure_schema(session)
        ctx = cls._latest_live_context(session)
        technical = cls._safe_rows(
            session,
            """
            SELECT line_name, cavity_code, cavity_no, COALESCE(status,'Active') AS status
            FROM production_line_cavities
            ORDER BY line_name, cavity_no
            """,
        )
        registry = cls._safe_rows(
            session,
            "SELECT * FROM mpps_fi_resource_registry WHERE resource_type='CAVITY'",
        )
        registry_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
        for r in registry:
            meta = cls._resource_meta(r)
            line = _text(r.get("parent_key") or meta.get("line_name"))
            cavity = _text(r.get("canonical_name") or r.get("resource_key"))
            if line and cavity:
                key = (_norm(line), _norm(cavity))
                old = registry_by_pair.get(key)
                if old is None or _norm(r.get("lifecycle_status")) == "ACTIVE":
                    registry_by_pair[key] = r

        canonical: dict[tuple[str, str], dict[str, Any]] = {}
        for r in technical:
            line = _text(r.get("line_name"))
            cavity = _text(r.get("cavity_code")) or f"CAVITY-{_i(r.get('cavity_no'))}"
            if not line or not cavity:
                continue
            key = (_norm(line), _norm(cavity))
            tech_status = _norm(r.get("status")) or "ACTIVE"
            learned = registry_by_pair.get(key, {})
            lifecycle = _norm(learned.get("lifecycle_status"))
            if tech_status == "BREAKDOWN":
                status = "BREAKDOWN"
            elif tech_status in {"RETIRED", "INACTIVE"}:
                status = "RETIRED" if tech_status == "RETIRED" else "DORMANT"
            elif lifecycle in {"RETIRED", "RETIREMENT CANDIDATE", "DORMANT", "REVIEW"}:
                status = lifecycle
            else:
                status = "ACTIVE"
            canonical[key] = {"line": line, "cavity": cavity, "status": status}

        # Fallback for learned cavities not projected into the technical register yet.
        for key, r in registry_by_pair.items():
            if key in canonical:
                continue
            meta = cls._resource_meta(r)
            line = _text(r.get("parent_key") or meta.get("line_name"))
            cavity = _text(r.get("canonical_name") or r.get("resource_key"))
            tech_status = _norm(meta.get("technical_status"))
            lifecycle = _norm(r.get("lifecycle_status")) or "LEARNING"
            if tech_status == "BREAKDOWN":
                status = "BREAKDOWN"
            elif lifecycle in {"RETIRED", "RETIREMENT CANDIDATE", "DORMANT", "REVIEW"}:
                status = lifecycle
            else:
                status = "ACTIVE" if lifecycle == "ACTIVE" else lifecycle
            canonical[key] = {"line": line or "UNMAPPED", "cavity": cavity, "status": status}

        rows = sorted(canonical.values(), key=lambda r: (str(r["line"]).upper(), str(r["cavity"]).upper()))
        return {
            "latest_plan_date": ctx.get("plan_date"),
            "rows": rows,
            "lines": sorted({r["line"] for r in rows if r.get("line") and r.get("line") != "UNMAPPED"}),
        }

    @classmethod
    def molds_snapshot(cls, session) -> dict[str, Any]:
        cls.ensure_schema(session)
        rows = cls._safe_rows(
            session,
            """
            SELECT mold_code,max_mold,average_use,normal_production_average,
                   active_shift_count,actual_shift_samples,related_saps_json,status,last_seen_date
            FROM mpps_fi_mold_profiles
            ORDER BY mold_code
            """,
        )
        result=[]
        for r in rows:
            saps=r.get("related_saps_json") or []
            if isinstance(saps,str):
                try: saps=json.loads(saps)
                except Exception: saps=[]
            result.append({
                **r,
                "related_saps": saps if isinstance(saps,list) else [],
                "related_saps_display": ", ".join((saps if isinstance(saps,list) else [])[:4]) + (" ..." if isinstance(saps,list) and len(saps)>4 else ""),
            })
        return {"rows": result, "count": len(result), "latest_plan_date": cls._latest_live_context(session).get("plan_date")}

    @classmethod
    def casings_snapshot(cls, session) -> dict[str, Any]:
        """Canonical casing register with filters backed by learned relationships."""
        cls.ensure_schema(session)
        registry = cls._safe_rows(
            session,
            "SELECT * FROM mpps_fi_resource_registry WHERE resource_type='CASING' ORDER BY canonical_name",
        )
        allocations = cls._safe_rows(
            session,
            """
            SELECT casing_type, sap_code, item_description, mold_code, line_name, cavity_code
            FROM mpps_fi_plan_allocations
            WHERE shift_name IN ('DAY','NIGHT') AND planned_qty > 0
            """,
        )
        smds_rows = cls._safe_rows(
            session,
            """
            SELECT TRIM(sap_code) AS sap_code, COALESCE(material_description,'') AS material_description,
                   COALESCE(key_code,'') AS key_code, COALESCE(casing_type,'') AS casing_type
            FROM smds WHERE TRIM(COALESCE(sap_code,'')) <> ''
            """,
        )

        groups: dict[str, dict[str, Any]] = {}
        status_rank = {"REVIEW": 6, "ACTIVE": 5, "LEARNING": 4, "DORMANT": 3, "RETIREMENT CANDIDATE": 2, "RETIRED": 1}

        def ensure(name: str, status: str = "LEARNING") -> dict[str, Any] | None:
            canonical = _canonical_casing(name)
            if not canonical:
                return None
            key = _norm(canonical)
            rec = groups.setdefault(key, {
                "casing": canonical, "status": status or "LEARNING", "related_saps": set(),
                "related_molds": set(), "descriptions": set(), "lines": set(), "cavities": set(),
            })
            if canonical == "No Casing":
                rec["casing"] = "No Casing"
                rec["status"] = "ACTIVE"
            elif status_rank.get(_norm(status), 0) > status_rank.get(_norm(rec.get("status")), 0):
                rec["status"] = _norm(status) or "LEARNING"
            return rec

        for r in registry:
            rec = ensure(_text(r.get("canonical_name") or r.get("resource_key")), str(r.get("lifecycle_status") or "LEARNING"))
            if rec is None:
                continue
            meta = cls._resource_meta(r)
            sap_example = _code(meta.get("sap_example"))
            if sap_example:
                rec["related_saps"].add(sap_example)

        for r in allocations:
            rec = ensure(_text(r.get("casing_type")), "LEARNING")
            if rec is None:
                continue
            sap = _code(r.get("sap_code"))
            if sap:
                rec["related_saps"].add(sap)
            if _text(r.get("mold_code")):
                rec["related_molds"].add(_text(r.get("mold_code")))
            if _text(r.get("item_description")):
                rec["descriptions"].add(_text(r.get("item_description")))
            if _text(r.get("line_name")):
                rec["lines"].add(_text(r.get("line_name")))
            if _text(r.get("cavity_code")):
                rec["cavities"].add(_text(r.get("cavity_code")))

        # SMDS is a technical mapping source and is useful even before a casing has
        # accumulated many historical OVEN observations.
        for r in smds_rows:
            rec = ensure(_text(r.get("casing_type")), "LEARNING")
            if rec is None:
                continue
            sap = _code(r.get("sap_code"))
            if sap:
                rec["related_saps"].add(sap)
            if _text(r.get("material_description")):
                rec["descriptions"].add(_text(r.get("material_description")))

        rows=[]
        for rec in sorted(groups.values(), key=lambda x: (x["casing"] != "No Casing", str(x["casing"]).upper())):
            saps=sorted(rec["related_saps"]); molds=sorted(rec["related_molds"]); desc=sorted(rec["descriptions"])
            rows.append({
                "casing": rec["casing"],
                "status": rec["status"],
                "related_saps": saps,
                "related_molds": molds,
                "related_saps_display": ", ".join(saps[:5]) + (" ..." if len(saps)>5 else ""),
                "related_molds_display": ", ".join(molds[:4]) + (" ..." if len(molds)>4 else ""),
                "search_blob": " ".join([rec["casing"], " ".join(saps), " ".join(molds), " ".join(desc)]),
            })
        return {"rows": rows, "latest_plan_date": cls._latest_live_context(session).get("plan_date")}

    @classmethod
    def resource_detail_snapshot(
        cls, session, *, resource_type: str, line: str = "", cavity: str = "",
        mold_code: str = "", casing: str = ""
    ) -> dict[str, Any]:
        cls.ensure_schema(session)
        rtype = _norm(resource_type)
        params = {"line": line, "cavity": cavity, "mold": mold_code, "casing": _norm(_canonical_casing(casing))}
        base_select = """
            SELECT plan_date,line_name,cavity_code,sap_code,item_description,mold_code,casing_type,shift_name,planned_qty
            FROM mpps_fi_plan_allocations
        """
        if rtype == "LINE":
            rows = cls._safe_rows(session, base_select + """
                WHERE LOWER(TRIM(line_name))=LOWER(TRIM(:line)) AND planned_qty>0
                ORDER BY plan_date DESC,id DESC LIMIT 12000
            """, params)
            title = line
        elif rtype == "CAVITY":
            rows = cls._safe_rows(session, base_select + """
                WHERE LOWER(TRIM(line_name))=LOWER(TRIM(:line))
                  AND LOWER(TRIM(cavity_code))=LOWER(TRIM(:cavity)) AND planned_qty>0
                ORDER BY plan_date DESC,id DESC LIMIT 12000
            """, params)
            title = f"{line} / {cavity}"
        elif rtype == "MOLD":
            rows = cls._safe_rows(session, base_select + """
                WHERE LOWER(TRIM(mold_code))=LOWER(TRIM(:mold)) AND planned_qty>0
                ORDER BY plan_date DESC,id DESC LIMIT 12000
            """, params)
            title = mold_code
        elif rtype == "CASING":
            rows = cls._safe_rows(session, base_select + """
                WHERE (CASE
                    WHEN UPPER(TRIM(COALESCE(casing_type,''))) IN ('-','--','NO CASING','NO-CASING','NONE','N/A','NA','NOT REQUIRED') THEN 'NO CASING'
                    ELSE UPPER(TRIM(COALESCE(casing_type,''))) END) = :casing
                  AND planned_qty>0
                ORDER BY plan_date DESC,id DESC LIMIT 12000
            """, params)
            title = _canonical_casing(casing) or casing
            # Add technical SAP mappings that have not yet appeared in an OVEN plan.
            mapped = cls._safe_rows(session, """
                SELECT NULL::date AS plan_date,'' AS line_name,'' AS cavity_code,TRIM(sap_code) AS sap_code,
                       COALESCE(material_description,'') AS item_description,'' AS mold_code,
                       COALESCE(casing_type,'') AS casing_type,'' AS shift_name,0 AS planned_qty
                FROM smds
                WHERE (CASE
                    WHEN UPPER(TRIM(COALESCE(casing_type,''))) IN ('-','--','NO CASING','NO-CASING','NONE','N/A','NA','NOT REQUIRED') THEN 'NO CASING'
                    ELSE UPPER(TRIM(COALESCE(casing_type,''))) END) = :casing
            """, params)
            rows.extend(mapped)
        else:
            rows = []
            title = resource_type

        grouped: dict[str, dict[str, Any]] = {}
        cavities: set[str] = set()
        dates: set[Any] = set()
        all_lines: set[str] = set()
        for r in rows:
            sap = _code(r.get("sap_code"))
            if not sap:
                continue
            g = grouped.setdefault(sap, {
                "sap_code": sap, "description": "", "molds": set(), "casings": set(),
                "cavities": set(), "lines": set(), "dates": set(), "last_seen": None, "planned_qty": 0,
            })
            if _text(r.get("item_description")):
                g["description"] = _text(r.get("item_description"))
            if _text(r.get("mold_code")):
                g["molds"].add(_text(r.get("mold_code")))
            canonical_casing = _canonical_casing(r.get("casing_type"))
            if canonical_casing:
                g["casings"].add(canonical_casing)
            if _text(r.get("cavity_code")):
                cav = _text(r.get("cavity_code")); g["cavities"].add(cav); cavities.add(cav)
            if _text(r.get("line_name")):
                ln = _text(r.get("line_name")); g["lines"].add(ln); all_lines.add(ln)
            d = r.get("plan_date")
            if d is not None:
                dates.add(d); g["dates"].add(d)
                if g["last_seen"] is None or d > g["last_seen"]:
                    g["last_seen"] = d
            g["planned_qty"] += max(0, _i(r.get("planned_qty")))

        out=[]
        for g in sorted(grouped.values(), key=lambda x: (str(x["last_seen"] or ""), x["sap_code"]), reverse=True):
            out.append({
                "sap_code": g["sap_code"],
                "description": g["description"],
                "mold_code": ", ".join(sorted(g["molds"])),
                "casing": ", ".join(sorted(g["casings"])),
                "lines": ", ".join(sorted(g["lines"])),
                "cavity_count": len(g["cavities"]),
                "observed_days": len(g["dates"]),
                "last_seen": g["last_seen"],
                "planned_qty": g["planned_qty"],
            })
        return {
            "resource_type": rtype, "title": title, "related_saps": len(out),
            "cavity_count": len(cavities), "line_count": len(all_lines),
            "observed_days": len(dates), "rows": out,
        }

    @classmethod
    def tab_snapshot(cls, session, tab: str) -> dict[str, Any]:
        tab=(tab or "overview").lower()
        if tab=="lines": return cls.production_lines_snapshot(session)
        if tab=="cavities": return cls.cavities_snapshot(session)
        if tab=="molds": return cls.molds_snapshot(session)
        if tab=="capacity":
            return {"rows": cls._safe_rows(session,"""
                SELECT p.*,COALESCE(s.material_description,'') AS item_description,
                       COALESCE(s.key_code,'') AS mold_key,COALESCE(s.casing_type,'') AS casing_type
                FROM mpps_fi_capacity_profiles p
                LEFT JOIN smds s ON p.model_level='SAP' AND TRIM(s.sap_code)=TRIM(p.entity_key)
                ORDER BY p.confidence_score DESC,p.sample_days DESC LIMIT 3000
            """)}
        if tab=="model":
            return {
                "acceleration": cls.runtime_acceleration().to_dict(),
                "model_runs": cls._safe_rows(session,"SELECT created_at,model_family,device,sample_count,validation_wape_pct,validation_mae,promoted,feature_version FROM mpps_fi_model_runs ORDER BY id DESC LIMIT 100"),
                "compatibility": cls._safe_rows(session,"SELECT * FROM mpps_fi_resource_compatibility ORDER BY confidence_score DESC,observed_days DESC LIMIT 1000"),
            }
        if tab=="casings":
            return cls.casings_snapshot(session)
        return {
            "state": cls._safe_row(session,"SELECT * FROM mpps_fi_state WHERE id=1"),
            "casing_pressure": cls.casing_pressure(session),
            "execution_observations": cls._safe_rows(session,"SELECT * FROM mpps_fi_execution_observations ORDER BY production_date DESC,sap_code LIMIT 150"),
        }

    @classmethod
    def initialize_if_needed(
        cls,
        session,
        *,
        progress_callback: Callable[[int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        """Perform only one-time/empty-state preparation for the V11 workspace.

        The old dashboard path seeded masters and bootstrapped historical OVEN data
        on every page refresh.  That made the Factory Capacity page feel slow even
        when nothing had changed.  This gate keeps those write-heavy operations
        out of normal page navigation while preserving first-run self-healing.
        """
        cls._progress(progress_callback, 5, "Preparing intelligence database", "Checking V11 schema")
        cls.ensure_schema(session)

        cached_state = cls._safe_row(
            session,
            """
            SELECT model_version, latest_plan_date, resource_observations,
                   execution_observations, capacity_profiles, high_confidence_profiles,
                   last_training_device, last_training_at, updated_at
            FROM mpps_fi_state WHERE id=1
            """,
        )
        if (
            _i(cached_state.get("resource_observations")) > 0
            or _i(cached_state.get("execution_observations")) > 0
            or _i(cached_state.get("capacity_profiles")) > 0
        ):
            cls._progress(
                progress_callback,
                60,
                "Intelligence cache ready",
                f"{_i(cached_state.get('execution_observations')):,} execution observations cached",
            )
            return {"state": cached_state, "cached_fast_path": True}

        counts = cls._safe_row(
            session,
            """
            SELECT
                (SELECT COUNT(*) FROM mpps_fi_resource_registry) AS resources,
                (SELECT COUNT(*) FROM mpps_fi_plan_allocations) AS allocations,
                (SELECT COUNT(*) FROM mpps_fi_execution_observations) AS executions,
                (SELECT COUNT(*) FROM mpps_fi_capacity_profiles) AS profiles
            """,
        )
        result: dict[str, Any] = {
            "resources_before": _i(counts.get("resources")),
            "allocations_before": _i(counts.get("allocations")),
            "executions_before": _i(counts.get("executions")),
            "profiles_before": _i(counts.get("profiles")),
        }

        cls._progress(progress_callback, 12, "Checking cached intelligence", "Using existing learned data where available")

        if result["resources_before"] <= 0:
            cls._progress(progress_callback, 20, "Loading factory resource register", "Production lines, cavities, molds and casings")
            result.update(cls.seed_technical_registry(session))
        else:
            cls._progress(progress_callback, 24, "Factory resource register ready", f"{result['resources_before']:,} learned/technical resources cached")

        if result["allocations_before"] <= 0:
            cls._progress(progress_callback, 32, "Preparing historical OVEN evidence", "One-time migration of already imported plans")
            result.update(cls.bootstrap_existing_history(session))
        else:
            cls._progress(progress_callback, 42, "Historical OVEN evidence ready", f"{result['allocations_before']:,} allocation observations cached")

        executions_now = _i(
            cls._safe_row(session, "SELECT COUNT(*) AS c FROM mpps_fi_execution_observations").get("c")
        )
        allocations_now = _i(
            cls._safe_row(session, "SELECT COUNT(*) AS c FROM mpps_fi_plan_allocations").get("c")
        )
        if executions_now <= 0 and allocations_now > 0:
            cls._progress(progress_callback, 50, "Linking plan to verified actual", "Building first execution-observation cache")
            result.update(cls.rebuild_execution_observations(session))
        else:
            cls._progress(progress_callback, 56, "Execution evidence ready", f"{executions_now:,} verified plan-vs-actual observations cached")

        # Keep the state row current after first-run preparation.  Normal dashboard
        # refreshes read this cached state instead of recounting/reseeding everything.
        result["state"] = cls.refresh_state(session)
        cls._progress(progress_callback, 60, "Intelligence cache ready", "Loading the current workspace snapshot")
        return result

    @classmethod
    def dashboard(
        cls,
        session,
        *,
        limit: int = 1000,
        prepare: bool = True,
        progress_callback: Callable[[int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        cls.ensure_schema(session)
        if prepare:
            cls.initialize_if_needed(session, progress_callback=progress_callback)
            state = cls.refresh_state(session)
        else:
            state = cls._safe_row(
                session,
                """
                SELECT model_version, latest_plan_date, resource_observations,
                       execution_observations, capacity_profiles, high_confidence_profiles,
                       last_training_device, last_training_at, updated_at
                FROM mpps_fi_state WHERE id=1
                """,
            )
            if not state:
                state = cls.refresh_state(session)

        cls._progress(progress_callback, 68, "Loading resource intelligence", "Reading cached production resources")
        acceleration = cls.runtime_acceleration().to_dict()
        resources = cls._safe_rows(
            session,
            """
            SELECT * FROM mpps_fi_resource_registry
            ORDER BY resource_type, lifecycle_status, canonical_name
            """,
        )
        cls._progress(progress_callback, 76, "Loading capacity profiles", "Reading learned safe / expected / stretch models")
        profiles = cls._safe_rows(
            session,
            """
            SELECT p.*,
                   COALESCE(s.material_description,'') AS item_description,
                   COALESCE(s.key_code,'') AS mold_key,
                   COALESCE(s.casing_type,'') AS casing_type
            FROM mpps_fi_capacity_profiles p
            LEFT JOIN smds s
              ON p.model_level='SAP' AND TRIM(s.sap_code)=TRIM(p.entity_key)
            ORDER BY CASE WHEN p.model_level='FACTORY' THEN 0 WHEN p.model_level='SAP' THEN 1 ELSE 2 END,
                     p.confidence_score DESC, p.sample_days DESC
            LIMIT :limit
            """,
            {"limit": max(1, min(int(limit), 10000))},
        )
        cls._progress(progress_callback, 84, "Loading execution evidence", "Reading recent plan-vs-actual resource evidence")
        latest_obs = cls._safe_rows(
            session,
            """
            SELECT *
            FROM mpps_fi_execution_observations
            ORDER BY production_date DESC, sap_code
            LIMIT :limit
            """,
            {"limit": max(1, min(int(limit), 10000))},
        )
        cls._progress(progress_callback, 90, "Loading learned compatibility", "SAP, line, mold, cavity and casing evidence")
        compatibility = cls._safe_rows(
            session,
            """
            SELECT *
            FROM mpps_fi_resource_compatibility
            ORDER BY confidence_score DESC, observed_days DESC
            LIMIT :limit
            """,
            {"limit": max(1, min(int(limit), 10000))},
        )
        model_runs = cls._safe_rows(
            session,
            """
            SELECT created_at, model_family, device, sample_count,
                   validation_wape_pct, validation_mae, promoted, feature_version
            FROM mpps_fi_model_runs
            ORDER BY id DESC
            LIMIT 100
            """,
        )
        cls._progress(progress_callback, 95, "Checking shared casing pressure", "Applying current open-shipment demand")
        casing_pressure = cls.casing_pressure(session)
        cls._progress(progress_callback, 99, "Finalizing workspace", "Preparing responsive table snapshot")
        return {
            "state": state,
            "acceleration": acceleration,
            "resources": resources,
            "profiles": profiles,
            "execution_observations": latest_obs,
            "compatibility": compatibility,
            "model_runs": model_runs,
            "casing_pressure": casing_pressure,
        }


__all__ = [
    "FactoryResourceIntelligenceService",
    "CapacityResolution",
    "AccelerationInfo",
]
