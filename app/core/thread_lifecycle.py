from __future__ import annotations

from collections.abc import Iterable
from time import perf_counter
from typing import Any

from PySide6.QtCore import QObject, QThread


def _walk_values(value: Any, seen: set[int]) -> Iterable[QThread]:
    if value is None:
        return
    ident = id(value)
    if ident in seen:
        return
    seen.add(ident)

    if isinstance(value, QThread):
        yield value
        return

    if isinstance(value, dict):
        for key, item in list(value.items()):
            yield from _walk_values(key, seen)
            yield from _walk_values(item, seen)
        return

    if isinstance(value, (list, tuple, set, frozenset)):
        for item in list(value):
            yield from _walk_values(item, seen)
        return


def collect_qthreads(root: QObject | None) -> list[QThread]:
    if root is None:
        return []

    found: dict[int, QThread] = {}

    try:
        for thread in root.findChildren(QThread):
            found[id(thread)] = thread
    except Exception:
        pass

    seen: set[int] = set()
    try:
        attributes = vars(root)
    except Exception:
        attributes = {}

    for value in list(attributes.values()):
        for thread in _walk_values(value, seen):
            found[id(thread)] = thread

    return list(found.values())


def quiesce_qthreads(
    root: QObject | None,
    *,
    wait_ms: int = 3500,
    force_wait_ms: int = 750,
) -> dict[str, int]:
    """Stop page-owned QThreads before Qt destroys their wrappers.

    Normal worker completion is always preferred. requestInterruption/quit are sent
    first, then a bounded wait is used. terminate() is reserved for application
    shutdown only when a worker ignored the graceful stop budget.
    """

    threads = [thread for thread in collect_qthreads(root) if thread.isRunning()]
    report = {
        "found": len(threads),
        "graceful": 0,
        "forced": 0,
        "still_running": 0,
    }

    if not threads:
        return report

    for thread in threads:
        try:
            thread.requestInterruption()
        except Exception:
            pass
        try:
            thread.quit()
        except Exception:
            pass

    deadline = perf_counter() + max(0, int(wait_ms)) / 1000.0
    for thread in threads:
        if not thread.isRunning():
            report["graceful"] += 1
            continue
        remaining_ms = max(0, int((deadline - perf_counter()) * 1000))
        try:
            thread.wait(remaining_ms)
        except Exception:
            pass
        if not thread.isRunning():
            report["graceful"] += 1

    for thread in threads:
        if not thread.isRunning():
            continue
        report["forced"] += 1
        try:
            thread.terminate()
            thread.wait(max(0, int(force_wait_ms)))
        except Exception:
            pass
        if thread.isRunning():
            report["still_running"] += 1

    return report
