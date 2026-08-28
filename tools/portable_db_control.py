from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(
    os.environ.get("MPPS_PORTABLE_ROOT")
    or Path(__file__).resolve().parents[1]
).resolve()

PG_BIN = ROOT / "runtime" / "postgresql" / "bin"
DEFAULT_PGDATA = ROOT / "portable_db" / "pgdata"
R73_NVME_ROOT = Path(os.environ.get("MPPS_NVME_ROOT") or r"C:\MPPS_ML_FAST")
R73_ACTIVE_FLAG = Path(
    os.environ.get("MPPS_R73_ACTIVE_FLAG")
    or (R73_NVME_ROOT / "R73_ACTIVE.flag")
)
R73_PGDATA = R73_NVME_ROOT / "pgdata"
PGDATA = Path(
    os.environ.get("MPPS_PGDATA")
    or (R73_PGDATA if R73_ACTIVE_FLAG.exists() and R73_PGDATA.exists() else DEFAULT_PGDATA)
).resolve()
LOGS = Path(os.environ.get("MPPS_PGLOGS") or (R73_NVME_ROOT / "logs" if PGDATA == R73_PGDATA.resolve() else ROOT / "logs"))

PORT = str(os.environ.get("MPPS_DB_PORT") or "55432")
DB_USER = os.environ.get("MPPS_DB_USER") or "mpps_admin"
DB_PASSWORD = os.environ.get("MPPS_DB_PASSWORD") or ""
DB_NAME = os.environ.get("MPPS_DB_NAME") or "factory_planner"

PG_ISREADY = PG_BIN / "pg_isready.exe"
PG_CTL = PG_BIN / "pg_ctl.exe"

CREATE_NO_WINDOW = 0x08000000


def _run_hidden(
    args: list[str],
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def ready(timeout: int = 1) -> bool:
    try:
        result = _run_hidden(
            [
                str(PG_ISREADY),
                "--host=127.0.0.1",
                f"--port={PORT}",
                f"--timeout={max(1, int(timeout))}",
                "--quiet",
            ],
            timeout=max(2, int(timeout) + 2),
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def write_ready() -> bool:
    try:
        import psycopg

        connection = psycopg.connect(
            host="127.0.0.1",
            port=int(PORT),
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
            connect_timeout=2,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        pg_is_in_recovery(),
                        current_setting('transaction_read_only')
                    """
                )
                recovery, read_only = cursor.fetchone()
                return (
                    not bool(recovery)
                    and str(read_only).strip().lower() == "off"
                )
        finally:
            connection.close()
    except Exception:
        return False


def wait_write_ready(seconds: int = 45) -> bool:
    deadline = time.monotonic() + max(1, int(seconds))

    while time.monotonic() < deadline:
        if ready(1) and write_ready():
            return True
        time.sleep(0.4)

    return False


def start() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)

    # CRITICAL R5.3 RULE:
    # If a PostgreSQL server already owns the configured port/data directory,
    # never start a second master. Recovery/startup state is waited out.
    if ready(1):
        if wait_write_ready(60):
            print(
                "MPPS portable PostgreSQL is already running "
                "and read-write ready."
            )
            return 0

        print(
            "ERROR: MPPS portable PostgreSQL is already running, "
            "but did not become read-write ready within 60 seconds."
        )
        print(
            "No duplicate PostgreSQL server was started. "
            "Run Stop_And_Eject_MPPS.cmd, then start MPPS again."
        )
        return 3

    pg_log = LOGS / "postgresql.log"
    control_log = LOGS / "pg_ctl_runtime.log"

    # pg_ctl is the correct Windows launcher for the PostgreSQL server.
    # DEVNULL + CREATE_NO_WINDOW prevents pg_ctl/pg_isready console windows.
    args = [
        str(PG_CTL),
        "start",
        "-D",
        str(PGDATA),
        "-l",
        str(pg_log),
        "-w",
        "-t",
        "30",
        "-o",
        f"-p {PORT} -h 127.0.0.1",
    ]

    with control_log.open("a", encoding="utf-8") as log:
        log.write(
            f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "R5.3 pg_ctl start requested\n"
        )

    try:
        result = _run_hidden(args, timeout=35)
        start_code = result.returncode
    except subprocess.TimeoutExpired:
        # A timeout must not trigger a duplicate server.
        # First verify whether PostgreSQL actually started.
        start_code = None

    if wait_write_ready(45):
        print("MPPS portable PostgreSQL started and read-write ready.")
        return 0

    if ready(1):
        print(
            "ERROR: PostgreSQL is accepting connections but is still "
            "in recovery/read-only state."
        )
        print(
            "No second server was started. "
            f"See: {pg_log}"
        )
        return 3

    if start_code is None:
        print("ERROR: pg_ctl start timed out and PostgreSQL is not ready.")
    else:
        print(
            "ERROR: pg_ctl could not start portable PostgreSQL "
            f"(exit code {start_code})."
        )

    print(f"See: {pg_log}")
    print(f"See: {control_log}")
    return 1


def stop() -> int:
    if not ready(1):
        print("MPPS portable PostgreSQL is already stopped.")
        return 0

    try:
        result = _run_hidden(
            [
                str(PG_CTL),
                "stop",
                "-D",
                str(PGDATA),
                "-m",
                "fast",
                "-w",
                "-t",
                "30",
            ],
            timeout=35,
        )
    except subprocess.TimeoutExpired:
        print("ERROR: PostgreSQL stop timed out.")
        return 1

    if result.returncode != 0:
        print(
            "ERROR: PostgreSQL did not stop cleanly "
            f"(exit code {result.returncode})."
        )
        return result.returncode or 1

    # Confirm port release; do not report success while the master is still live.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not ready(1):
            print("MPPS portable PostgreSQL stopped.")
            return 0
        time.sleep(0.25)

    print("ERROR: PostgreSQL stop returned success but port is still active.")
    return 1


def status() -> int:
    if not ready(1):
        print("MPPS portable PostgreSQL: STOPPED")
        return 1

    if write_ready():
        print("MPPS portable PostgreSQL: READY / READ-WRITE")
        return 0

    print("MPPS portable PostgreSQL: RUNNING / RECOVERY")
    return 2


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: portable_db_control.py start|stop|status")
        return 2

    command = sys.argv[1].strip().lower()

    if command == "start":
        return start()
    if command == "stop":
        return stop()
    if command == "status":
        return status()

    print(f"Unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
