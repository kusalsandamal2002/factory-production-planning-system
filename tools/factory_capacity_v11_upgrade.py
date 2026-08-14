from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import get_session
from app.services.factory_resource_intelligence_service import FactoryResourceIntelligenceService
from app.services.performance_runtime import configure_process_environment


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare / verify MPPS Factory Capacity Intelligence V11")
    parser.add_argument("--prepare", action="store_true", help="Create schema, bootstrap existing history, rebuild observations and train profiles")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    perf = configure_process_environment()
    result: dict[str, object] = {
        "runtime": {
            "cpu_count": perf.cpu_count,
            "thread_pool_size": perf.thread_pool_size,
            "process_priority": perf.process_priority,
            "gpu_note": perf.gpu_note,
        }
    }

    with get_session() as session:
        svc = FactoryResourceIntelligenceService()
        svc.ensure_schema(session)
        result["schema"] = "OK"
        if args.prepare:
            result["training"] = svc.train_profiles(session)
        dashboard = svc.dashboard(session, limit=20)
        result["state"] = dashboard.get("state", {})
        result["acceleration"] = dashboard.get("acceleration", {})
        result["top_profiles"] = [
            {
                "level": p.get("model_level"),
                "entity": p.get("entity_key"),
                "samples": p.get("sample_days"),
                "safe": p.get("safe_capacity_qty"),
                "expected": p.get("expected_capacity_qty"),
                "stretch": p.get("stretch_capacity_qty"),
                "confidence": p.get("confidence_score"),
                "band": p.get("confidence_band"),
            }
            for p in dashboard.get("profiles", [])[:10]
        ]

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("[MPPS V11] Factory Capacity Intelligence health check")
        print(f"Schema: {result['schema']}")
        runtime = result["runtime"]
        print(f"CPU cores: {runtime['cpu_count']} | workers: {runtime['thread_pool_size']} | priority: {runtime['process_priority']}")
        print(runtime["gpu_note"])
        state = result.get("state", {})
        print(f"Latest plan date: {state.get('latest_plan_date')}")
        print(f"Resource observations: {state.get('resource_observations', 0)}")
        print(f"Execution observations: {state.get('execution_observations', 0)}")
        print(f"Capacity profiles: {state.get('capacity_profiles', 0)}")
        print(f"High-confidence profiles: {state.get('high_confidence_profiles', 0)}")
        if args.prepare:
            print("Training/prepare result:")
            for key, value in (result.get("training") or {}).items():
                print(f"  {key}: {value}")
        print("[MPPS V11] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
