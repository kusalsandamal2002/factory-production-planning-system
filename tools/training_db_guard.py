from __future__ import annotations

import os
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MPPS_PORTABLE_ROOT", str(ROOT))

import portable_db_control as control


def wait_write_ready(seconds: int, *, label: str) -> bool:
    deadline = time.monotonic() + max(1, int(seconds))
    next_status = 0.0

    while time.monotonic() < deadline:
        if control.write_ready():
            print(
                f"R7.2 DB GUARD: PostgreSQL read-write ready ({label}).",
                flush=True,
            )
            return True

        now = time.monotonic()
        if now >= next_status:
            remaining = max(0, int(deadline - now))
            state = "accepting connections" if control.ready(1) else "not accepting"
            print(
                "R7.2 DB GUARD: waiting for read-write state; "
                f"{state}; up to {remaining}s remaining.",
                flush=True,
            )
            next_status = now + 15.0

        time.sleep(1.0)

    return False


def main() -> int:
    print("R7.2 DB GUARD: verifying training database.", flush=True)

    # With portable_env.cmd loaded by the launcher, this check now has the
    # correct DB user/password. pg_isready alone is not enough because it does
    # not prove that the training connection can authenticate and write.
    if control.write_ready():
        print("R7.2 DB GUARD: database already read-write ready.", flush=True)
        return 0

    if control.ready(1):
        print(
            "R7.2 DB GUARD: server is reachable but the write gate is not ready. "
            "Waiting before any restart.",
            flush=True,
        )
        if wait_write_ready(300, label="existing server"):
            return 0

        print(
            "R7.2 DB GUARD: existing server did not recover within 5 minutes. "
            "Performing one clean pg_ctl fast restart.",
            flush=True,
        )
        stop_rc = control.stop()
        if stop_rc != 0 and control.ready(1):
            print(
                "ERROR: PostgreSQL could not be stopped cleanly. "
                "No force-kill was attempted.",
                flush=True,
            )
            return 2

        time.sleep(2.0)

    start_rc = control.start()
    if start_rc == 0 and control.write_ready():
        print("R7.2 DB GUARD: clean start is read-write ready.", flush=True)
        return 0

    # R5.3 intentionally has short startup timeouts. A large external-drive WAL
    # recovery may legitimately take longer, so R7.2 keeps waiting without ever
    # launching a duplicate PostgreSQL master.
    if wait_write_ready(900, label="post-restart recovery"):
        return 0

    print(
        "ERROR: Portable PostgreSQL did not become read-write ready after "
        "the extended R7.2 recovery window.",
        flush=True,
    )
    print(f"See: {ROOT / 'logs' / 'postgresql.log'}", flush=True)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
