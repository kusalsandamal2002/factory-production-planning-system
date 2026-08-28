from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPPS_PORTABLE_ROOT", str(ROOT))


def apply_training_priority() -> str:
    profile = str(os.environ.get("MPPS_ML_PROFILE") or "").strip().upper()
    if profile not in {"MAX", "MAX_QUALITY", "HIGH", "HIGH_QUALITY"}:
        return "NORMAL"

    if os.name != "nt":
        return "MAX_QUALITY"

    try:
        import ctypes

        ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.kernel32.SetPriorityClass(
            handle,
            ABOVE_NORMAL_PRIORITY_CLASS,
        )
        return "ABOVE_NORMAL" if ok else "NORMAL"
    except Exception:
        return "NORMAL"


from app.services.ml_finalization_service import MLFinalizationService


def progress(value: int, message: str) -> None:
    print(f"[R7 ML {int(value):03d}%] {message}", flush=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="MPPS R7 final historical-data and ML training pipeline"
    )
    result.add_argument(
        "--prepare",
        action="store_true",
        help="Verify/repair stock authority and print current readiness only.",
    )
    result.add_argument(
        "--all",
        action="store_true",
        help="Import Historical Inbox, validate, train and auto-promote eligible models.",
    )
    result.add_argument(
        "--install-runtime",
        action="store_true",
        help="Install missing portable numpy/scikit-learn/joblib/xgboost runtime packages.",
    )
    result.add_argument(
        "--no-stock-repair",
        action="store_true",
        help="Do not rebuild Current Stock from the exact committed workbook.",
    )
    result.add_argument(
        "--no-promote",
        action="store_true",
        help="Train candidates but do not promote champions.",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    prepare_only = bool(args.prepare and not args.all)
    priority = apply_training_priority()
    profile = str(os.environ.get("MPPS_ML_PROFILE") or "STANDARD").strip().upper()
    workers = str(os.environ.get("MPPS_ML_THREADS") or "AUTO").strip()
    print(
        f"[R7 ML] Training profile={profile}; workers={workers}; "
        f"process_priority={priority}",
        flush=True,
    )

    report = MLFinalizationService.run_final_pipeline(
        import_inbox=not prepare_only,
        train=not prepare_only,
        install_runtime=bool(args.install_runtime),
        repair_stock=not bool(args.no_stock_repair),
        auto_promote=not bool(args.no_promote),
        progress=progress,
    )

    print("", flush=True)
    print("=" * 72, flush=True)
    print(" MPPS R7 FINAL ML PIPELINE RESULT", flush=True)
    print("=" * 72, flush=True)
    print(f"Status                : {report.get('status')}", flush=True)
    stock = report.get("stock_authority") or {}
    readiness = report.get("readiness_after") or {}
    dataset = readiness.get("dataset") or {}
    training = report.get("training") or {}
    runtime = report.get("runtime") or {}
    history = report.get("historical_import") or {}

    print(f"Stock verified        : {stock.get('verified')}", flush=True)
    print(f"Stock repaired        : {stock.get('repaired')}", flush=True)
    print(f"ML runtime ready      : {runtime.get('required_ready')}", flush=True)
    print(f"History span          : {dataset.get('history_days')} days", flush=True)
    print(f"Observation days      : {dataset.get('observation_days')}", flush=True)
    print(f"Observation rows      : {dataset.get('total_rows')}", flush=True)
    print(
        f"2-year preferred      : {readiness.get('preferred_two_year_history_met')}",
        flush=True,
    )
    print(
        f"Models data-ready     : {readiness.get('ready_models')}/{readiness.get('total_models')}",
        flush=True,
    )
    print(f"Inbox imported        : {history.get('imported', 0)}", flush=True)
    print(f"Inbox duplicates      : {history.get('skipped_exact_duplicates', 0)}", flush=True)
    print(f"Inbox failed          : {history.get('failed', 0)}", flush=True)
    print(f"Models trained        : {training.get('trained', 0)}", flush=True)
    print(f"Champions promoted    : {training.get('promoted', 0)}", flush=True)
    print(f"Training failures     : {training.get('failed', 0)}", flush=True)
    print(f"Total champions       : {report.get('champion_count', 0)}", flush=True)
    if report.get("training_block_reason"):
        print(f"Training gate         : {report.get('training_block_reason')}", flush=True)
    print(f"Report TXT            : {report.get('report_text')}", flush=True)
    print(f"Report JSON           : {report.get('report_json')}", flush=True)
    print("", flush=True)

    status = str(report.get("status") or "")
    if status in {"COMPLETED", "WAITING_FOR_DATA_OR_RUNTIME"}:
        nvme_root = Path(os.environ.get("MPPS_NVME_ROOT") or ROOT)
        try:
            nvme_root.mkdir(parents=True, exist_ok=True)
            (nvme_root / "R73_PIPELINE_COMPLETE.flag").write_text(
                json.dumps(
                    {
                        "status": status,
                        "report_text": report.get("report_text"),
                        "report_json": report.get("report_json"),
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    if report.get("status") == "COMPLETED_WITH_WARNINGS":
        return 2
    if report.get("status") == "WAITING_FOR_DATA_OR_RUNTIME":
        return 3
    if report.get("status") == "PAUSED_SAFE":
        return 4
    if report.get("status") == "PAUSED_LOW_SPACE":
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
