from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from sqlalchemy import text


@dataclass(frozen=True)
class OperationalSource:
    """Latest workbook allowed to drive live factory operations."""

    plan_date: date | None = None
    workbook_name: str = ""
    import_run_id: int | None = None
    sync_run_id: int | None = None
    confidence_pct: float = 0.0
    authority: str = "NONE"
    sync_confirmed: bool = False

    @property
    def next_planning_date(self) -> date:
        return (self.plan_date or date.today()) + timedelta(days=1)

    @property
    def label(self) -> str:
        if not self.plan_date:
            return "Live OVEN: not imported"
        return f"Live OVEN: {self.plan_date.isoformat()}"


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


class OperationalSourceService:
    """Resolve the single operational workbook authority.

    V10.2 integrity rule:
      * the highest committed, non-rolled-back workbook plan date is the
        operational date;
      * a committed LIVE sync run is preferred on the same plan date because it
        proves shipment synchronization completed;
      * a newer committed import can never be hidden by an older LIVE sync row;
      * older committed workbooks remain historical/ML evidence and can never
        move the operational cutoff backwards.

    This fixes the V10.1 edge case where an older LIVE sync row (for example
    2026-08-04) could mask a newer successfully committed import (for example
    2026-08-10).
    """

    @staticmethod
    def _candidate_key(candidate: Mapping[str, Any]) -> tuple:
        plan_date = _as_date(candidate.get("plan_date")) or date.min
        sync_confirmed = bool(candidate.get("sync_confirmed"))
        run_id = int(candidate.get("sync_run_id") or candidate.get("import_run_id") or 0)
        # Newest date first. On a tie prefer LIVE-sync confirmation, then latest id.
        return (plan_date, int(sync_confirmed), run_id)

    @classmethod
    def _pick_newest_candidate(cls, candidates: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        valid = [candidate for candidate in candidates if _as_date(candidate.get("plan_date"))]
        if not valid:
            return None
        return max(valid, key=cls._candidate_key)

    @staticmethod
    def _to_source(candidate: Mapping[str, Any] | None) -> OperationalSource:
        if not candidate:
            return OperationalSource()
        raw_confidence = float(candidate.get("confidence_score") or 0.0)
        confidence_pct = raw_confidence * 100.0 if raw_confidence <= 1.5 else raw_confidence
        return OperationalSource(
            plan_date=_as_date(candidate.get("plan_date")),
            workbook_name=str(candidate.get("workbook_name") or ""),
            import_run_id=int(candidate["import_run_id"]) if candidate.get("import_run_id") else None,
            sync_run_id=int(candidate["sync_run_id"]) if candidate.get("sync_run_id") else None,
            confidence_pct=confidence_pct,
            authority=str(candidate.get("authority") or "COMMITTED IMPORT"),
            sync_confirmed=bool(candidate.get("sync_confirmed")),
        )

    @classmethod
    def latest(cls, session) -> OperationalSource:
        candidates: list[dict[str, Any]] = []

        # Strongest evidence: a committed LIVE shipment-sync run.
        try:
            row = session.execute(
                text(
                    """
                    SELECT
                        sr.id AS sync_run_id,
                        sr.import_run_id,
                        sr.plan_date,
                        COALESCE(ir.workbook_name, sr.workbook_name, '') AS workbook_name,
                        COALESCE(ir.confidence_score, 0) AS confidence_score
                    FROM excel_shipment_sync_runs sr
                    LEFT JOIN excel_import_runs ir ON ir.id = sr.import_run_id
                    WHERE sr.sync_mode = 'LIVE'
                      AND sr.status = 'COMMITTED'
                      AND sr.rollback_at IS NULL
                      AND COALESCE(ir.rollback_at IS NULL, TRUE)
                      AND sr.plan_date IS NOT NULL
                    ORDER BY sr.plan_date DESC, sr.id DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if row:
                candidate = dict(row)
                candidate.update({"authority": "LIVE SYNC", "sync_confirmed": True})
                candidates.append(candidate)
        except Exception:
            # Older installations may not yet contain continuous-sync tables.
            pass

        # Independent committed-import candidate. Crucially, this is compared
        # against the LIVE-sync candidate instead of being used only as a fallback.
        try:
            row = session.execute(
                text(
                    """
                    SELECT
                        id AS import_run_id,
                        plan_date,
                        workbook_name,
                        COALESCE(confidence_score, 0) AS confidence_score
                    FROM excel_import_runs
                    WHERE status IN ('COMMITTED', 'COMMITTED WITH WARNINGS')
                      AND rollback_at IS NULL
                      AND plan_date IS NOT NULL
                    ORDER BY plan_date DESC, id DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if row:
                candidate = dict(row)
                candidate.update({"authority": "COMMITTED IMPORT", "sync_confirmed": False})
                candidates.append(candidate)
        except Exception:
            pass

        return cls._to_source(cls._pick_newest_candidate(candidates))

    @classmethod
    def live_date(cls, session, fallback: date | None = None) -> date:
        return cls.latest(session).plan_date or fallback or date.today()

    @classmethod
    def next_plan_date(cls, session, fallback: date | None = None) -> date:
        source = cls.latest(session)
        if source.plan_date:
            return source.plan_date + timedelta(days=1)
        return (fallback or date.today()) + timedelta(days=1)

    @classmethod
    def is_historical(cls, session, candidate_plan_date: date) -> bool:
        latest = cls.latest(session).plan_date
        return bool(latest and candidate_plan_date < latest)


def source_dict(source: OperationalSource) -> dict[str, Any]:
    return {
        "plan_date": source.plan_date.isoformat() if source.plan_date else None,
        "workbook_name": source.workbook_name,
        "import_run_id": source.import_run_id,
        "sync_run_id": source.sync_run_id,
        "confidence_pct": round(source.confidence_pct, 2),
        "authority": source.authority,
        "sync_confirmed": source.sync_confirmed,
        "next_planning_date": source.next_planning_date.isoformat(),
    }
