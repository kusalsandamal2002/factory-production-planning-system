from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass


# MPPS V11 PERFORMANCE RUNTIME
# CPU/RAM acceleration is always safe. GPU is opt-in at the ML-library layer and
# is never required for deterministic planning, SQL or Excel import.


@dataclass(frozen=True)
class PerformanceRuntimeInfo:
    cpu_count: int
    process_priority: str
    thread_pool_size: int
    gpu_note: str


def _cpu_count() -> int:
    return max(1, int(os.cpu_count() or 1))


def _gpu_note() -> tuple[bool, str]:
    try:
        if shutil.which("nvidia-smi"):
            proc = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return True, proc.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass
    return False, ""


def configure_process_environment() -> PerformanceRuntimeInfo:
    """Tune process-level performance without making GPU a hard dependency."""
    cpu = _cpu_count()
    workers = cpu if cpu <= 4 else max(2, cpu - 1)

    # Numerical libraries can use all cores for large vector/tree operations.
    # The Qt/background worker pool keeps one logical core free on larger PCs so
    # the UI stays responsive while training/backfill work uses the rest.
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ.setdefault(name, str(cpu))
    os.environ.setdefault("MPPS_ML_WORKERS", str(workers))
    os.environ.setdefault("JOBLIB_TEMP_FOLDER", os.path.join(os.getenv("TEMP", "."), "mpps_joblib"))
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

    priority = "NORMAL"
    if platform.system().lower() == "windows":
        try:
            import ctypes

            ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.kernel32.SetPriorityClass(handle, ABOVE_NORMAL_PRIORITY_CLASS):
                priority = "ABOVE_NORMAL"
        except Exception:
            priority = "NORMAL"

    gpu, gpu_name = _gpu_note()
    if gpu:
        os.environ.setdefault("MPPS_GPU_AVAILABLE", "1")
        os.environ.setdefault("MPPS_GPU_NAME", gpu_name)
        note = (
            f"GPU detected: {gpu_name}. Optional XGBoost/CUDA challengers may use it; "
            "CPU remains the safe fallback."
        )
    else:
        os.environ.setdefault("MPPS_GPU_AVAILABLE", "0")
        note = (
            "No NVIDIA CUDA accelerator detected. CPU/RAM parallelism is fully enabled; "
            "GPU is not required for factory planning."
        )

    return PerformanceRuntimeInfo(
        cpu_count=cpu,
        process_priority=priority,
        thread_pool_size=max(4, workers),
        gpu_note=note,
    )


def configure_qt_thread_pool(info: PerformanceRuntimeInfo) -> None:
    try:
        from PySide6.QtCore import QThreadPool

        pool = QThreadPool.globalInstance()
        pool.setMaxThreadCount(info.thread_pool_size)
        pool.setExpiryTimeout(30_000)
    except Exception:
        pass
