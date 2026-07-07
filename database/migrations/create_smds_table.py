from __future__ import annotations

from app.services.smds_schema import ensure_smds_and_legacy_tables


def main() -> None:
    ensure_smds_and_legacy_tables()
    print("SMDS and Excel foundation tables are ready.")


if __name__ == "__main__":
    main()
