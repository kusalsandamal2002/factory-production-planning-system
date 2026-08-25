from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from hashlib import sha1
import json
import re
from typing import Any, Iterable

from openpyxl.utils import column_index_from_string
from sqlalchemy import text


# INTELLIGENT CONTINUOUS EXCEL SYNC + LEARNING FOUNDATION V7.0

ACTIVE_SOURCE_STATUSES = {"OK", "YES", "ACTIVE"}
GENERIC_SHIPMENT_NAMES = {
    "",
    "DUMMY",
    "SHIPMENT",
    "SHIP",
    "ORDER",
    "CUSTOMER",
}
CLOSED_OR_PROTECTED_STATUSES = {
    "cancelled",
    "canceled",
    "closed",
    "complete",
    "completed",
    "shipped",
    "done",
    "on hold",
    "hold",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _norm(value: Any) -> str:
    value = _text(value).upper()
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _code(value: Any) -> str:
    value = _text(value)
    if re.fullmatch(r"\d+\.0", value):
        value = value[:-2]
    return value.upper()


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except Exception:
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return value


def _source_base_key(name: str) -> str:
    normalized = _norm(name)
    return normalized or "UNNAMED"


def _identity_key(base_key: str, suffix: str = "") -> str:
    seed = f"OVEN_SHEET|{base_key}|{suffix}"
    digest = sha1(seed.encode("utf-8")).hexdigest()[:24].upper()
    return f"OVEN-{digest}"


def _shipment_no(identity_key: str) -> str:
    return f"XLS-SYNC-{identity_key.split('-')[-1][:12]}"


def _column_sort_key(column_name: str) -> tuple[int, str]:
    try:
        return (
            column_index_from_string(_text(column_name).upper()),
            _text(column_name),
        )
    except Exception:
        return (10**9, _text(column_name))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


@dataclass
class ShipmentGroup:
    shipment_column: str
    shipment_name: str
    source_status: str
    source_target_date: date | None
    source_date_class: str
    items: dict[str, dict[str, Any]]
    total_qty: int
    item_count: int
    base_key: str
    identity_key: str = ""
    identity_id: int | None = None
    canonical_shipment_id: int | None = None

    @property
    def sap_codes(self) -> set[str]:
        return set(self.items)

    @property
    def is_generic(self) -> bool:
        return self.base_key in GENERIC_SHIPMENT_NAMES

    @property
    def source_active(self) -> bool:
        return self.source_status in ACTIVE_SOURCE_STATUSES


@dataclass
class SyncPreviewRow:
    action: str
    identity_key: str
    shipment_column: str
    shipment_name: str
    existing_shipment_id: int | None
    existing_shipment_no: str
    source_status: str
    source_target_date: str
    source_date_class: str
    old_item_count: int
    new_item_count: int
    old_total_qty: int
    new_total_qty: int
    changed_items: int
    new_items: int
    removed_items: int
    conflicts: int
    manual_fields_preserved: int
    reason: str


@dataclass
class SyncPreview:
    mode: str
    reason: str
    plan_date: str
    latest_live_plan_date: str
    rows: list[SyncPreviewRow] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "plan_date": self.plan_date,
            "latest_live_plan_date": self.latest_live_plan_date,
            "rows": [asdict(row) for row in self.rows],
            "summary": dict(self.summary),
        }


class WorkbookContinuousSyncService:
    """Duplicate-safe, revision-aware shipment synchronizer.

    The service keeps every workbook as a dated snapshot, but only the newest
    allowed revision changes live stock/shipment records. It preserves manual
    target dates, completed/produced quantities, holds and user-owned notes.
    """

    SOURCE_FAMILY = "OVEN_SHEET"

    def __init__(self, project_root=None):
        self.project_root = project_root

    @staticmethod
    def ensure_schema(session) -> None:
        statements = [
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_family TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_identity_key TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_latest_run_id BIGINT
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_latest_plan_date DATE
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_latest_workbook TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_latest_column TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_latest_status TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_missing_from_latest BOOLEAN NOT NULL DEFAULT FALSE
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_revision_no INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_sync_status TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipments
            ADD COLUMN IF NOT EXISTS source_sync_note TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_item_key TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_latest_run_id BIGINT
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_latest_plan_date DATE
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_latest_qty INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_removed_from_latest BOOLEAN NOT NULL DEFAULT FALSE
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_revision_no INTEGER NOT NULL DEFAULT 0
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_sync_status TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_sync_note TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE mpps_shipment_items
            ADD COLUMN IF NOT EXISTS source_manual_lock BOOLEAN NOT NULL DEFAULT FALSE
            """,
            """
            ALTER TABLE excel_import_shipment_snapshots
            ADD COLUMN IF NOT EXISTS source_target_date DATE
            """,
            """
            ALTER TABLE excel_import_shipment_snapshots
            ADD COLUMN IF NOT EXISTS source_date_class TEXT NOT NULL DEFAULT ''
            """,
            """
            ALTER TABLE excel_import_shipment_snapshots
            ADD COLUMN IF NOT EXISTS source_identity_key TEXT NOT NULL DEFAULT ''
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_shipment_identities (
                id BIGSERIAL PRIMARY KEY,
                source_family TEXT NOT NULL,
                identity_key TEXT NOT NULL,
                base_key TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                canonical_shipment_id BIGINT,
                first_seen_plan_date DATE,
                last_seen_plan_date DATE,
                latest_run_id BIGINT,
                latest_workbook_hash TEXT NOT NULL DEFAULT '',
                latest_workbook_name TEXT NOT NULL DEFAULT '',
                latest_column TEXT NOT NULL DEFAULT '',
                latest_status TEXT NOT NULL DEFAULT '',
                latest_item_fingerprint TEXT NOT NULL DEFAULT '',
                latest_total_qty INTEGER NOT NULL DEFAULT 0,
                latest_item_count INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                missing_since_plan_date DATE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_family, identity_key)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_excel_shipment_identities_base
            ON excel_shipment_identities(source_family, base_key, is_active)
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_shipment_sync_runs (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT,
                workbook_hash TEXT NOT NULL DEFAULT '',
                workbook_name TEXT NOT NULL DEFAULT '',
                plan_date DATE,
                sync_mode VARCHAR(20) NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'RUNNING',
                reason TEXT NOT NULL DEFAULT '',
                new_shipments INTEGER NOT NULL DEFAULT 0,
                updated_shipments INTEGER NOT NULL DEFAULT 0,
                unchanged_shipments INTEGER NOT NULL DEFAULT 0,
                deferred_shipments INTEGER NOT NULL DEFAULT 0,
                missing_shipments INTEGER NOT NULL DEFAULT 0,
                review_shipments INTEGER NOT NULL DEFAULT 0,
                new_items INTEGER NOT NULL DEFAULT 0,
                changed_items INTEGER NOT NULL DEFAULT 0,
                removed_items INTEGER NOT NULL DEFAULT 0,
                conflict_items INTEGER NOT NULL DEFAULT 0,
                manual_fields_preserved INTEGER NOT NULL DEFAULT 0,
                details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                rollback_at TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_excel_shipment_sync_runs_date
            ON excel_shipment_sync_runs(plan_date DESC, id DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_shipment_sync_rows (
                id BIGSERIAL PRIMARY KEY,
                sync_run_id BIGINT NOT NULL
                    REFERENCES excel_shipment_sync_runs(id)
                    ON DELETE CASCADE,
                import_run_id BIGINT,
                identity_id BIGINT,
                identity_key TEXT NOT NULL DEFAULT '',
                canonical_shipment_id BIGINT,
                shipment_column TEXT NOT NULL DEFAULT '',
                shipment_name TEXT NOT NULL DEFAULT '',
                action VARCHAR(40) NOT NULL,
                source_status TEXT NOT NULL DEFAULT '',
                source_target_date DATE,
                old_total_qty INTEGER NOT NULL DEFAULT 0,
                new_total_qty INTEGER NOT NULL DEFAULT 0,
                old_item_count INTEGER NOT NULL DEFAULT 0,
                new_item_count INTEGER NOT NULL DEFAULT 0,
                changed_items INTEGER NOT NULL DEFAULT 0,
                new_items INTEGER NOT NULL DEFAULT 0,
                removed_items INTEGER NOT NULL DEFAULT 0,
                conflicts INTEGER NOT NULL DEFAULT 0,
                manual_fields_preserved INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_authoritative_shipment_archive (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT,
                archived_plan_date DATE,
                archived_workbook TEXT NOT NULL DEFAULT '',
                previous_shipment_id BIGINT,
                previous_shipment_no TEXT NOT NULL DEFAULT '',
                previous_source_family TEXT NOT NULL DEFAULT '',
                shipment_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                reason TEXT NOT NULL DEFAULT '',
                archived_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_excel_authoritative_shipment_archive_run
            ON excel_authoritative_shipment_archive(import_run_id, archived_at DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS excel_shipment_item_revisions (
                id BIGSERIAL PRIMARY KEY,
                sync_run_id BIGINT NOT NULL
                    REFERENCES excel_shipment_sync_runs(id)
                    ON DELETE CASCADE,
                import_run_id BIGINT,
                identity_key TEXT NOT NULL DEFAULT '',
                shipment_id BIGINT,
                shipment_item_id BIGINT,
                sap_code TEXT NOT NULL,
                action VARCHAR(40) NOT NULL,
                old_qty INTEGER NOT NULL DEFAULT 0,
                new_qty INTEGER NOT NULL DEFAULT 0,
                produced_qty INTEGER NOT NULL DEFAULT 0,
                completed_qty INTEGER NOT NULL DEFAULT 0,
                protected_actual BOOLEAN NOT NULL DEFAULT FALSE,
                conflict BOOLEAN NOT NULL DEFAULT FALSE,
                reason TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_mpps_shipments_source_identity
            ON mpps_shipments(source_family, source_identity_key)
            WHERE source_family <> '' AND source_identity_key <> ''
            """,
        ]
        for statement in statements:
            session.execute(text(statement))

    @staticmethod
    def _group_analysis(analysis) -> list[ShipmentGroup]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in analysis.shipment_rows:
            grouped[_text(row.get("shipment_column"))].append(dict(row))

        groups: list[ShipmentGroup] = []
        for column in sorted(grouped, key=_column_sort_key):
            rows = grouped[column]
            first = rows[0]
            items: dict[str, dict[str, Any]] = {}
            for row in rows:
                code = _code(row.get("sap_code"))
                if not code:
                    continue
                quantity = _safe_int(row.get("quantity"))
                if code in items:
                    items[code]["quantity"] += quantity
                else:
                    items[code] = {
                        "sap_code": code,
                        "description": _text(row.get("description")),
                        "quantity": quantity,
                        "source_row": row.get("source_row"),
                    }

            source_target = first.get("source_target_date")
            if isinstance(source_target, str) and source_target:
                try:
                    source_target = date.fromisoformat(source_target)
                except Exception:
                    source_target = None
            elif isinstance(source_target, datetime):
                source_target = source_target.date()
            elif not isinstance(source_target, date):
                source_target = None

            name = _text(first.get("shipment_name"))
            groups.append(
                ShipmentGroup(
                    shipment_column=column,
                    shipment_name=name,
                    source_status=_text(first.get("source_status")).upper(),
                    source_target_date=source_target,
                    source_date_class=_text(first.get("source_date_class")),
                    items=items,
                    total_qty=sum(item["quantity"] for item in items.values()),
                    item_count=len(items),
                    base_key=_source_base_key(name),
                )
            )
        return groups

    @staticmethod
    def _item_fingerprint(group: ShipmentGroup) -> str:
        payload = "|".join(sorted(group.sap_codes))
        return sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _latest_live_plan_date(session) -> date | None:
        return session.execute(
            text(
                """
                SELECT MAX(plan_date)
                FROM excel_shipment_sync_runs
                WHERE sync_mode = 'LIVE'
                  AND status = 'COMMITTED'
                  AND rollback_at IS NULL
                """
            )
        ).scalar()

    def resolve_mode(
        self,
        session,
        analysis,
        options: dict[str, Any] | None = None,
    ) -> tuple[str, str, date | None]:
        options = options or {}
        plan_date = (
            date.fromisoformat(analysis.plan_date)
            if analysis.plan_date
            else date.today()
        )
        latest = self._latest_live_plan_date(session)
        if options.get("force_historical_snapshot"):
            return (
                "HISTORICAL",
                "Historical Snapshot Only was selected by the user.",
                latest,
            )
        if options.get("force_live_revision"):
            return (
                "LIVE",
                "Live Revision Sync was explicitly selected by the user.",
                latest,
            )
        if options.get("auto_detect_import_mode", True) and latest and plan_date < latest:
            return (
                "HISTORICAL",
                (
                    f"Workbook plan date {plan_date.isoformat()} is older than "
                    f"the latest live revision {latest.isoformat()}."
                ),
                latest,
            )
        if options.get("authoritative_latest_shipments", False):
            return (
                "LIVE",
                (
                    "Workbook is the newest eligible revision. Its shipment "
                    "snapshot is FINAL/authoritative: previous Excel-managed "
                    "live shipments will be archived and replaced by this workbook."
                ),
                latest,
            )
        return (
            "LIVE",
            "Workbook is the newest eligible revision and may update live data.",
            latest,
        )

    def _load_identities(self, session) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT
                        identity.*,
                        shipment.status AS canonical_status,
                        shipment.planning_status AS canonical_planning_status
                    FROM excel_shipment_identities identity
                    LEFT JOIN mpps_shipments shipment
                      ON shipment.id = identity.canonical_shipment_id
                    WHERE identity.source_family = :source_family
                    ORDER BY identity.id
                    """
                ),
                {"source_family": self.SOURCE_FAMILY},
            ).mappings().all()
        ]

    @staticmethod
    def _identity_item_sets(session, identities: Iterable[dict[str, Any]]) -> dict[int, set[str]]:
        ids = [int(row["id"]) for row in identities]
        if not ids:
            return {}
        result: dict[int, set[str]] = defaultdict(set)
        rows = session.execute(
            text(
                """
                SELECT
                    identity.id AS identity_id,
                    item.sap_code
                FROM excel_shipment_identities identity
                JOIN mpps_shipment_items item
                  ON item.shipment_id = identity.canonical_shipment_id
                WHERE identity.id = ANY(:identity_ids)
                  AND COALESCE(item.quantity, 0) > 0
                """
            ),
            {"identity_ids": ids},
        ).mappings().all()
        for row in rows:
            result[int(row["identity_id"])].add(_code(row["sap_code"]))
        return result

    def _assign_identities(
        self,
        session,
        groups: list[ShipmentGroup],
    ) -> None:
        identities = self._load_identities(session)
        by_base: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for identity in identities:
            by_base[_text(identity.get("base_key"))].append(identity)
        item_sets = self._identity_item_sets(session, identities)

        groups_by_base: dict[str, list[ShipmentGroup]] = defaultdict(list)
        for group in groups:
            groups_by_base[group.base_key].append(group)

        for base_key, current_groups in groups_by_base.items():
            existing = list(by_base.get(base_key, []))
            current_groups.sort(key=lambda group: _column_sort_key(group.shipment_column))

            if len(current_groups) == 1:
                group = current_groups[0]
                open_identities = [
                    row
                    for row in existing
                    if bool(row.get("is_active", True))
                    and _text(
                        row.get("canonical_status")
                    ).lower()
                    not in CLOSED_OR_PROTECTED_STATUSES
                ]
                identity = (
                    open_identities[0]
                    if open_identities
                    else None
                )
                if identity:
                    group.identity_key = _text(identity["identity_key"])
                    group.identity_id = int(identity["id"])
                    canonical = identity.get("canonical_shipment_id")
                    group.canonical_shipment_id = (
                        int(canonical)
                        if canonical
                        else None
                    )
                elif existing:
                    # A completed/closed shipment with the same display name
                    # must remain historical. Start a new stable generation
                    # instead of overwriting protected actual production.
                    generation = len(existing) + 1
                    candidate = _identity_key(
                        base_key,
                        f"GEN-{generation}",
                    )
                    existing_keys = {
                        _text(row.get("identity_key"))
                        for row in existing
                    }
                    while candidate in existing_keys:
                        generation += 1
                        candidate = _identity_key(
                            base_key,
                            f"GEN-{generation}",
                        )
                    group.identity_key = candidate
                else:
                    group.identity_key = _identity_key(base_key)
                continue

            available_existing = {
                int(row["id"]): row
                for row in existing
                if bool(row.get("is_active", True))
                and _text(
                    row.get("canonical_status")
                ).lower()
                not in CLOSED_OR_PROTECTED_STATUSES
            }
            existing_identity_keys = {
                _text(row.get("identity_key"))
                for row in existing
            }
            for group in current_groups:
                best: tuple[float, int] | None = None
                for identity_id, identity in available_existing.items():
                    score = _jaccard(
                        group.sap_codes,
                        item_sets.get(identity_id, set()),
                    )
                    if best is None or score > best[0]:
                        best = (score, identity_id)
                if best and best[0] >= 0.35:
                    identity = available_existing.pop(best[1])
                    group.identity_key = _text(identity["identity_key"])
                    group.identity_id = int(identity["id"])
                    canonical = identity.get("canonical_shipment_id")
                    group.canonical_shipment_id = int(canonical) if canonical else None
                else:
                    suffix = self._item_fingerprint(group)[:10].upper()
                    candidate = _identity_key(base_key, suffix)
                    used = {
                        g.identity_key
                        for g in current_groups
                        if g.identity_key
                    }
                    if (
                        candidate in used
                        or candidate in existing_identity_keys
                    ):
                        candidate = _identity_key(
                            base_key,
                            f"{suffix}-{group.shipment_column}",
                        )
                    generation = 2
                    while (
                        candidate in used
                        or candidate in existing_identity_keys
                    ):
                        candidate = _identity_key(
                            base_key,
                            (
                                f"{suffix}-{group.shipment_column}-"
                                f"GEN-{generation}"
                            ),
                        )
                        generation += 1
                    group.identity_key = candidate

    @classmethod
    def _find_legacy_canonical_shipment(
        cls,
        session,
        identity_key: str,
    ) -> dict[str, Any] | None:
        """Adopt a shipment created by an older sync generation.

        V7 builds could already have written ``source_family`` /
        ``source_identity_key`` or the deterministic ``shipment_no`` before
        the V8 ``excel_shipment_identities`` registry existed.  Without this
        bridge V8 can attempt a second INSERT and PostgreSQL correctly raises
        a unique-integrity error.  Prefer an exact source identity, then fall
        back to the deterministic shipment number.
        """
        key = _text(identity_key)
        if not key:
            return None
        stable_no = _shipment_no(key)
        return session.execute(
            text(
                """
                SELECT *
                FROM mpps_shipments
                WHERE (source_family = :source_family
                       AND source_identity_key = :identity_key)
                   OR shipment_no = :shipment_no
                ORDER BY
                    CASE
                        WHEN source_family = :source_family
                         AND source_identity_key = :identity_key THEN 0
                        ELSE 1
                    END,
                    id
                LIMIT 1
                """
            ),
            {
                "source_family": cls.SOURCE_FAMILY,
                "identity_key": key,
                "shipment_no": stable_no,
            },
        ).mappings().first()

    @staticmethod
    def _load_shipment(session, shipment_id: int | None) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
        if not shipment_id:
            return None, {}
        shipment = session.execute(
            text("SELECT * FROM mpps_shipments WHERE id = :id"),
            {"id": int(shipment_id)},
        ).mappings().first()
        if not shipment:
            return None, {}
        items = session.execute(
            text(
                """
                SELECT *
                FROM mpps_shipment_items
                WHERE shipment_id = :shipment_id
                ORDER BY id
                """
            ),
            {"shipment_id": int(shipment_id)},
        ).mappings().all()
        return dict(shipment), {_code(row["sap_code"]): dict(row) for row in items}

    @staticmethod
    def _manual_fields_count(shipment: dict[str, Any] | None) -> int:
        if not shipment:
            return 0
        count = 0
        if bool(shipment.get("target_date_is_manual")):
            count += 1
        if _text(shipment.get("status")).lower() in CLOSED_OR_PROTECTED_STATUSES:
            count += 1
        if _text(shipment.get("note")):
            count += 1
        return count

    def preview_with_session(
        self,
        session,
        analysis,
        options: dict[str, Any] | None = None,
    ) -> SyncPreview:
        self.ensure_schema(session)
        options = options or {}
        mode, reason, latest = self.resolve_mode(session, analysis, options)
        plan_date = (
            date.fromisoformat(analysis.plan_date)
            if analysis.plan_date
            else date.today()
        )
        groups = self._group_analysis(analysis)
        self._assign_identities(session, groups)

        rows: list[SyncPreviewRow] = []
        seen_identity_keys: set[str] = set()

        for group in groups:
            seen_identity_keys.add(group.identity_key)
            shipment, existing_items = self._load_shipment(
                session,
                group.canonical_shipment_id,
            )
            old_codes = {
                code
                for code, item in existing_items.items()
                if _safe_int(item.get("quantity")) > 0
                and not bool(item.get("source_removed_from_latest"))
            }
            new_codes = set(group.items)
            new_items = len(new_codes - old_codes)
            removed_items = len(old_codes - new_codes)
            changed_items = 0
            conflicts = 0

            for code in old_codes & new_codes:
                old_item = existing_items[code]
                old_qty = _safe_int(old_item.get("quantity"))
                new_qty = _safe_int(group.items[code].get("quantity"))
                if old_qty != new_qty:
                    changed_items += 1
                protected_floor = max(
                    _safe_int(old_item.get("produced_qty")),
                    _safe_int(old_item.get("completed_qty")),
                )
                if new_qty < protected_floor:
                    conflicts += 1
            for code in old_codes - new_codes:
                old_item = existing_items[code]
                if (
                    _safe_int(old_item.get("produced_qty")) > 0
                    or _safe_int(old_item.get("completed_qty")) > 0
                    or bool(old_item.get("source_manual_lock"))
                ):
                    conflicts += 1

            old_total = sum(_safe_int(item.get("quantity")) for item in existing_items.values())
            old_item_count = len(old_codes)
            manual_preserved = self._manual_fields_count(shipment)

            if group.is_generic:
                action = "IGNORED_GENERIC"
                action_reason = "Generic shipment header is retained only in the snapshot."
            elif mode == "HISTORICAL":
                action = "SNAPSHOT_ONLY"
                action_reason = reason
            elif not group.source_active and not options.get("sync_deferred_shipments", False):
                action = "DEFERRED"
                action_reason = (
                    f"Source status {group.source_status or '-'} is not active; "
                    "the demand remains in the dated snapshot."
                )
            elif shipment is None:
                action = "NEW"
                action_reason = "No canonical live shipment exists for this stable identity."
            elif conflicts:
                action = "REVIEW"
                action_reason = (
                    "The new workbook would reduce or remove quantities below "
                    "recorded production/completion or a manual item lock."
                )
            elif new_items or removed_items or changed_items or old_total != group.total_qty:
                action = "UPDATED"
                action_reason = "Shipment items or quantities changed in the latest workbook revision."
            else:
                action = "UNCHANGED"
                action_reason = "The live shipment already matches this workbook revision."

            rows.append(
                SyncPreviewRow(
                    action=action,
                    identity_key=group.identity_key,
                    shipment_column=group.shipment_column,
                    shipment_name=group.shipment_name,
                    existing_shipment_id=int(shipment["id"]) if shipment else None,
                    existing_shipment_no=_text(shipment.get("shipment_no")) if shipment else "",
                    source_status=group.source_status,
                    source_target_date=(
                        group.source_target_date.isoformat()
                        if group.source_target_date
                        else ""
                    ),
                    source_date_class=group.source_date_class,
                    old_item_count=old_item_count,
                    new_item_count=group.item_count,
                    old_total_qty=old_total,
                    new_total_qty=group.total_qty,
                    changed_items=changed_items,
                    new_items=new_items,
                    removed_items=removed_items,
                    conflicts=conflicts,
                    manual_fields_preserved=manual_preserved,
                    reason=action_reason,
                )
            )

        if mode == "LIVE" and options.get("mark_missing_shipments", True):
            for identity in self._load_identities(session):
                key = _text(identity.get("identity_key"))
                if not key or key in seen_identity_keys or not bool(identity.get("is_active", True)):
                    continue
                shipment, existing_items = self._load_shipment(
                    session,
                    int(identity["canonical_shipment_id"])
                    if identity.get("canonical_shipment_id")
                    else None,
                )
                if not shipment:
                    continue
                last_seen = identity.get("last_seen_plan_date")
                if last_seen and isinstance(last_seen, datetime):
                    last_seen = last_seen.date()
                if last_seen and plan_date < last_seen:
                    continue
                actual_qty = sum(
                    max(
                        _safe_int(item.get("produced_qty")),
                        _safe_int(item.get("completed_qty")),
                    )
                    for item in existing_items.values()
                )
                manual_preserved = self._manual_fields_count(shipment)
                conflicts = 1 if actual_qty > 0 or manual_preserved else 0
                rows.append(
                    SyncPreviewRow(
                        action=("REVIEW_MISSING" if conflicts else "MISSING_FROM_LATEST"),
                        identity_key=key,
                        shipment_column=_text(identity.get("latest_column")),
                        shipment_name=_text(identity.get("display_name")),
                        existing_shipment_id=int(shipment["id"]),
                        existing_shipment_no=_text(shipment.get("shipment_no")),
                        source_status="MISSING",
                        source_target_date="",
                        source_date_class="",
                        old_item_count=len(existing_items),
                        new_item_count=0,
                        old_total_qty=sum(
                            _safe_int(item.get("quantity"))
                            for item in existing_items.values()
                        ),
                        new_total_qty=0,
                        changed_items=0,
                        new_items=0,
                        removed_items=len(existing_items),
                        conflicts=conflicts,
                        manual_fields_preserved=manual_preserved,
                        reason=(
                            "Shipment is absent from the latest workbook but has actual/manual data; review is required."
                            if conflicts
                            else "Shipment is absent from the newest live workbook and will be excluded without deletion."
                        ),
                    )
                )

        counts = Counter(row.action.lower() for row in rows)
        summary = {
            "total_rows": len(rows),
            "new_shipments": counts["new"],
            "updated_shipments": counts["updated"],
            "unchanged_shipments": counts["unchanged"],
            "deferred_shipments": counts["deferred"] + counts["ignored_generic"],
            "snapshot_only_shipments": counts["snapshot_only"],
            "missing_shipments": counts["missing_from_latest"],
            "review_shipments": counts["review"] + counts["review_missing"],
            "new_items": sum(row.new_items for row in rows),
            "changed_items": sum(row.changed_items for row in rows),
            "removed_items": sum(row.removed_items for row in rows),
            "conflict_items": sum(row.conflicts for row in rows),
            "manual_fields_preserved": sum(row.manual_fields_preserved for row in rows),
        }
        return SyncPreview(
            mode=mode,
            reason=reason,
            plan_date=plan_date.isoformat(),
            latest_live_plan_date=latest.isoformat() if latest else "",
            rows=rows,
            summary=summary,
        )

    def preview(self, analysis, options: dict[str, Any] | None = None) -> dict[str, Any]:
        from app.database import get_session

        with get_session() as session:
            return self.preview_with_session(session, analysis, options).to_dict()

    @staticmethod
    def _insert_sync_row(session, sync_run_id: int, import_run_id: int, row: SyncPreviewRow) -> None:
        session.execute(
            text(
                """
                INSERT INTO excel_shipment_sync_rows (
                    sync_run_id,
                    import_run_id,
                    identity_key,
                    canonical_shipment_id,
                    shipment_column,
                    shipment_name,
                    action,
                    source_status,
                    source_target_date,
                    old_total_qty,
                    new_total_qty,
                    old_item_count,
                    new_item_count,
                    changed_items,
                    new_items,
                    removed_items,
                    conflicts,
                    manual_fields_preserved,
                    reason,
                    details_json
                )
                VALUES (
                    :sync_run_id,
                    :import_run_id,
                    :identity_key,
                    :canonical_shipment_id,
                    :shipment_column,
                    :shipment_name,
                    :action,
                    :source_status,
                    :source_target_date,
                    :old_total_qty,
                    :new_total_qty,
                    :old_item_count,
                    :new_item_count,
                    :changed_items,
                    :new_items,
                    :removed_items,
                    :conflicts,
                    :manual_fields_preserved,
                    :reason,
                    CAST(:details_json AS JSONB)
                )
                """
            ),
            {
                "sync_run_id": sync_run_id,
                "import_run_id": import_run_id,
                "identity_key": row.identity_key,
                "canonical_shipment_id": row.existing_shipment_id,
                "shipment_column": row.shipment_column,
                "shipment_name": row.shipment_name,
                "action": row.action,
                "source_status": row.source_status,
                "source_target_date": (
                    date.fromisoformat(row.source_target_date)
                    if row.source_target_date
                    else None
                ),
                "old_total_qty": row.old_total_qty,
                "new_total_qty": row.new_total_qty,
                "old_item_count": row.old_item_count,
                "new_item_count": row.new_item_count,
                "changed_items": row.changed_items,
                "new_items": row.new_items,
                "removed_items": row.removed_items,
                "conflicts": row.conflicts,
                "manual_fields_preserved": row.manual_fields_preserved,
                "reason": row.reason,
                "details_json": json.dumps(asdict(row), default=str),
            },
        )

    @staticmethod
    def _record_item_revision(
        session,
        *,
        sync_run_id: int,
        import_run_id: int,
        identity_key: str,
        shipment_id: int,
        shipment_item_id: int | None,
        sap_code: str,
        action: str,
        old_qty: int,
        new_qty: int,
        produced_qty: int,
        completed_qty: int,
        protected_actual: bool,
        conflict: bool,
        reason: str,
    ) -> None:
        session.execute(
            text(
                """
                INSERT INTO excel_shipment_item_revisions (
                    sync_run_id,
                    import_run_id,
                    identity_key,
                    shipment_id,
                    shipment_item_id,
                    sap_code,
                    action,
                    old_qty,
                    new_qty,
                    produced_qty,
                    completed_qty,
                    protected_actual,
                    conflict,
                    reason
                )
                VALUES (
                    :sync_run_id,
                    :import_run_id,
                    :identity_key,
                    :shipment_id,
                    :shipment_item_id,
                    :sap_code,
                    :action,
                    :old_qty,
                    :new_qty,
                    :produced_qty,
                    :completed_qty,
                    :protected_actual,
                    :conflict,
                    :reason
                )
                """
            ),
            {
                "sync_run_id": sync_run_id,
                "import_run_id": import_run_id,
                "identity_key": identity_key,
                "shipment_id": shipment_id,
                "shipment_item_id": shipment_item_id,
                "sap_code": sap_code,
                "action": action,
                "old_qty": old_qty,
                "new_qty": new_qty,
                "produced_qty": produced_qty,
                "completed_qty": completed_qty,
                "protected_actual": protected_actual,
                "conflict": conflict,
                "reason": reason,
            },
        )

    @staticmethod
    def _target_fields(group: ShipmentGroup, existing: dict[str, Any] | None) -> tuple[dict[str, Any], int]:
        manual_preserved = 0
        existing = existing or {}
        if bool(existing.get("target_date_is_manual")):
            manual_preserved += 1
            return ({}, manual_preserved)

        if group.source_target_date and group.source_date_class == "EXCEL_APPROVED":
            return (
                {
                    "target_date": group.source_target_date,
                    "manager_order_date": group.source_target_date,
                    "target_date_is_manual": False,
                    "target_date_source": "Excel Approved",
                },
                manual_preserved,
            )
        return (
            {
                "target_date": None,
                "manager_order_date": None,
                "target_date_is_manual": False,
                "target_date_source": "Auto Earliest Feasible Factory Out",
            },
            manual_preserved,
        )

    def _identity_row(self, session, identity_key: str):
        """Return a shipment identity without assuming the registry is complete."""
        return session.execute(
            text(
                """
                SELECT * FROM excel_shipment_identities
                WHERE source_family = :source_family
                  AND identity_key = :identity_key
                LIMIT 1
                """
            ),
            {
                "source_family": self.SOURCE_FAMILY,
                "identity_key": identity_key,
            },
        ).mappings().first()

    def _ensure_identity_row(
        self,
        session,
        *,
        ledger,
        import_run_id: int,
        group: ShipmentGroup,
        analysis,
        plan_date: date,
    ):
        """Create/repair the stable identity row atomically and return it.

        Older V7 databases can contain a shipment with no V8 identity registry
        row, while a failed import can also leave preview state stale.  This
        method makes the registry idempotent instead of relying on `.one()`.
        """
        identity = self._identity_row(session, group.identity_key)
        if identity is not None:
            return identity

        values = {
            "source_family": self.SOURCE_FAMILY,
            "identity_key": group.identity_key,
            "base_key": group.base_key,
            "display_name": group.shipment_name,
            "canonical_shipment_id": None,
            "first_seen_plan_date": plan_date,
            "last_seen_plan_date": plan_date,
            "latest_run_id": import_run_id,
            "latest_workbook_hash": analysis.workbook_hash,
            "latest_workbook_name": analysis.workbook_name,
            "latest_column": group.shipment_column,
            "latest_status": group.source_status,
            "latest_item_fingerprint": self._item_fingerprint(group),
            "latest_total_qty": group.total_qty,
            "latest_item_count": group.item_count,
            "is_active": True,
            "missing_since_plan_date": None,
            "updated_at": datetime.now(),
        }
        ledger._upsert_with_change(
            session,
            import_run_id,
            "excel_shipment_identities",
            {
                "source_family": self.SOURCE_FAMILY,
                "identity_key": group.identity_key,
            },
            values,
        )
        identity = self._identity_row(session, group.identity_key)
        if identity is None:
            raise RuntimeError(
                "Shipment identity registry could not be created/recovered for "
                f"{group.identity_key}. No live shipment was changed."
            )
        return identity

    @staticmethod
    def _authoritative_shipment_no(plan_date: date, group: ShipmentGroup) -> str:
        """Deterministic live number for the exact latest-workbook shipment."""
        seed = (
            f"{plan_date.isoformat()}|{group.shipment_column}|"
            f"{group.shipment_name}|{group.base_key}"
        )
        digest = sha1(seed.encode("utf-8")).hexdigest()[:12].upper()
        return f"XLS-FINAL-{plan_date.strftime('%Y%m%d')}-{digest}"

    def _archive_and_remove_previous_excel_live_shipments(
        self,
        session,
        *,
        import_run_id: int,
        analysis,
        plan_date: date,
        ledger,
        counters: Counter,
    ) -> int:
        """Move the previous Excel-controlled live queue out of operational tables.

        Historical Excel snapshots, actual production, stock history and AI learning
        remain untouched.  Only live shipments created/managed by OVEN Excel sync are
        removed from the operational queue, after a full JSON archive is written.
        """
        previous = session.execute(
            text(
                """
                SELECT *
                FROM mpps_shipments
                WHERE COALESCE(source_family, '') = :source_family
                   OR COALESCE(shipment_no, '') LIKE 'XLS-SYNC-%'
                   OR COALESCE(shipment_no, '') LIKE 'XLS-FINAL-%'
                ORDER BY id
                """
            ),
            {"source_family": self.SOURCE_FAMILY},
        ).mappings().all()

        for shipment in previous:
            shipment = dict(shipment)
            shipment_id = int(shipment["id"])
            items = [
                dict(row)
                for row in session.execute(
                    text(
                        """
                        SELECT * FROM mpps_shipment_items
                        WHERE shipment_id = :shipment_id
                        ORDER BY id
                        """
                    ),
                    {"shipment_id": shipment_id},
                ).mappings().all()
            ]
            session.execute(
                text(
                    """
                    INSERT INTO excel_authoritative_shipment_archive (
                        import_run_id,
                        archived_plan_date,
                        archived_workbook,
                        previous_shipment_id,
                        previous_shipment_no,
                        previous_source_family,
                        shipment_json,
                        items_json,
                        reason
                    ) VALUES (
                        :import_run_id,
                        :plan_date,
                        :workbook,
                        :shipment_id,
                        :shipment_no,
                        :source_family,
                        CAST(:shipment_json AS JSONB),
                        CAST(:items_json AS JSONB),
                        :reason
                    )
                    """
                ),
                {
                    "import_run_id": import_run_id,
                    "plan_date": plan_date,
                    "workbook": analysis.workbook_name,
                    "shipment_id": shipment_id,
                    "shipment_no": _text(shipment.get("shipment_no")),
                    "source_family": _text(shipment.get("source_family")),
                    "shipment_json": json.dumps(_json_safe(shipment), default=str),
                    "items_json": json.dumps(_json_safe(items), default=str),
                    "reason": (
                        "Archived because a newer/equal-date OVEN workbook is the "
                        "authoritative live shipment snapshot."
                    ),
                },
            )

            # Record DELETEs so the built-in import rollback can restore the
            # previous operational queue if the user rolls this import back.
            for item in items:
                ledger._record_change(
                    session,
                    import_run_id,
                    "mpps_shipment_items",
                    "DELETE",
                    {"id": int(item["id"])},
                    item,
                    {},
                )
            ledger._record_change(
                session,
                import_run_id,
                "mpps_shipments",
                "DELETE",
                {"id": shipment_id},
                shipment,
                {},
            )
            counters["authoritative_shipments_archived"] += 1
            counters["authoritative_items_archived"] += len(items)

        if previous:
            session.execute(
                text(
                    """
                    DELETE FROM mpps_shipments
                    WHERE COALESCE(source_family, '') = :source_family
                       OR COALESCE(shipment_no, '') LIKE 'XLS-SYNC-%'
                       OR COALESCE(shipment_no, '') LIKE 'XLS-FINAL-%'
                    """
                ),
                {"source_family": self.SOURCE_FAMILY},
            )

        # The registry is historical metadata; clear only live pointers.  Old
        # identity rows remain useful for audit but cannot point at deleted live rows.
        session.execute(
            text(
                """
                UPDATE excel_shipment_identities
                SET canonical_shipment_id = NULL,
                    is_active = FALSE,
                    missing_since_plan_date = :plan_date,
                    updated_at = CURRENT_TIMESTAMP
                WHERE source_family = :source_family
                """
            ),
            {"plan_date": plan_date, "source_family": self.SOURCE_FAMILY},
        )
        return len(previous)

    def _sync_authoritative_latest(
        self,
        session,
        *,
        import_run_id: int,
        analysis,
        options: dict[str, Any],
        counters: Counter,
        ledger,
        preview: SyncPreview,
    ) -> dict[str, Any]:
        """Replace the Excel-controlled live shipment queue from the latest file.

        Business rule: the newest OVEN workbook by plan date is the live shipment
        truth.  Older workbooks are historical only.  Previous Excel live shipments
        are archived, removed from operational planning, and the latest workbook is
        rebuilt exactly from its non-zero shipment rows.
        """
        plan_date = date.fromisoformat(preview.plan_date)
        sync_run_id = session.execute(
            text(
                """
                INSERT INTO excel_shipment_sync_runs (
                    import_run_id, workbook_hash, workbook_name, plan_date,
                    sync_mode, status, reason
                ) VALUES (
                    :import_run_id, :workbook_hash, :workbook_name, :plan_date,
                    'LIVE', 'RUNNING', :reason
                )
                RETURNING id
                """
            ),
            {
                "import_run_id": import_run_id,
                "workbook_hash": analysis.workbook_hash,
                "workbook_name": analysis.workbook_name,
                "plan_date": plan_date,
                "reason": preview.reason,
            },
        ).scalar_one()

        archived = self._archive_and_remove_previous_excel_live_shipments(
            session,
            import_run_id=import_run_id,
            analysis=analysis,
            plan_date=plan_date,
            ledger=ledger,
            counters=counters,
        )

        groups = [
            group
            for group in self._group_analysis(analysis)
            if group.item_count > 0 and group.total_qty > 0
        ]
        created_shipments = 0
        created_items = 0

        for group in groups:
            # All non-zero shipment columns in the newest workbook are treated as
            # real demand, including columns previously labelled deferred.
            if not group.shipment_name:
                group.shipment_name = f"SHIPMENT {group.shipment_column}"
                group.base_key = _source_base_key(group.shipment_name)
            group.identity_key = _identity_key(
                group.base_key,
                f"AUTHORITATIVE-{group.shipment_column}",
            )
            stable_no = self._authoritative_shipment_no(plan_date, group)
            target_date = group.source_target_date

            shipment_values = {
                "shipment_no": stable_no,
                "shipment_id": stable_no,
                "shipment_name": group.shipment_name,
                "customer_name": group.shipment_name,
                "shipment_date": plan_date,
                "target_date": target_date,
                "target_date_is_manual": False,
                "target_date_source": "LATEST OVEN EXCEL",
                "plan_date": plan_date,
                "factory_can_receive_date": None,
                "factory_out_date": None,
                "dispatch_buffer_days": 0,
                "delivery_status": "Pending Planning",
                "delay_days": 0,
                "early_days": 0,
                "total_qty": group.total_qty,
                "completed_qty": 0,
                "progress_pct": 0,
                "planning_status": "Pending Replan",
                "planning_note": (
                    "Authoritative latest OVEN workbook shipment; Excel quantity "
                    "is the live planning truth until a newer workbook is committed."
                ),
                "last_replanned_at": None,
                "status": "Planned",
                "note": (
                    f"FINAL shipment snapshot from {analysis.workbook_name}; "
                    f"source column {group.shipment_column}."
                ),
                "source_family": self.SOURCE_FAMILY,
                "source_identity_key": group.identity_key,
                "source_latest_run_id": import_run_id,
                "source_latest_plan_date": plan_date,
                "source_latest_workbook": analysis.workbook_name,
                "source_latest_column": group.shipment_column,
                "source_latest_status": group.source_status,
                "source_missing_from_latest": False,
                "source_revision_no": 1,
                "source_sync_status": "AUTHORITATIVE_LATEST",
                "source_sync_note": "Live shipment rebuilt from the latest workbook.",
                "updated_at": datetime.now(),
            }
            inserted_shipment = ledger._insert_with_change(
                session,
                import_run_id,
                "mpps_shipments",
                shipment_values,
                key_fields={"shipment_no": stable_no},
            )
            if not inserted_shipment or inserted_shipment.get("id") is None:
                raise RuntimeError(
                    f"Authoritative shipment insert returned no id for {stable_no}."
                )
            shipment_id = int(inserted_shipment["id"])
            created_shipments += 1

            for code, source_item in group.items.items():
                qty = _safe_int(source_item.get("quantity"))
                if qty <= 0:
                    continue
                item_values = {
                    "shipment_id": shipment_id,
                    "sap_code": code,
                    "item_description": _text(source_item.get("description")),
                    "quantity": qty,
                    "stock_allocated_qty": 0,
                    "produced_qty": 0,
                    "completed_qty": 0,
                    "production_required_qty": qty,
                    "remaining_qty": qty,
                    "progress_pct": 0,
                    "item_status": "Pending",
                    "planning_note": "Latest Excel demand; waiting for global replan.",
                    "schedule_reason": "Waiting for cumulative stock/resource planning.",
                    "factory_out_reason": "Waiting for cumulative stock/resource planning.",
                    "note": f"Authoritative Excel import run #{import_run_id}",
                    "source_item_key": f"{group.identity_key}|{code}",
                    "source_latest_run_id": import_run_id,
                    "source_latest_plan_date": plan_date,
                    "source_latest_qty": qty,
                    "source_removed_from_latest": False,
                    "source_revision_no": 1,
                    "source_sync_status": "AUTHORITATIVE_LATEST",
                    "source_sync_note": "Created from latest workbook demand.",
                    "updated_at": datetime.now(),
                }
                inserted_item = ledger._insert_with_change(
                    session,
                    import_run_id,
                    "mpps_shipment_items",
                    item_values,
                    key_fields={"shipment_id": shipment_id, "sap_code": code},
                )
                if not inserted_item or inserted_item.get("id") is None:
                    raise RuntimeError(
                        "Authoritative shipment item INSERT returned no row: "
                        f"shipment_id={shipment_id}, sap_code={code}."
                    )
                created_items += 1
                self._record_item_revision(
                    session,
                    sync_run_id=sync_run_id,
                    import_run_id=import_run_id,
                    identity_key=group.identity_key,
                    shipment_id=shipment_id,
                    shipment_item_id=int(inserted_item["id"]),
                    sap_code=_text(inserted_item.get("sap_code") or code),
                    action="AUTHORITATIVE_NEW",
                    old_qty=0,
                    new_qty=qty,
                    produced_qty=0,
                    completed_qty=0,
                    protected_actual=False,
                    conflict=False,
                    reason="Created from the latest authoritative workbook.",
                )

            # Rebuild one current identity pointer for traceability.  The natural
            # key UPSERT is race-safe and old identities remain inactive history.
            identity = self._ensure_identity_row(
                session,
                ledger=ledger,
                import_run_id=import_run_id,
                group=group,
                analysis=analysis,
                plan_date=plan_date,
            )
            ledger._update_existing_by_id(
                session,
                import_run_id,
                "excel_shipment_identities",
                int(identity["id"]),
                {
                    "display_name": group.shipment_name,
                    "canonical_shipment_id": shipment_id,
                    "first_seen_plan_date": identity.get("first_seen_plan_date") or plan_date,
                    "last_seen_plan_date": plan_date,
                    "latest_run_id": import_run_id,
                    "latest_workbook_hash": analysis.workbook_hash,
                    "latest_workbook_name": analysis.workbook_name,
                    "latest_column": group.shipment_column,
                    "latest_status": group.source_status,
                    "latest_item_fingerprint": self._item_fingerprint(group),
                    "latest_total_qty": group.total_qty,
                    "latest_item_count": group.item_count,
                    "is_active": True,
                    "missing_since_plan_date": None,
                    "updated_at": datetime.now(),
                },
            )
            session.execute(
                text(
                    """
                    UPDATE excel_import_shipment_snapshots
                    SET live_shipment_id = :shipment_id,
                        source_identity_key = :identity_key
                    WHERE run_id = :run_id
                      AND shipment_column = :shipment_column
                    """
                ),
                {
                    "shipment_id": shipment_id,
                    "identity_key": group.identity_key,
                    "run_id": import_run_id,
                    "shipment_column": group.shipment_column,
                },
            )

            sync_row = SyncPreviewRow(
                action="AUTHORITATIVE_LATEST",
                identity_key=group.identity_key,
                shipment_column=group.shipment_column,
                shipment_name=group.shipment_name,
                existing_shipment_id=None,
                existing_shipment_no="",
                source_status=group.source_status,
                source_target_date=(target_date.isoformat() if target_date else ""),
                source_date_class=group.source_date_class,
                old_item_count=0,
                new_item_count=group.item_count,
                old_total_qty=0,
                new_total_qty=group.total_qty,
                changed_items=0,
                new_items=group.item_count,
                removed_items=0,
                conflicts=0,
                manual_fields_preserved=0,
                reason="Latest workbook is the FINAL live shipment truth.",
            )
            self._insert_sync_row(session, sync_run_id, import_run_id, sync_row)

        counters["shipments_created"] += created_shipments
        counters["shipment_items_created"] += created_items
        counters["authoritative_live_shipments"] += created_shipments
        counters["authoritative_live_items"] += created_items

        details = {
            "sync_mode": "LIVE",
            "authority_mode": "LATEST_WORKBOOK_FINAL",
            "sync_reason": preview.reason,
            "archived_previous_shipments": archived,
            "new_shipments": created_shipments,
            "new_items": created_items,
            "updated_shipments": 0,
            "unchanged_shipments": 0,
            "deferred_shipments": 0,
            "missing_shipments": archived,
            "review_shipments": 0,
            "changed_items": 0,
            "removed_items": int(counters.get("authoritative_items_archived", 0)),
            "conflict_items": 0,
            "manual_fields_preserved": 0,
            "live_change_count": archived + created_shipments + created_items,
        }
        session.execute(
            text(
                """
                UPDATE excel_shipment_sync_runs
                SET status = 'COMMITTED',
                    new_shipments = :new_shipments,
                    updated_shipments = 0,
                    unchanged_shipments = 0,
                    deferred_shipments = 0,
                    missing_shipments = :missing_shipments,
                    review_shipments = 0,
                    new_items = :new_items,
                    changed_items = 0,
                    removed_items = :removed_items,
                    conflict_items = 0,
                    manual_fields_preserved = 0,
                    details_json = CAST(:details_json AS JSONB),
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = :sync_run_id
                """
            ),
            {
                "sync_run_id": sync_run_id,
                "new_shipments": created_shipments,
                "missing_shipments": archived,
                "new_items": created_items,
                "removed_items": int(counters.get("authoritative_items_archived", 0)),
                "details_json": json.dumps(details, default=str),
            },
        )
        return {"sync_run_id": sync_run_id, **details}

    def sync(
        self,
        session,
        *,
        import_run_id: int,
        analysis,
        options: dict[str, Any],
        counters: Counter,
        ledger,
    ) -> dict[str, Any]:
        self.ensure_schema(session)
        preview = self.preview_with_session(session, analysis, options)
        plan_date = date.fromisoformat(preview.plan_date)

        if (
            preview.mode == "LIVE"
            and options.get("authoritative_latest_shipments", False)
        ):
            return self._sync_authoritative_latest(
                session,
                import_run_id=import_run_id,
                analysis=analysis,
                options=options,
                counters=counters,
                ledger=ledger,
                preview=preview,
            )

        sync_run_id = session.execute(
            text(
                """
                INSERT INTO excel_shipment_sync_runs (
                    import_run_id,
                    workbook_hash,
                    workbook_name,
                    plan_date,
                    sync_mode,
                    status,
                    reason
                )
                VALUES (
                    :import_run_id,
                    :workbook_hash,
                    :workbook_name,
                    :plan_date,
                    :sync_mode,
                    'RUNNING',
                    :reason
                )
                RETURNING id
                """
            ),
            {
                "import_run_id": import_run_id,
                "workbook_hash": analysis.workbook_hash,
                "workbook_name": analysis.workbook_name,
                "plan_date": plan_date,
                "sync_mode": preview.mode,
                "reason": preview.reason,
            },
        ).scalar_one()

        groups = self._group_analysis(analysis)
        self._assign_identities(session, groups)
        group_by_identity = {group.identity_key: group for group in groups}

        for row in preview.rows:
            self._insert_sync_row(session, sync_run_id, import_run_id, row)
            counters[f"shipment_sync_{row.action.lower()}"] += 1

            if row.action in {"SNAPSHOT_ONLY", "DEFERRED", "IGNORED_GENERIC"}:
                group = group_by_identity.get(row.identity_key)
                if group and group.identity_id:
                    ledger._update_existing_by_id(
                        session,
                        import_run_id,
                        "excel_shipment_identities",
                        int(group.identity_id),
                        {
                            "display_name": group.shipment_name,
                            "last_seen_plan_date": plan_date,
                            "latest_run_id": import_run_id,
                            "latest_workbook_hash": analysis.workbook_hash,
                            "latest_workbook_name": analysis.workbook_name,
                            "latest_column": group.shipment_column,
                            "latest_status": group.source_status,
                            "latest_item_fingerprint": self._item_fingerprint(group),
                            "latest_total_qty": group.total_qty,
                            "latest_item_count": group.item_count,
                            "updated_at": datetime.now(),
                        },
                    )
                continue

            if row.action in {"MISSING_FROM_LATEST", "REVIEW_MISSING"}:
                shipment, _ = self._load_shipment(session, row.existing_shipment_id)
                if not shipment:
                    continue
                identity = session.execute(
                    text(
                        """
                        SELECT * FROM excel_shipment_identities
                        WHERE source_family = :source_family
                          AND identity_key = :identity_key
                        LIMIT 1
                        """
                    ),
                    {
                        "source_family": self.SOURCE_FAMILY,
                        "identity_key": row.identity_key,
                    },
                ).mappings().first()
                if identity:
                    ledger._update_existing_by_id(
                        session,
                        import_run_id,
                        "excel_shipment_identities",
                        int(identity["id"]),
                        {
                            "is_active": False if row.action == "MISSING_FROM_LATEST" else True,
                            "missing_since_plan_date": plan_date,
                            "updated_at": datetime.now(),
                        },
                    )
                update_values = {
                    "source_missing_from_latest": True,
                    "lifecycle_status": "CLOSURE_REVIEW",
                    "source_latest_run_id": import_run_id,
                    "source_latest_plan_date": plan_date,
                    "source_sync_status": row.action,
                    "source_sync_note": row.reason,
                    "updated_at": datetime.now(),
                }
                if row.action == "MISSING_FROM_LATEST":
                    update_values.update(
                        {
                            "status": "Review Required",
                            "planning_status": "Missing From Latest Workbook",
                            "delivery_status": "Review Required",
                            "planning_note": row.reason,
                        }
                    )
                ledger._update_existing_by_id(
                    session,
                    import_run_id,
                    "mpps_shipments",
                    int(shipment["id"]),
                    update_values,
                )
                continue

            group = group_by_identity.get(row.identity_key)
            if not group:
                continue

            identity = self._ensure_identity_row(
                session,
                ledger=ledger,
                import_run_id=import_run_id,
                group=group,
                analysis=analysis,
                plan_date=plan_date,
            )

            shipment_id = identity.get("canonical_shipment_id")

            # Migration bridge: an older continuous-sync build may already
            # have created the live shipment while the V8 identity registry
            # is empty/unlinked.  Adopt that row instead of attempting a
            # duplicate INSERT that violates shipment_no/source-identity
            # uniqueness.
            if not shipment_id:
                legacy_shipment = self._find_legacy_canonical_shipment(
                    session,
                    group.identity_key,
                )
                if legacy_shipment:
                    shipment_id = int(legacy_shipment["id"])
                    ledger._update_existing_by_id(
                        session,
                        import_run_id,
                        "excel_shipment_identities",
                        int(identity["id"]),
                        {
                            "canonical_shipment_id": shipment_id,
                            "updated_at": datetime.now(),
                        },
                    )
                    identity = {
                        **dict(identity),
                        "canonical_shipment_id": shipment_id,
                    }
                    counters["legacy_shipments_adopted"] += 1

            shipment, existing_items = self._load_shipment(
                session,
                int(shipment_id) if shipment_id else None,
            )
            target_values, target_preserved = self._target_fields(group, shipment)
            counters["shipment_manual_fields_preserved"] += target_preserved

            if not shipment:
                stable_no = _shipment_no(group.identity_key)
                values = {
                    "shipment_no": stable_no,
                    "shipment_id": stable_no,
                    "shipment_name": group.shipment_name,
                    "customer_name": group.shipment_name,
                    "shipment_date": plan_date,
                    "status": "Planned",
                    "note": (
                        f"Continuously synchronized from {analysis.workbook_name}; "
                        "future revisions update this shipment instead of creating duplicates."
                    ),
                    "plan_date": plan_date,
                    "factory_can_receive_date": None,
                    "factory_out_date": None,
                    "dispatch_buffer_days": 0,
                    "delivery_status": "Pending Planning",
                    "delay_days": 0,
                    "early_days": 0,
                    "planning_status": "Pending Replan",
                    "planning_note": "Latest Excel revision committed; cumulative planning is pending.",
                    "last_replanned_at": None,
                    "source_family": self.SOURCE_FAMILY,
                    "source_identity_key": group.identity_key,
                    "source_latest_run_id": import_run_id,
                    "source_latest_plan_date": plan_date,
                    "source_latest_workbook": analysis.workbook_name,
                    "source_latest_column": group.shipment_column,
                    "source_latest_status": group.source_status,
                    "source_missing_from_latest": False,
                    "source_revision_no": 1,
                    "source_sync_status": "NEW",
                    "source_sync_note": "Created from the first live workbook revision.",
                    "updated_at": datetime.now(),
                    **target_values,
                }
                ledger._insert_with_change(
                    session,
                    import_run_id,
                    "mpps_shipments",
                    values,
                    key_fields={"shipment_no": stable_no},
                )
                shipment = session.execute(
                    text("SELECT * FROM mpps_shipments WHERE shipment_no = :shipment_no"),
                    {"shipment_no": stable_no},
                ).mappings().first()
                if shipment is None:
                    shipment = self._find_legacy_canonical_shipment(
                        session, group.identity_key
                    )
                if shipment is None:
                    raise RuntimeError(
                        "Shipment row could not be recovered after creation for "
                        f"identity {group.identity_key}. No partial import was committed."
                    )
                shipment_id = int(shipment["id"])
                ledger._update_existing_by_id(
                    session,
                    import_run_id,
                    "excel_shipment_identities",
                    int(identity["id"]),
                    {
                        "canonical_shipment_id": shipment_id,
                        "updated_at": datetime.now(),
                    },
                )
                existing_items = {}
                counters["shipments_created"] += 1
            else:
                shipment_id = int(shipment["id"])
                protected_status = _text(shipment.get("status")).lower()
                status_values: dict[str, Any] = {}
                if protected_status not in CLOSED_OR_PROTECTED_STATUSES:
                    status_values = {
                        "status": "Planned",
                        "planning_status": "Pending Replan",
                        "delivery_status": "Pending Planning",
                        "factory_can_receive_date": None,
                        "factory_out_date": None,
                    }
                else:
                    counters["shipment_manual_fields_preserved"] += 1

                ledger._update_existing_by_id(
                    session,
                    import_run_id,
                    "mpps_shipments",
                    shipment_id,
                    {
                        "shipment_name": group.shipment_name,
                        "customer_name": group.shipment_name,
                        "shipment_date": plan_date,
                        "plan_date": plan_date,
                        "source_family": self.SOURCE_FAMILY,
                        "source_identity_key": group.identity_key,
                        "source_latest_run_id": import_run_id,
                        "source_latest_plan_date": plan_date,
                        "source_latest_workbook": analysis.workbook_name,
                        "source_latest_column": group.shipment_column,
                        "source_latest_status": group.source_status,
                        "source_missing_from_latest": False,
                        "source_revision_no": _safe_int(shipment.get("source_revision_no")) + 1,
                        "source_sync_status": row.action,
                        "source_sync_note": row.reason,
                        "planning_note": (
                            shipment.get("planning_note")
                            if protected_status in CLOSED_OR_PROTECTED_STATUSES
                            else "Latest Excel revision committed; cumulative planning is pending."
                        ),
                        "updated_at": datetime.now(),
                        **status_values,
                        **target_values,
                    },
                )
                if row.action == "UNCHANGED":
                    counters["shipments_unchanged"] += 1
                else:
                    counters["shipments_updated"] += 1

            current_items = {
                _code(item["sap_code"]): item
                for item in session.execute(
                    text(
                        """
                        SELECT * FROM mpps_shipment_items
                        WHERE shipment_id = :shipment_id
                        ORDER BY id
                        """
                    ),
                    {"shipment_id": shipment_id},
                ).mappings().all()
            }

            for code, source_item in group.items.items():
                new_qty = _safe_int(source_item.get("quantity"))
                existing_item = current_items.get(code)
                if not existing_item:
                    ledger._insert_with_change(
                        session,
                        import_run_id,
                        "mpps_shipment_items",
                        {
                            "shipment_id": shipment_id,
                            "sap_code": code,
                            "item_description": _text(source_item.get("description")),
                            "quantity": new_qty,
                            "item_status": "Pending",
                            "note": f"Continuous Excel sync run #{import_run_id}",
                            "stock_allocated_qty": 0,
                            "production_required_qty": new_qty,
                            "remaining_qty": new_qty,
                            "planning_note": "New or revised Excel demand; global planning is pending.",
                            "schedule_reason": "Waiting for cumulative stock/resource planning.",
                            "factory_out_reason": "Waiting for cumulative stock/resource planning.",
                            "source_item_key": f"{group.identity_key}|{code}",
                            "source_latest_run_id": import_run_id,
                            "source_latest_plan_date": plan_date,
                            "source_latest_qty": new_qty,
                            "source_removed_from_latest": False,
                            "source_revision_no": 1,
                            "source_sync_status": "NEW",
                            "source_sync_note": "Created from latest workbook revision.",
                            "updated_at": datetime.now(),
                        },
                        key_fields={"shipment_id": shipment_id, "sap_code": code},
                    )
                    inserted_item = session.execute(
                        text(
                            """
                            SELECT * FROM mpps_shipment_items
                            WHERE shipment_id = :shipment_id AND sap_code = :sap_code
                            ORDER BY id LIMIT 1
                            """
                        ),
                        {"shipment_id": shipment_id, "sap_code": code},
                    ).mappings().first()
                    if inserted_item is None:
                        raise RuntimeError(
                            "Shipment item could not be recovered after insert: "
                            f"shipment_id={shipment_id}, sap_code={code}."
                        )
                    self._record_item_revision(
                        session,
                        sync_run_id=sync_run_id,
                        import_run_id=import_run_id,
                        identity_key=group.identity_key,
                        shipment_id=shipment_id,
                        shipment_item_id=int(inserted_item["id"]),
                        sap_code=code,
                        action="NEW",
                        old_qty=0,
                        new_qty=new_qty,
                        produced_qty=0,
                        completed_qty=0,
                        protected_actual=False,
                        conflict=False,
                        reason="New SAP item appeared in the workbook shipment.",
                    )
                    counters["shipment_items_created"] += 1
                    continue

                old_qty = _safe_int(existing_item.get("quantity"))
                produced = _safe_int(existing_item.get("produced_qty"))
                completed = _safe_int(existing_item.get("completed_qty"))
                protected_floor = max(produced, completed)
                manual_lock = bool(existing_item.get("source_manual_lock"))
                conflict = new_qty < protected_floor or manual_lock
                if conflict:
                    ledger._update_existing_by_id(
                        session,
                        import_run_id,
                        "mpps_shipment_items",
                        int(existing_item["id"]),
                        {
                            "source_latest_run_id": import_run_id,
                            "source_latest_plan_date": plan_date,
                            "source_latest_qty": new_qty,
                            "source_sync_status": "REVIEW",
                            "source_sync_note": (
                                "Workbook quantity was not applied because actual production/completion "
                                "or a manual item lock must be preserved."
                            ),
                            "updated_at": datetime.now(),
                        },
                    )
                    self._record_item_revision(
                        session,
                        sync_run_id=sync_run_id,
                        import_run_id=import_run_id,
                        identity_key=group.identity_key,
                        shipment_id=shipment_id,
                        shipment_item_id=int(existing_item["id"]),
                        sap_code=code,
                        action="REVIEW",
                        old_qty=old_qty,
                        new_qty=new_qty,
                        produced_qty=produced,
                        completed_qty=completed,
                        protected_actual=True,
                        conflict=True,
                        reason="Quantity is below actual/completed production or the item is manually locked.",
                    )
                    counters["shipment_item_conflicts"] += 1
                    continue

                remaining = max(0, new_qty - completed)
                action = "UPDATED" if old_qty != new_qty else "UNCHANGED"
                ledger._update_existing_by_id(
                    session,
                    import_run_id,
                    "mpps_shipment_items",
                    int(existing_item["id"]),
                    {
                        "item_description": _text(source_item.get("description")),
                        "quantity": new_qty,
                        "item_status": "Pending" if remaining else "Completed",
                        "stock_allocated_qty": 0,
                        "production_required_qty": remaining,
                        "remaining_qty": remaining,
                        "planning_note": "Latest Excel quantity committed; global planning is pending.",
                        "schedule_reason": "Waiting for cumulative stock/resource planning.",
                        "factory_out_reason": "Waiting for cumulative stock/resource planning.",
                        "source_item_key": f"{group.identity_key}|{code}",
                        "source_latest_run_id": import_run_id,
                        "source_latest_plan_date": plan_date,
                        "source_latest_qty": new_qty,
                        "source_removed_from_latest": False,
                        "source_revision_no": _safe_int(existing_item.get("source_revision_no")) + 1,
                        "source_sync_status": action,
                        "source_sync_note": "Synchronized from the latest workbook revision.",
                        "updated_at": datetime.now(),
                    },
                )
                self._record_item_revision(
                    session,
                    sync_run_id=sync_run_id,
                    import_run_id=import_run_id,
                    identity_key=group.identity_key,
                    shipment_id=shipment_id,
                    shipment_item_id=int(existing_item["id"]),
                    sap_code=code,
                    action=action,
                    old_qty=old_qty,
                    new_qty=new_qty,
                    produced_qty=produced,
                    completed_qty=completed,
                    protected_actual=False,
                    conflict=False,
                    reason="Latest workbook quantity synchronized safely.",
                )
                if old_qty != new_qty:
                    counters["shipment_items_updated"] += 1

            for code, existing_item in current_items.items():
                if code in group.items or bool(existing_item.get("source_removed_from_latest")):
                    continue
                old_qty = _safe_int(existing_item.get("quantity"))
                produced = _safe_int(existing_item.get("produced_qty"))
                completed = _safe_int(existing_item.get("completed_qty"))
                manual_lock = bool(existing_item.get("source_manual_lock"))
                protected = produced > 0 or completed > 0 or manual_lock
                if protected:
                    ledger._update_existing_by_id(
                        session,
                        import_run_id,
                        "mpps_shipment_items",
                        int(existing_item["id"]),
                        {
                            "source_latest_run_id": import_run_id,
                            "source_latest_plan_date": plan_date,
                            "source_latest_qty": 0,
                            "source_sync_status": "REMOVAL_REVIEW",
                            "source_sync_note": (
                                "Item is absent from the latest workbook but is retained because actual production/completion or a manual lock exists."
                            ),
                            "updated_at": datetime.now(),
                        },
                    )
                    action = "REMOVAL_REVIEW"
                    conflict = True
                    reason = "Removal protected by actual/completed production or manual lock."
                    counters["shipment_item_conflicts"] += 1
                else:
                    ledger._update_existing_by_id(
                        session,
                        import_run_id,
                        "mpps_shipment_items",
                        int(existing_item["id"]),
                        {
                            "quantity": 0,
                            "item_status": "Removed From Latest Workbook",
                            "stock_allocated_qty": 0,
                            "production_required_qty": 0,
                            "remaining_qty": 0,
                            "planning_note": "Removed from the latest source revision; row retained for audit.",
                            "schedule_reason": "Removed from latest workbook.",
                            "factory_out_reason": "Removed from latest workbook.",
                            "source_latest_run_id": import_run_id,
                            "source_latest_plan_date": plan_date,
                            "source_latest_qty": 0,
                            "source_removed_from_latest": True,
                            "source_revision_no": _safe_int(existing_item.get("source_revision_no")) + 1,
                            "source_sync_status": "REMOVED",
                            "source_sync_note": "Safely excluded without deleting the audit row.",
                            "updated_at": datetime.now(),
                        },
                    )
                    action = "REMOVED"
                    conflict = False
                    reason = "Item was absent from the latest workbook and had no protected actual data."
                    counters["shipment_items_removed"] += 1

                self._record_item_revision(
                    session,
                    sync_run_id=sync_run_id,
                    import_run_id=import_run_id,
                    identity_key=group.identity_key,
                    shipment_id=shipment_id,
                    shipment_item_id=int(existing_item["id"]),
                    sap_code=code,
                    action=action,
                    old_qty=old_qty,
                    new_qty=0,
                    produced_qty=produced,
                    completed_qty=completed,
                    protected_actual=protected,
                    conflict=conflict,
                    reason=reason,
                )

            identity = self._ensure_identity_row(
                session,
                ledger=ledger,
                import_run_id=import_run_id,
                group=group,
                analysis=analysis,
                plan_date=plan_date,
            )
            ledger._update_existing_by_id(
                session,
                import_run_id,
                "excel_shipment_identities",
                int(identity["id"]),
                {
                    "display_name": group.shipment_name,
                    "canonical_shipment_id": shipment_id,
                    "first_seen_plan_date": identity.get("first_seen_plan_date") or plan_date,
                    "last_seen_plan_date": plan_date,
                    "latest_run_id": import_run_id,
                    "latest_workbook_hash": analysis.workbook_hash,
                    "latest_workbook_name": analysis.workbook_name,
                    "latest_column": group.shipment_column,
                    "latest_status": group.source_status,
                    "latest_item_fingerprint": self._item_fingerprint(group),
                    "latest_total_qty": group.total_qty,
                    "latest_item_count": group.item_count,
                    "is_active": True,
                    "missing_since_plan_date": None,
                    "updated_at": datetime.now(),
                },
            )

            session.execute(
                text(
                    """
                    UPDATE excel_import_shipment_snapshots
                    SET
                        live_shipment_id = :shipment_id,
                        source_identity_key = :identity_key
                    WHERE run_id = :run_id
                      AND shipment_column = :shipment_column
                    """
                ),
                {
                    "shipment_id": shipment_id,
                    "identity_key": group.identity_key,
                    "run_id": import_run_id,
                    "shipment_column": group.shipment_column,
                },
            )

        summary = dict(preview.summary)
        summary.update(
            {
                "sync_run_id": sync_run_id,
                "sync_mode": preview.mode,
                "sync_reason": preview.reason,
                "live_change_count": (
                    summary.get("new_shipments", 0)
                    + summary.get("updated_shipments", 0)
                    + summary.get("missing_shipments", 0)
                ),
            }
        )
        session.execute(
            text(
                """
                UPDATE excel_shipment_sync_runs
                SET
                    status = 'COMMITTED',
                    new_shipments = :new_shipments,
                    updated_shipments = :updated_shipments,
                    unchanged_shipments = :unchanged_shipments,
                    deferred_shipments = :deferred_shipments,
                    missing_shipments = :missing_shipments,
                    review_shipments = :review_shipments,
                    new_items = :new_items,
                    changed_items = :changed_items,
                    removed_items = :removed_items,
                    conflict_items = :conflict_items,
                    manual_fields_preserved = :manual_fields_preserved,
                    details_json = CAST(:details_json AS JSONB),
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = :sync_run_id
                """
            ),
            {
                "sync_run_id": sync_run_id,
                "new_shipments": summary.get("new_shipments", 0),
                "updated_shipments": summary.get("updated_shipments", 0),
                "unchanged_shipments": summary.get("unchanged_shipments", 0),
                "deferred_shipments": summary.get("deferred_shipments", 0),
                "missing_shipments": summary.get("missing_shipments", 0),
                "review_shipments": summary.get("review_shipments", 0),
                "new_items": summary.get("new_items", 0),
                "changed_items": summary.get("changed_items", 0),
                "removed_items": summary.get("removed_items", 0),
                "conflict_items": summary.get("conflict_items", 0),
                "manual_fields_preserved": summary.get("manual_fields_preserved", 0),
                "details_json": json.dumps(summary, default=str),
            },
        )
        for key, value in summary.items():
            if isinstance(value, int):
                counters[f"sync_{key}"] += value
        return summary
