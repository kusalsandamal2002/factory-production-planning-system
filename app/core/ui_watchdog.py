from __future__ import annotations

from time import perf_counter

from PySide6.QtCore import QObject, QTimer, Signal


class UIWatchdog(QObject):
    """Detect long Qt event-loop stalls without adding work to the hot path."""

    stall_detected = Signal(float)

    def __init__(self, interval_ms: int = 100, warn_ms: int = 250, parent=None):
        super().__init__(parent)
        self.interval_ms = max(50, int(interval_ms))
        self.warn_ms = max(self.interval_ms + 25, int(warn_ms))
        self._last_tick = perf_counter()
        self._timer = QTimer(self)
        self._timer.setInterval(self.interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._last_tick = perf_counter()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        now = perf_counter()
        elapsed_ms = (now - self._last_tick) * 1000.0
        self._last_tick = now
        stall_ms = elapsed_ms - self.interval_ms
        if stall_ms >= self.warn_ms:
            print(
                f"[MPPS UI STALL] event-loop delay={stall_ms:.0f}ms",
                flush=True,
            )
            self.stall_detected.emit(float(stall_ms))
