from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import sys

from sqlalchemy import create_engine, text


def valid_identifier(value: str) -> bool:
    return bool(value) and value.replace("_", "").isalnum()


def looks_windows_absolute(value: str) -> bool:
    return (
        len(value) >= 3
        and value[1:3] in (":\\", ":/")
        and value[0].isalpha()
    )


root = Path(sys.argv[1]).resolve()
database_url = os.environ["DATABASE_URL"]

search_roots = (
    root / "data_sources" / "import_archive",
    root / "data_sources" / "raw_historical",
    root / "models",
    root / "ml_workspace",
)

index: dict[str, list[Path]] = {}

for base in search_roots:
    if not base.exists():
        continue
    for path in base.rglob("*"):
        if path.is_file():
            index.setdefault(path.name.lower(), []).append(path)

path_columns = {
    "archive_path",
    "file_path",
    "workbook_path",
    "source_path",
    "model_path",
    "checkpoint_path",
    "output_path",
    "stored_path",
    "artifact_path",
    "pickle_path",
}

engine = create_engine(database_url, pool_pre_ping=True)

updated = 0
unresolved = 0

with engine.begin() as conn:
    columns = conn.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND data_type IN (
                  'character varying',
                  'character',
                  'text'
              )
            """
        )
    ).mappings().all()

    for column in columns:
        table_name = str(column["table_name"])
        column_name = str(column["column_name"])

        if column_name.lower() not in path_columns:
            continue

        if not valid_identifier(table_name) or not valid_identifier(column_name):
            continue

        rows = conn.execute(
            text(
                f"""
                SELECT ctid::text AS row_ctid, "{column_name}" AS stored_value
                FROM "{table_name}"
                WHERE "{column_name}" IS NOT NULL
                  AND "{column_name}" <> ''
                """
            )
        ).mappings().all()

        for row in rows:
            value = str(row.get("stored_value") or "").strip()

            if not value:
                continue

            if not Path(value).is_absolute() and not looks_windows_absolute(value):
                continue

            try:
                filename = PureWindowsPath(value).name
            except Exception:
                filename = Path(value).name

            matches = index.get(filename.lower(), [])

            if len(matches) != 1:
                unresolved += 1
                continue

            relative = str(matches[0].relative_to(root))

            conn.execute(
                text(
                    f"""
                    UPDATE "{table_name}"
                    SET "{column_name}"=:relative_path
                    WHERE ctid::text=:row_ctid
                    """
                ),
                {
                    "relative_path": relative,
                    "row_ctid": row["row_ctid"],
                },
            )
            updated += 1

print(f"PORTABLE PATH REBASE updated={updated} unresolved={unresolved}")
