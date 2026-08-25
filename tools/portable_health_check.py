from __future__ import annotations

import os
from pathlib import Path
import platform
import sys
import time

from sqlalchemy import create_engine, text


root = Path(
    os.environ.get("MPPS_PORTABLE_ROOT")
    or Path(__file__).resolve().parents[1]
).resolve()

checks: list[tuple[str, bool, str]] = []


def add(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok), detail))


add("Portable marker", (root / ".mpps_portable_root").exists(), str(root))
add("run.py", (root / "run.py").exists())
add("Python runtime", (root / "runtime/python/python.exe").exists())
add("PostgreSQL runtime", (root / "runtime/postgresql/bin/pg_ctl.exe").exists())
add("PostgreSQL data", (root / "portable_db/pgdata/PG_VERSION").exists())
add("ML workspace", (root / "ml_workspace").is_dir())
add("Models", (root / "models").is_dir())
add("Backups", (root / "backups").is_dir())

try:
    import PySide6
    import openpyxl
    import psycopg
    import sqlalchemy
    add("Python dependencies", True)
except Exception as exc:
    add("Python dependencies", False, str(exc))

try:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url, pool_pre_ping=True)
    started = time.perf_counter()
    with engine.connect() as conn:
        value = conn.execute(text("SELECT 1")).scalar()
        db_name = conn.execute(text("SELECT current_database()")).scalar()
        version = conn.execute(text("SHOW server_version")).scalar()
    elapsed = time.perf_counter() - started
    add(
        "Portable PostgreSQL query",
        value == 1,
        f"db={db_name}; version={version}; {elapsed:.3f}s",
    )
except Exception as exc:
    add("Portable PostgreSQL query", False, str(exc))

try:
    from app.config import settings
    add(
        "Root-relative config",
        Path(settings.project_root).resolve() == root,
        str(settings.project_root),
    )
except Exception as exc:
    add("Root-relative config", False, str(exc))

try:
    import app.ui.main_window
    add("MPPS core import", True)
except Exception as exc:
    add("MPPS core import", False, str(exc))

print()
print("=" * 72)
print("MPPS PORTABLE HEALTH CHECK")
print("=" * 72)
print(f"Root   : {root}")
print(f"Python : {sys.executable}")
print(f"OS     : {platform.platform()}")
print()

failed = 0
for name, ok, detail in checks:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        failed += 1

print()
print(f"Result: {len(checks) - failed}/{len(checks)} checks passed.")

if failed:
    print("PORTABLE HEALTH CHECK FAILED")
    raise SystemExit(1)

print("PORTABLE HEALTH CHECK PASSED")
