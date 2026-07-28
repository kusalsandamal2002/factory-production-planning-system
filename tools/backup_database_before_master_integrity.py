from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime

from sqlalchemy.engine import make_url

from app.config import settings


def _find_pg_dump() -> Path:
    from_path = shutil.which("pg_dump") or shutil.which("pg_dump.exe")
    if from_path:
        return Path(from_path)

    candidates: list[Path] = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if not base:
            continue
        for version in range(20, 11, -1):
            candidates.append(
                Path(base)
                / "PostgreSQL"
                / str(version)
                / "bin"
                / "pg_dump.exe"
            )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "pg_dump was not found. Add PostgreSQL bin to PATH "
        "or install PostgreSQL client tools before running this update."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / "Downloads"),
    )
    args = parser.parse_args()

    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError(
            "This safety backup supports PostgreSQL databases only."
        )

    database_name = str(url.database or "").strip()
    if not database_name:
        raise RuntimeError("DATABASE_URL has no database name.")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / (
        f"{database_name}_BEFORE_MASTER_INTEGRITY_{stamp}.backup"
    )

    pg_dump = _find_pg_dump()
    command = [
        str(pg_dump),
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--file",
        str(output_path),
        "--host",
        str(url.host or "localhost"),
        "--port",
        str(url.port or 5432),
        "--username",
        str(url.username or "postgres"),
        database_name,
    ]

    environment = os.environ.copy()
    if url.password is not None:
        environment["PGPASSWORD"] = str(url.password)

    completed = subprocess.run(
        command,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "PostgreSQL safety backup failed.\n"
            f"pg_dump: {pg_dump}\n"
            f"Error: {completed.stderr.strip()}"
        )

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(
            "pg_dump returned success but the backup file is missing or empty."
        )

    print("DATABASE SAFETY BACKUP PASSED")
    print(f"Database: {database_name}")
    print(f"Backup: {output_path}")
    print(f"Bytes: {output_path.stat().st_size}")


if __name__ == "__main__":
    main()
