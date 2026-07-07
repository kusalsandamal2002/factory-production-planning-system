from __future__ import annotations

from app.services.smds_schema import ensure_excel_foundation_tables


def main() -> None:
    ensure_excel_foundation_tables()
    print("Excel foundation tables are ready.")


if __name__ == "__main__":
    main()
