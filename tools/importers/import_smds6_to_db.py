from __future__ import annotations

import argparse
from pathlib import Path

from app.services.smds_excel_importer import import_smds_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import SMDS6.xlsx into the central smds table.")
    parser.add_argument(
        "--file",
        default="data_sources/SMDS6.xlsx",
        help="Path to SMDS6.xlsx. Default: data_sources/SMDS6.xlsx",
    )
    parser.add_argument("--sheet", default="ALL", help="Workbook sheet name. Default: ALL")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Do not truncate smds before import; upsert rows by SAP code instead.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = import_smds_workbook(
        file_path=Path(args.file),
        sheet_name=args.sheet,
        replace=not args.append,
    )

    print("SMDS import completed.")
    print(f"File: {result.file_path}")
    print(f"Sheet: {result.sheet_name}")
    print(f"Imported rows: {result.imported_rows}")
    print(f"Skipped rows: {result.skipped_rows}")


if __name__ == "__main__":
    main()
