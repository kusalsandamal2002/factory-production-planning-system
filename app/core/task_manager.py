from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from typing import Any
import os
import traceback
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


@dataclass(frozen=True)
class TaskInfo:
    task_id: str
    key: str
    generation: int
    started_at: float


class _TaskSignals(QObject):
    result = Signal(str, str, int, object)
    error = Signal(str, str, int, str)
    finished = Signal(str, str, int, float)


class _TaskRunnable(QRunnable):
    def __init__(
        self,
        task_id: str,
        key: str,
        generation: int,
        fn: Callable[[], Any],
        signals: _TaskSignals,
    ) -> None:
        super().__init__()
        self.task_id = task_id
        self.key = key
        self.generation = generation
        self.fn = fn
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        started = perf_counter()
        try:
            payload = self.fn()
        except Exception:
            self.signals.error.emit(
                self.task_id,
                self.key,
                self.generation,
                traceback.format_exc(),
            )
        else:
            self.signals.result.emit(
                self.task_id,
                self.key,
                self.generation,
                payload,
            )
        finally:
            self.signals.finished.emit(
                self.task_id,
                self.key,
                self.generation,
                perf_counter() - started,
            )


class TaskManager(QObject):
    """Bounded shared worker-pool with stale-result protection.

    UI pages submit pure Python/DB work to this manager. Results are dispatched
    back through a QObject that lives on the GUI thread. Re-submitting a keyed
    task increments its generation, so older results are silently discarded.
    """

    task_started = Signal(object)
    task_finished = Signal(object, float)
    task_failed = Signal(object, str)

    _instance: "TaskManager | None" = None

    def __init__(self) -> None:
        super().__init__()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(4, min(12, (os.cpu_count() or 8) - 1)))
        self.pool.setExpiryTimeout(30000)
        self._lock = Lock()
        self._generation: dict[str, int] = {}
        self._callbacks: dict[str, tuple[Callable[[Any], None] | None, Callable[[str], None] | None, TaskInfo]] = {}
        self._signals: dict[str, _TaskSignals] = {}
        self._accepting = True

    @classmethod
    def instance(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def submit(
        self,
        key: str,
        fn: Callable[[], Any],
        *,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        priority: int = 0,
        replace: bool = True,
    ) -> TaskInfo | None:
        if not self._accepting:
            return None

        key = str(key or "task")
        with self._lock:
            current = self._generation.get(key, 0)
            generation = current + 1 if replace else current
            if generation <= 0:
                generation = 1
            self._generation[key] = generation

        task_id = uuid.uuid4().hex
        info = TaskInfo(
            task_id=task_id,
            key=key,
            generation=generation,
            started_at=perf_counter(),
        )
        signals = _TaskSignals()
        signals.result.connect(self._dispatch_result)
        signals.error.connect(self._dispatch_error)
        signals.finished.connect(self._dispatch_finished)

        with self._lock:
            self._callbacks[task_id] = (on_result, on_error, info)
            self._signals[task_id] = signals

        runnable = _TaskRunnable(task_id, key, generation, fn, signals)
        self.task_started.emit(info)
        self.pool.start(runnable, priority)
        return info

    def cancel(self, key: str) -> None:
        key = str(key)
        with self._lock:
            self._generation[key] = self._generation.get(key, 0) + 1

    def cancel_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in list(self._generation):
                if key.startswith(prefix):
                    self._generation[key] = self._generation.get(key, 0) + 1

    def cancel_all(self) -> None:
        with self._lock:
            for key in list(self._generation):
                self._generation[key] = self._generation.get(key, 0) + 1

    def is_current(self, key: str, generation: int) -> bool:
        with self._lock:
            return self._generation.get(key, 0) == generation

    @Slot(str, str, int, object)
    def _dispatch_result(self, task_id: str, key: str, generation: int, payload: Any) -> None:
        with self._lock:
            callback_tuple = self._callbacks.get(task_id)
            is_current = self._generation.get(key, 0) == generation
        if not callback_tuple or not is_current:
            return
        on_result, _on_error, _info = callback_tuple
        if on_result is not None:
            on_result(payload)

    @Slot(str, str, int, str)
    def _dispatch_error(self, task_id: str, key: str, generation: int, message: str) -> None:
        with self._lock:
            callback_tuple = self._callbacks.get(task_id)
            is_current = self._generation.get(key, 0) == generation
        if not callback_tuple or not is_current:
            return
        _on_result, on_error, info = callback_tuple
        self.task_failed.emit(info, message)
        if on_error is not None:
            on_error(message)

    @Slot(str, str, int, float)
    def _dispatch_finished(self, task_id: str, key: str, generation: int, elapsed: float) -> None:
        with self._lock:
            callback_tuple = self._callbacks.pop(task_id, None)
            self._signals.pop(task_id, None)
        if callback_tuple is not None:
            _r, _e, info = callback_tuple
            self.task_finished.emit(info, float(elapsed))

    def shutdown(self, wait_ms: int = 5000) -> bool:
        self._accepting = False
        self.cancel_all()
        try:
            self.pool.clear()
        except Exception:
            pass
        try:
            done = bool(self.pool.waitForDone(max(0, int(wait_ms))))
        except Exception:
            done = False
        if not done:
            print(
                f"[MPPS TASK WARNING] Worker pool did not fully stop within {int(wait_ms)}ms",
                flush=True,
            )
        return done
