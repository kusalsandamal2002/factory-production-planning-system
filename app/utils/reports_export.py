from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path


def export_to_csv(headers: list[str], rows: list[list[str]], filename_prefix: str) -> str:
    # Set the destination directory as 'exports' under the workspace root
    base_dir = Path(__file__).resolve().parent.parent.parent
    export_dir = base_dir / "exports"
    
    if not export_dir.exists():
        export_dir.mkdir(parents=True, exist_ok=True)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.csv"
    filepath = export_dir / filename
    
    with open(filepath, mode="w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)
        
    return str(filepath)
