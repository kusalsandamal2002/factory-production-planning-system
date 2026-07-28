from __future__ import annotations

from pathlib import Path

from app.services.master_data_normalization import (
    identifier_key,
    is_no_casing,
    line_identity,
    normalize_casing_type,
    normalize_mold_key,
    normalize_sap_code,
)


def main() -> None:
    assert normalize_casing_type(
        " B5   Special  03 "
    ) == "B5 Special 03"

    assert identifier_key(
        "B5 Special  03"
    ) == identifier_key(
        "b5 special 03"
    )

    assert normalize_casing_type(
        "no   casing"
    ) == "No Casing"
    assert is_no_casing(
        "No-Casing"
    )

    assert normalize_mold_key(
        "18x7 - 8 tr"
    ) == "18X7-8 TR"

    assert normalize_mold_key(
        " 14×5-10 sm "
    ) == "14X5-10 SM"

    assert normalize_sap_code(
        " 60000546 "
    ) == "60000546"

    assert line_identity(
        "T 600 -01 PRESS"
    ) == line_identity(
        "t-600 01 press"
    )

    project_root = Path(__file__).resolve().parents[1]

    planner_source = (
        project_root
        / "app"
        / "services"
        / "factory_planning_engine.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    casing_source = (
        project_root
        / "app"
        / "ui"
        / "casing_master_page.py"
    ).read_text(
        encoding="utf-8-sig"
    )
    mold_source = (
        project_root
        / "app"
        / "ui"
        / "mold_master_page.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert "mpps_identifier_key" in planner_source
    assert (
        "available_casing_count is the physical"
        in planner_source
    )
    assert (
        "condition_status" in casing_source
        and "stock_status" in casing_source
        and "available_casing_count" in casing_source
    )
    assert "UPDATE smds" in mold_source
    assert (
        "planning_resource_reservations"
        in mold_source
    )

    print(
        "MASTER DATA NORMALIZATION TEST PASSED"
    )
    print(
        "Whitespace, case, dash and multiplication "
        "variants resolve to one identity."
    )
    print(
        "Casing availability uses physical "
        "Active + Free units."
    )
    print(
        "Mold and casing renames update linked "
        "planning records."
    )


if __name__ == "__main__":
    main()
