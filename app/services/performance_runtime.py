from __future__ import annotations

import os
import platform
from dataclasses import dataclass


# MPPS ULTRA PERFORMANCE + GLOBAL PROGRESS V7.2


@dataclass(frozen=True)
class PerformanceRuntimeInfo:
    cpu_count: int
    process_priority: str
    thread_pool_size: int
    gpu_note: str


def _cpu_count() -> int:
    return max(1, int(os.cpu_count() or 1))


def configure_process_environment() -> PerformanceRuntimeInfo:
    """Tune safe local-process performance before heavy numerical imports.

    The deterministic planner is Python/SQL bound, so forcing it onto the GPU
    would add transfer overhead rather than make it faster. GPU acceleration is
    reserved for ML libraries that explicitly support CUDA/DirectML. CPU, RAM,
    database pooling and background worker priority are tuned here instead.
    """
    cpu = _cpu_count()

    # Allow numerical libraries used by future/local ML workloads to use the
    # available CPU cores. setdefault preserves an explicit user override.
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ.setdefault(name, str(cpu))

    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

    priority = "NORMAL"
    if platform.system().lower() == "windows":
        try:
            import ctypes

            ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.kernel32.SetPriorityClass(
                handle,
                ABOVE_NORMAL_PRIORITY_CLASS,
            ):
                priority = "ABOVE_NORMAL"
        except Exception:
            priority = "NORMAL"

    thread_pool_size = max(4, cpu)
    return PerformanceRuntimeInfo(
        cpu_count=cpu,
        process_priority=priority,
        thread_pool_size=thread_pool_size,
        gpu_note=(
            "GPU is used only by ML workloads that explicitly support it; "
            "the deterministic SQL/cavity scheduler is CPU/RAM optimized."
        ),
    )


def configure_qt_thread_pool(info: PerformanceRuntimeInfo) -> None:
    try:
        from PySide6.QtCore import QThreadPool

        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(info.thread_pool_size)
        pool.setExpiryTimeout(30_000)
    except Exception:
        pass
