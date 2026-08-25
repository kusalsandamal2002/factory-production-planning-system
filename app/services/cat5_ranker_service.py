from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class CAT5RankerService:
    """Read-only consumer for CAT5 historical ranking champion artifacts.

    Compatibility returns item-specific historical evidence only. Recommendation
    may use exact-description and line/global fallbacks when item history is not
    yet available. This service never writes official planning/master data.
    """

    SUPPORTED = {
        "line_compatibility",
        "cavity_compatibility",
        "line_recommendation",
        "cavity_recommendation",
    }

    @staticmethod
    def _models_dir() -> Path:
        project_root = Path(__file__).resolve().parents[2]
        configured = str(os.environ.get("MPPS_MODELS_DIR") or "").strip()
        path = Path(configured).expanduser() if configured else project_root / "models"
        if not path.is_absolute():
            path = project_root / path
        return path.resolve()

    @staticmethod
    def _norm(value: Any) -> str:
        return " ".join(str(value or "").strip().upper().split())

    @classmethod
    def _primary_key(cls, model_key: str, *, sap_code: Any, line: Any = "") -> str:
        sap = cls._norm(sap_code)
        if model_key.startswith("cavity_"):
            line_value = cls._norm(line)
            return f"{sap}\x1f{line_value}" if sap and line_value else ""
        return sap

    @classmethod
    def _secondary_key(cls, model_key: str, *, description: Any, line: Any = "") -> str:
        desc = cls._norm(description)
        if not desc:
            return ""
        if model_key.startswith("cavity_"):
            line_value = cls._norm(line)
            return f"{desc}\x1f{line_value}" if line_value else ""
        return desc

    @classmethod
    def load_champion(cls, model_key: str) -> dict[str, Any]:
        key = str(model_key or "").strip()
        if key not in cls.SUPPORTED:
            raise ValueError(f"Unsupported CAT5 ranker model: {key}")
        try:
            import joblib
        except Exception as exc:
            raise RuntimeError("joblib is required to load CAT5 champion artifacts.") from exc
        path = cls._models_dir() / "production" / key / "champion.joblib"
        if not path.exists():
            raise FileNotFoundError(f"No CAT5 champion artifact: {path}")
        artifact = joblib.load(path)
        if str(artifact.get("model_type") or "") != "CAT5-HISTORY-RANKER-V1":
            raise ValueError(f"Unexpected CAT5 artifact type for {key}.")
        return artifact

    @classmethod
    def rank(
        cls,
        model_key: str,
        *,
        sap_code: Any,
        line: Any = "",
        description: Any = "",
        top_k: int | None = None,
    ) -> dict[str, Any]:
        artifact = cls.load_champion(model_key)
        ranker = dict(artifact.get("ranker") or {})
        compatibility = str(model_key).endswith("_compatibility")

        primary_key = cls._primary_key(model_key, sap_code=sap_code, line=line)
        rows = (ranker.get("primary_rankings") or {}).get(primary_key) or []
        evidence_level = "SAP_HISTORY"

        if not rows and not compatibility:
            secondary_key = cls._secondary_key(
                model_key, description=description, line=line
            )
            rows = (ranker.get("secondary_rankings") or {}).get(secondary_key) or []
            evidence_level = "EXACT_DESCRIPTION_HISTORY"

        if not rows and not compatibility:
            fallback_key = cls._norm(line) if str(model_key).startswith("cavity_") else "__GLOBAL__"
            rows = (ranker.get("fallback_rankings") or {}).get(fallback_key) or []
            evidence_level = "LINE_HISTORY" if fallback_key != "__GLOBAL__" else "GLOBAL_HISTORY"

        if not rows and not compatibility:
            rows = (ranker.get("global_rankings") or {}).get("__GLOBAL__") or []
            evidence_level = "GLOBAL_HISTORY"

        if compatibility and not rows:
            evidence_level = "UNKNOWN_NO_ITEM_HISTORY"

        default_k = None
        if model_key == "line_recommendation":
            default_k = 1
        elif model_key == "cavity_recommendation":
            default_k = 5

        limit = top_k if top_k is not None else default_k
        selected = list(rows) if limit is None else list(rows)[:max(1, int(limit))]
        return {
            "model_key": model_key,
            "model_version": artifact.get("model_version"),
            "backend": artifact.get("backend"),
            "evidence_level": evidence_level,
            "results": selected,
        }
