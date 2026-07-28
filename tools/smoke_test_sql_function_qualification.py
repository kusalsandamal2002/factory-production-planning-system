from __future__ import annotations

import re
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    migration_path = (
        project_root
        / "database"
        / "migrations"
        / "ensure_master_data_integrity.py"
    )
    source = migration_path.read_text(
        encoding="utf-8-sig"
    )

    function_names = [
        "mpps_clean_text",
        "mpps_identifier_key",
        "mpps_line_key",
        "mpps_canonical_sap",
        "mpps_canonical_mold_key",
        "mpps_canonical_casing",
        "mpps_resolve_mold_key",
        "mpps_resolve_casing_type",
        "mpps_resolve_line_name",
        "trg_mpps_normalize_smds",
        "trg_mpps_normalize_mold_master",
        "trg_mpps_normalize_casing_master",
        "trg_mpps_normalize_casing_unit",
        "trg_mpps_normalize_reservation",
        "trg_mpps_normalize_line",
        "trg_mpps_normalize_sap",
    ]

    failures: list[str] = []

    for function_name in function_names:
        match = re.search(
            rf"(?<![A-Za-z0-9_.])"
            rf"{re.escape(function_name)}"
            rf"(?=\s*\()",
            source,
        )
        if match:
            line = (
                source[:match.start()]
                .count("\n")
                + 1
            )
            failures.append(
                f"{function_name} is unqualified "
                f"at line {line}"
            )

    if (
        "SET LOCAL search_path = public, pg_catalog"
        not in source
    ):
        failures.append(
            "Explicit migration search_path is missing."
        )

    if failures:
        raise AssertionError(
            "\n".join(failures)
        )

    print(
        "SQL FUNCTION QUALIFICATION TEST PASSED"
    )
    print(
        "All master-data SQL functions and triggers "
        "are public-schema qualified."
    )
    print(
        "Migration search_path is explicit."
    )


if __name__ == "__main__":
    main()
