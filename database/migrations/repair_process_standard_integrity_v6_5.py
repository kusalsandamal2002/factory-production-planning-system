from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.master_data_normalization import (
    identifier_key,
    normalize_casing_type,
    normalize_line_name,
    normalize_mold_key,
)
from app.services.process_standard_resolution import (
    build_process_standard_index,
    process_standard_complete,
)


VERSION = "6.5.0"


def _safe_table_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"Unsafe table name: {value}")
    return value


def _valid_mapping(row: dict[str, Any]) -> bool:
    return (
        bool(normalize_mold_key(row.get("key_code"), unknown_value=""))
        and bool(normalize_line_name(row.get("line")))
        and bool(
            normalize_casing_type(
                row.get("casing_type"),
                unknown_value="",
            )
        )
    )


def _approval_evidence(
    row: dict[str, Any],
    approved_keys: set[str],
) -> tuple[bool, str]:
    sap_key = identifier_key(row.get("sap_code"))
    if sap_key in approved_keys:
        return True, "Approved status found in the latest SMDS approval backup"

    note = str(
        row.get("planning_manager_approval_note") or ""
    ).strip().lower()
    approved_at = row.get("planning_manager_approved_at")
    manager_updated = row.get("manager_approval_updated_at")
    reset_pattern = (
        approved_at is not None
        and manager_updated is None
        and note == "approved after smds import"
    )
    if reset_pattern:
        return True, "Legacy approved evidence matched the known reset pattern"
    return False, ""


def _ensure_schema(conn) -> None:
    for statement in [
        """
        ALTER TABLE smds
        ADD COLUMN IF NOT EXISTS process_standard_source TEXT
            NOT NULL DEFAULT ''
        """,
        """
        ALTER TABLE smds
        ADD COLUMN IF NOT EXISTS process_standard_confidence NUMERIC(7, 4)
            NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE smds
        ADD COLUMN IF NOT EXISTS process_standard_peer_count INTEGER
            NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE smds
        ADD COLUMN IF NOT EXISTS process_standard_inferred_at TIMESTAMP
        """,
        """
        CREATE TABLE IF NOT EXISTS process_standard_repair_runs (
            id BIGSERIAL PRIMARY KEY,
            version VARCHAR(32) NOT NULL,
            backup_table TEXT NOT NULL DEFAULT '',
            approval_backup_table TEXT NOT NULL DEFAULT '',
            total_rows INTEGER NOT NULL DEFAULT 0,
            missing_before INTEGER NOT NULL DEFAULT 0,
            inferred_rows INTEGER NOT NULL DEFAULT 0,
            approvals_restored INTEGER NOT NULL DEFAULT 0,
            unresolved_rows INTEGER NOT NULL DEFAULT 0,
            missing_after INTEGER NOT NULL DEFAULT 0,
            report_directory TEXT NOT NULL DEFAULT '',
            summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS process_standard_repair_rows (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL
                REFERENCES process_standard_repair_runs(id)
                ON DELETE CASCADE,
            smds_id BIGINT NOT NULL,
            sap_code TEXT NOT NULL DEFAULT '',
            material_description TEXT NOT NULL DEFAULT '',
            repair_status VARCHAR(40) NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            confidence NUMERIC(7, 4) NOT NULL DEFAULT 0,
            peer_count INTEGER NOT NULL DEFAULT 0,
            group_count INTEGER NOT NULL DEFAULT 0,
            approval_restored BOOLEAN NOT NULL DEFAULT FALSE,
            approval_evidence TEXT NOT NULL DEFAULT '',
            before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]:
        conn.execute(text(statement))


def _latest_approval_backup(conn) -> str:
    table_name = conn.execute(
        text(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename LIKE 'smds_approval_backup_%'
            ORDER BY tablename DESC
            LIMIT 1
            """
        )
    ).scalar()
    return str(table_name or "")


def _approved_keys(conn, backup_table: str) -> set[str]:
    if not backup_table:
        return set()
    table_name = _safe_table_name(backup_table)
    sql = (
        'SELECT sap_code FROM "' + table_name + '" '
        "WHERE LOWER(TRIM(COALESCE("
        "planning_manager_approval_status, ''))) = 'approved'"
    )
    rows = conn.execute(text(sql)).all()
    return {
        identifier_key(row[0])
        for row in rows
        if identifier_key(row[0])
    }


def _snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "curing_cycle": row.get("curing_cycle"),
        "normal_curing_minutes": row.get("normal_curing_minutes"),
        "normal_curing_time_text": row.get("normal_curing_time_text"),
        "handling_time": row.get("handling_time"),
        "day_plan": row.get("day_plan"),
        "night_plan": row.get("night_plan"),
        "total_plan": row.get("total_plan"),
        "approval_status": row.get("planning_manager_approval_status"),
        "approval_note": row.get("planning_manager_approval_note"),
        "process_standard_source": row.get("process_standard_source"),
        "process_standard_confidence": row.get("process_standard_confidence"),
        "process_standard_peer_count": row.get("process_standard_peer_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    report_root = project_root / "reports"
    report_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_directory = (
        report_root / f"process_standard_integrity_v6_5_{stamp}"
    )
    report_directory.mkdir(parents=True, exist_ok=True)

    backup_table = f"smds_process_standard_backup_{stamp}"
    changes: list[dict[str, Any]] = []

    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        _ensure_schema(conn)

        backup_sql = (
            'CREATE TABLE "' + backup_table + '" AS SELECT * FROM smds'
        )
        conn.execute(text(backup_sql))

        approval_backup = _latest_approval_backup(conn)
        approved_keys = _approved_keys(conn, approval_backup)
        rows = [
            dict(row)
            for row in conn.execute(
                text("SELECT * FROM smds ORDER BY id")
            ).mappings().all()
        ]
        total_rows = len(rows)
        missing_before = sum(
            not process_standard_complete(row)
            for row in rows
        )

        run_id = conn.execute(
            text(
                """
                INSERT INTO process_standard_repair_runs (
                    version,
                    backup_table,
                    approval_backup_table,
                    total_rows,
                    missing_before,
                    report_directory
                )
                VALUES (
                    :version,
                    :backup_table,
                    :approval_backup_table,
                    :total_rows,
                    :missing_before,
                    :report_directory
                )
                RETURNING id
                """
            ),
            {
                "version": VERSION,
                "backup_table": backup_table,
                "approval_backup_table": approval_backup,
                "total_rows": total_rows,
                "missing_before": missing_before,
                "report_directory": str(report_directory),
            },
        ).scalar_one()

        inferred_rows = 0
        approvals_restored = 0
        unresolved_rows = 0
        peer_rows = [dict(row) for row in rows]
        process_standard_index = build_process_standard_index(
            peer_rows
        )

        for original in rows:
            current = dict(original)
            before = _snapshot(current)
            resolution = None

            if not process_standard_complete(current):
                resolution = process_standard_index.resolve(
                    current
                )
                if resolution:
                    current.update(resolution.as_smds_values())
                    conn.execute(
                        text(
                            """
                            UPDATE smds
                            SET
                                curing_cycle = :curing_cycle,
                                normal_curing_minutes = :normal_curing_minutes,
                                normal_curing_time_text = :normal_curing_time_text,
                                handling_time = :handling_time,
                                day_plan = :day_plan,
                                night_plan = :night_plan,
                                total_plan = :total_plan,
                                process_standard_source = :source,
                                process_standard_confidence = :confidence,
                                process_standard_peer_count = :peer_count,
                                process_standard_inferred_at =
                                    CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                            """
                        ),
                        {
                            "id": current["id"],
                            "curing_cycle": resolution.curing_cycle,
                            "normal_curing_minutes": resolution.normal_curing_minutes,
                            "normal_curing_time_text": resolution.normal_curing_time_text,
                            "handling_time": resolution.handling_time,
                            "day_plan": resolution.day_plan,
                            "night_plan": resolution.night_plan,
                            "total_plan": resolution.total_plan,
                            "source": resolution.source,
                            "confidence": resolution.confidence,
                            "peer_count": resolution.peer_count,
                        },
                    )
                    inferred_rows += 1

            evidence, evidence_text = _approval_evidence(
                current,
                approved_keys,
            )
            currently_approved = (
                str(
                    current.get(
                        "planning_manager_approval_status"
                    )
                    or ""
                ).strip().lower()
                == "approved"
            )
            approval_restored = False
            approval_evidence = ""

            if (
                not currently_approved
                and evidence
                and process_standard_complete(current)
                and _valid_mapping(current)
            ):
                approval_evidence = evidence_text
                existing_note = str(
                    current.get(
                        "planning_manager_approval_note"
                    )
                    or ""
                ).strip()
                suffix = (
                    "V6.5 restored Approved status from verified "
                    "historical approval evidence after process-standard "
                    "validation."
                )
                new_note = (
                    f"{existing_note} | {suffix}"
                    if existing_note
                    else suffix
                )
                conn.execute(
                    text(
                        """
                        UPDATE smds
                        SET
                            planning_manager_approval_status = 'Approved',
                            planning_manager_approval_note = :note,
                            planning_manager_approved_at =
                                COALESCE(
                                    planning_manager_approved_at,
                                    CURRENT_TIMESTAMP
                                ),
                            manager_approval_updated_at =
                                CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": current["id"],
                        "note": new_note,
                    },
                )
                current[
                    "planning_manager_approval_status"
                ] = "Approved"
                current[
                    "planning_manager_approval_note"
                ] = new_note
                approval_restored = True
                approvals_restored += 1

            if process_standard_complete(current):
                repair_status = (
                    "INFERRED_AND_VALIDATED"
                    if resolution
                    else "EXISTING_VALID"
                )
            else:
                repair_status = "UNRESOLVED_REVIEW_REQUIRED"
                unresolved_rows += 1

            after = _snapshot(current)
            source = (
                resolution.source
                if resolution
                else str(
                    current.get(
                        "process_standard_source"
                    )
                    or ""
                )
            )
            confidence = (
                resolution.confidence
                if resolution
                else float(
                    current.get(
                        "process_standard_confidence"
                    )
                    or 0
                )
            )
            peer_count = (
                resolution.peer_count
                if resolution
                else int(
                    current.get(
                        "process_standard_peer_count"
                    )
                    or 0
                )
            )
            group_count = (
                resolution.group_count
                if resolution
                else 0
            )

            conn.execute(
                text(
                    """
                    INSERT INTO process_standard_repair_rows (
                        run_id,
                        smds_id,
                        sap_code,
                        material_description,
                        repair_status,
                        source,
                        confidence,
                        peer_count,
                        group_count,
                        approval_restored,
                        approval_evidence,
                        before_json,
                        after_json
                    )
                    VALUES (
                        :run_id,
                        :smds_id,
                        :sap_code,
                        :material_description,
                        :repair_status,
                        :source,
                        :confidence,
                        :peer_count,
                        :group_count,
                        :approval_restored,
                        :approval_evidence,
                        CAST(:before_json AS JSONB),
                        CAST(:after_json AS JSONB)
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "smds_id": current["id"],
                    "sap_code": str(current.get("sap_code") or ""),
                    "material_description": str(
                        current.get("material_description") or ""
                    ),
                    "repair_status": repair_status,
                    "source": source,
                    "confidence": confidence,
                    "peer_count": peer_count,
                    "group_count": group_count,
                    "approval_restored": approval_restored,
                    "approval_evidence": approval_evidence,
                    "before_json": json.dumps(before, default=str),
                    "after_json": json.dumps(after, default=str),
                },
            )

            if (
                resolution
                or approval_restored
                or repair_status == "UNRESOLVED_REVIEW_REQUIRED"
            ):
                changes.append(
                    {
                        "smds_id": current["id"],
                        "sap_code": str(current.get("sap_code") or ""),
                        "material_description": str(
                            current.get("material_description") or ""
                        ),
                        "repair_status": repair_status,
                        "curing_cycle": current.get("curing_cycle"),
                        "normal_curing_minutes": current.get(
                            "normal_curing_minutes"
                        ),
                        "handling_time": current.get("handling_time"),
                        "day_plan": current.get("day_plan"),
                        "night_plan": current.get("night_plan"),
                        "total_plan": current.get("total_plan"),
                        "source": source,
                        "confidence": confidence,
                        "peer_count": peer_count,
                        "group_count": group_count,
                        "approval_status": current.get(
                            "planning_manager_approval_status"
                        ),
                        "approval_restored": approval_restored,
                        "approval_evidence": approval_evidence,
                    }
                )

        missing_after = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM smds
                WHERE COALESCE(normal_curing_minutes, 0) <= 0
                   OR handling_time IS NULL
                   OR COALESCE(day_plan, 0) <= 0
                   OR COALESCE(night_plan, 0) <= 0
                   OR COALESCE(total_plan, 0) <= 0
                """
            )
        ).scalar_one()

        conn.execute(
            text(
                """
                DELETE FROM mpps_master_data_issues
                WHERE issue_code IN (
                    'PROCESS_STANDARD_UNRESOLVED_V6_5',
                    'PROCESS_STANDARD_INFERRED_V6_5'
                )
                """
            )
        )
        if inferred_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO mpps_master_data_issues (
                        issue_code,
                        severity,
                        entity_type,
                        entity_key,
                        affected_count,
                        details,
                        resolution_hint
                    )
                    VALUES (
                        'PROCESS_STANDARD_INFERRED_V6_5',
                        'INFO',
                        'SMDS',
                        'ALL',
                        :affected_count,
                        :details,
                        :resolution_hint
                    )
                    """
                ),
                {
                    "affected_count": inferred_rows,
                    "details": (
                        "Missing process standards were filled only from "
                        "high-confidence physical-resource peer consensus."
                    ),
                    "resolution_hint": (
                        "Review the V6.5 audit report and retain the values "
                        "unless engineering standards provide a newer rule."
                    ),
                },
            )
        if unresolved_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO mpps_master_data_issues (
                        issue_code,
                        severity,
                        entity_type,
                        entity_key,
                        affected_count,
                        details,
                        resolution_hint
                    )
                    VALUES (
                        'PROCESS_STANDARD_UNRESOLVED_V6_5',
                        'BLOCKER',
                        'SMDS',
                        'ALL',
                        :affected_count,
                        :details,
                        :resolution_hint
                    )
                    """
                ),
                {
                    "affected_count": unresolved_rows,
                    "details": (
                        "No sufficiently consistent resource-peer standard "
                        "was available. These rows remain unapproved and "
                        "cannot receive a fabricated production rate."
                    ),
                    "resolution_hint": (
                        "Enter an approved curing cycle and handling time "
                        "in SMDS Master. Day/night/total plan must then be "
                        "reviewed and approved."
                    ),
                },
            )

        summary = {
            "version": VERSION,
            "backup_table": backup_table,
            "approval_backup_table": approval_backup,
            "total_rows": total_rows,
            "missing_before": missing_before,
            "inferred_rows": inferred_rows,
            "approvals_restored": approvals_restored,
            "unresolved_rows": unresolved_rows,
            "missing_after": int(missing_after),
        }
        conn.execute(
            text(
                """
                UPDATE process_standard_repair_runs
                SET
                    inferred_rows = :inferred_rows,
                    approvals_restored = :approvals_restored,
                    unresolved_rows = :unresolved_rows,
                    missing_after = :missing_after,
                    summary_json = CAST(:summary_json AS JSONB)
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "inferred_rows": inferred_rows,
                "approvals_restored": approvals_restored,
                "unresolved_rows": unresolved_rows,
                "missing_after": int(missing_after),
                "summary_json": json.dumps(summary),
            },
        )

        example = conn.execute(
            text(
                """
                SELECT
                    sap_code,
                    curing_cycle,
                    normal_curing_minutes,
                    handling_time,
                    day_plan,
                    night_plan,
                    total_plan,
                    planning_manager_approval_status,
                    process_standard_source,
                    process_standard_confidence,
                    process_standard_peer_count
                FROM smds
                WHERE mpps_identifier_key(sap_code)
                    = mpps_identifier_key('60006811')
                LIMIT 1
                """
            )
        ).mappings().first()

    fieldnames = [
        "smds_id",
        "sap_code",
        "material_description",
        "repair_status",
        "curing_cycle",
        "normal_curing_minutes",
        "handling_time",
        "day_plan",
        "night_plan",
        "total_plan",
        "source",
        "confidence",
        "peer_count",
        "group_count",
        "approval_status",
        "approval_restored",
        "approval_evidence",
    ]
    report_csv = report_directory / "process_standard_audit.csv"
    with report_csv.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(changes)

    (report_directory / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    with (
        report_directory / "unresolved_items.csv"
    ).open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            row
            for row in changes
            if row["repair_status"] == "UNRESOLVED_REVIEW_REQUIRED"
        )

    print("PROCESS STANDARD INTEGRITY V6.5 REPAIR COMPLETED")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"report_directory: {report_directory}")
    if example:
        print(
            "SAP 60006811: "
            f"cycle={example.get('curing_cycle')}, "
            f"handling={example.get('handling_time')}, "
            f"day={example.get('day_plan')}, "
            f"night={example.get('night_plan')}, "
            f"total={example.get('total_plan')}, "
            f"approval={example.get('planning_manager_approval_status')}, "
            f"confidence={example.get('process_standard_confidence')}, "
            f"peers={example.get('process_standard_peer_count')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
