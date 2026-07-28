from __future__ import annotations

import argparse
import csv
from datetime import datetime
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.master_data_normalization import (
    identifier_key,
)
from database.migrations.ensure_master_data_integrity import (
    refresh_master_data_issues,
)


def _rows() -> list[dict[str, Any]]:
    with engine.begin() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT
                        issue_code,
                        severity,
                        entity_type,
                        entity_key,
                        affected_count,
                        details,
                        resolution_hint,
                        detected_at
                    FROM mpps_master_data_issues
                    ORDER BY
                        CASE severity
                            WHEN 'CRITICAL' THEN 0
                            WHEN 'HIGH' THEN 1
                            WHEN 'MEDIUM' THEN 2
                            ELSE 3
                        END,
                        issue_code,
                        entity_key
                    """
                )
            ).mappings().all()
        ]


def _mold_candidates() -> dict[str, list[str]]:
    with engine.begin() as conn:
        mold_keys = [
            str(value)
            for value in conn.execute(
                text(
                    """
                    SELECT mold_key_code
                    FROM mold_master
                    WHERE mpps_clean_text(
                            mold_key_code
                          ) <> ''
                    ORDER BY mold_key_code
                    """
                )
            ).scalars().all()
        ]
        missing_keys = [
            str(value)
            for value in conn.execute(
                text(
                    """
                    SELECT entity_key
                    FROM mpps_master_data_issues
                    WHERE issue_code =
                        'MISSING_MOLD_MASTER'
                    ORDER BY entity_key
                    """
                )
            ).scalars().all()
        ]

    identity_to_display = {
        identifier_key(value): value
        for value in mold_keys
    }
    choices = list(
        identity_to_display
    )

    result: dict[str, list[str]] = {}

    for missing in missing_keys:
        matches = get_close_matches(
            identifier_key(missing),
            choices,
            n=3,
            cutoff=0.55,
        )
        result[missing] = [
            identity_to_display[match]
            for match in matches
        ]

    return result


def _verify() -> dict[str, int]:
    with engine.begin() as conn:
        return {
            "duplicate_mold_keys": int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM (
                            SELECT
                                mpps_identifier_key(
                                    mold_key_code
                                )
                            FROM mold_master
                            GROUP BY
                                mpps_identifier_key(
                                    mold_key_code
                                )
                            HAVING COUNT(*) > 1
                        ) duplicate_keys
                        """
                    )
                ).scalar_one()
                or 0
            ),
            "duplicate_casing_types": int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM (
                            SELECT
                                mpps_identifier_key(
                                    casing_type
                                )
                            FROM casing_master
                            GROUP BY
                                mpps_identifier_key(
                                    casing_type
                                )
                            HAVING COUNT(*) > 1
                        ) duplicate_types
                        """
                    )
                ).scalar_one()
                or 0
            ),
            "casing_counter_mismatches": int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM mpps_master_data_issues
                        WHERE issue_code =
                            'CASING_COUNTER_MISMATCH'
                        """
                    )
                ).scalar_one()
                or 0
            ),
            "missing_casing_types": int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM mpps_master_data_issues
                        WHERE issue_code =
                            'MISSING_CASING_MASTER'
                        """
                    )
                ).scalar_one()
                or 0
            ),
            "missing_or_invalid_mold_keys": int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM mpps_master_data_issues
                        WHERE issue_code IN (
                            'MISSING_MOLD_MASTER',
                            'INVALID_SMDS_MOLD_KEY'
                        )
                        """
                    )
                ).scalar_one()
                or 0
            ),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="exports",
    )
    args = parser.parse_args()

    refresh_master_data_issues()

    output_dir = Path(
        args.output_dir
    ).expanduser().resolve()
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    txt_path = output_dir / (
        "MPPS_MASTER_DATA_INTEGRITY_"
        f"{stamp}.txt"
    )
    csv_path = output_dir / (
        "MPPS_MASTER_DATA_ISSUES_"
        f"{stamp}.csv"
    )

    issues = _rows()
    candidates = _mold_candidates()
    verification = _verify()

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as handle:
        fieldnames = [
            "severity",
            "issue_code",
            "entity_type",
            "entity_key",
            "affected_count",
            "details",
            "resolution_hint",
            "candidate_matches",
            "detected_at",
        ]
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()

        for issue in issues:
            writer.writerow({
                **{
                    key: issue.get(key)
                    for key in fieldnames
                    if key != "candidate_matches"
                },
                "candidate_matches": " | ".join(
                    candidates.get(
                        str(
                            issue.get(
                                "entity_key"
                            )
                            or ""
                        ),
                        [],
                    )
                ),
            })

    severity_counts: dict[str, int] = {}
    for issue in issues:
        severity = str(
            issue.get("severity") or "UNKNOWN"
        )
        severity_counts[severity] = (
            severity_counts.get(
                severity,
                0,
            )
            + 1
        )

    lines = [
        "MPPS MASTER DATA INTEGRITY REPORT",
        f"Generated: {datetime.now().isoformat()}",
        "",
        "Verification:",
    ]

    for key, value in verification.items():
        lines.append(
            f"- {key}: {value}"
        )

    lines.extend([
        "",
        f"Open issues: {len(issues)}",
        f"Severity counts: {severity_counts}",
        "",
        (
            "Software-normalization failures must be "
            "zero: duplicate mold keys, duplicate casing "
            "types, casing counter mismatches, and missing "
            "casing types."
        ),
        (
            "Missing physical mold keys are not auto-created. "
            "They require confirmation from the actual "
            "factory mold register."
        ),
        "",
    ])

    for index, issue in enumerate(
        issues,
        start=1,
    ):
        entity_key = str(
            issue.get("entity_key") or "-"
        )
        lines.extend([
            (
                f"{index}. "
                f"[{issue.get('severity')}] "
                f"{issue.get('issue_code')}"
            ),
            (
                "   Entity: "
                f"{issue.get('entity_type')} / "
                f"{entity_key}"
            ),
            (
                "   Affected rows: "
                f"{issue.get('affected_count')}"
            ),
            (
                "   Details: "
                f"{issue.get('details')}"
            ),
            (
                "   Resolution: "
                f"{issue.get('resolution_hint')}"
            ),
        ])

        close_matches = candidates.get(
            entity_key,
            [],
        )
        if close_matches:
            lines.append(
                "   Possible existing keys: "
                + ", ".join(close_matches)
            )

        lines.append("")

    txt_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    software_failures = (
        verification["duplicate_mold_keys"]
        + verification[
            "duplicate_casing_types"
        ]
        + verification[
            "casing_counter_mismatches"
        ]
        + verification[
            "missing_casing_types"
        ]
    )

    if software_failures:
        raise SystemExit(
            "MASTER DATA INTEGRITY AUDIT FAILED: "
            f"{verification}"
        )

    print(
        "MASTER DATA INTEGRITY AUDIT PASSED"
    )
    print(
        f"Open manager-review issues: "
        f"{len(issues)}"
    )
    print(
        "Unresolved physical molds: "
        f"{verification['missing_or_invalid_mold_keys']}"
    )
    print(f"TXT report: {txt_path}")
    print(f"CSV report: {csv_path}")


if __name__ == "__main__":
    main()
