from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
from statistics import mean
from typing import Any

from sqlalchemy import text

from app.config import BASE_DIR


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value if value is not None else default)))
    except Exception:
        return default


def _hash01(value: Any, salt: str) -> float:
    raw = f"{salt}|{str(value or '').strip().upper()}".encode("utf-8")
    n = int(hashlib.sha256(raw).hexdigest()[:12], 16)
    return (n % 1_000_003) / 1_000_003.0


def _wape(y_true: list[float], y_pred: list[float]) -> float:
    denom = sum(abs(x) for x in y_true)
    return sum(abs(a-b) for a,b in zip(y_true,y_pred)) / max(1.0, denom) * 100.0


@dataclass(frozen=True)
class AdvancedMLResult:
    trained: bool
    model_family: str
    device: str
    sample_count: int
    validation_wape_pct: float
    validation_mae: float
    model_path: str
    promoted: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class AdvancedCapacityML:
    """Optional global nonlinear challenger for factory execution prediction.

    The app never requires third-party ML packages to start. When XGBoost or
    scikit-learn is installed, this service trains a time-ordered challenger using
    resource features. If the accelerator is unavailable or validation is weak,
    the robust leakage-safe capacity ensemble remains champion.

    The global model predicts actual output from a proposed resource configuration.
    It is intentionally a challenger until enough historical files are backfilled.
    """

    FEATURE_VERSION = "FRCI-GLOBAL-EXEC-1"

    def __init__(self, model_dir: str | Path | None = None):
        self.model_dir = Path(model_dir or (BASE_DIR / "data_sources" / "models"))
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.model_dir / "factory_execution_ml_meta.json"
        self.pickle_path = self.model_dir / "factory_execution_ml.pkl"
        self.xgb_path = self.model_dir / "factory_execution_xgb.json"

    @staticmethod
    def _features(row: dict[str, Any]) -> list[float]:
        total_plan = max(0.0, _f(row.get("planned_total_qty")))
        day_plan = max(0.0, _f(row.get("planned_day_qty")))
        cavity_count = max(0.0, _f(row.get("distinct_cavity_count")))
        slots = max(0.0, _f(row.get("allocation_slot_count")))
        lines = max(0.0, _f(row.get("distinct_line_count")))
        production_date = row.get("production_date")
        weekday = production_date.weekday() if isinstance(production_date, date) else 0
        return [
            total_plan,
            day_plan / max(total_plan, 1.0),
            cavity_count,
            slots,
            lines,
            float(weekday),
            _hash01(row.get("sap_code"), "sap"),
            _hash01(row.get("mold_key"), "mold"),
            _hash01(row.get("casing_type"), "casing"),
            _hash01(row.get("primary_line"), "line"),
            math.log1p(total_plan),
            math.sqrt(max(cavity_count, 0.0)),
        ]

    @staticmethod
    def _validation_split(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        rows = sorted(rows, key=lambda r: (r.get("production_date"), str(r.get("sap_code") or "")))
        # Need enough unseen future observations to make promotion meaningful.
        if len(rows) < 40:
            return rows, []
        split = max(25, int(len(rows) * 0.80))
        split = min(split, len(rows) - max(10, int(len(rows) * 0.15)))
        return rows[:split], rows[split:]

    @staticmethod
    def _detect_xgboost():
        try:
            import xgboost as xgb
            return xgb
        except Exception:
            return None

    @staticmethod
    def _detect_sklearn():
        try:
            from sklearn.ensemble import HistGradientBoostingRegressor
            return HistGradientBoostingRegressor
        except Exception:
            return None

    @staticmethod
    def _gpu_available() -> bool:
        try:
            from app.services.factory_resource_intelligence_service import FactoryResourceIntelligenceService
            return FactoryResourceIntelligenceService.runtime_acceleration().gpu_available
        except Exception:
            return False

    def train(self, session, *, robust_wape: float | None = None) -> AdvancedMLResult:
        rows = [
            dict(r)
            for r in session.execute(
                text(
                    """
                    SELECT *
                    FROM mpps_fi_execution_observations
                    WHERE planned_total_qty > 0
                      AND actual_total_qty >= 0
                    ORDER BY production_date, sap_code
                    """
                )
            ).mappings().all()
        ]
        train_rows, valid_rows = self._validation_split(rows)
        if len(train_rows) < 30 or len(valid_rows) < 8:
            result = AdvancedMLResult(
                False, "ROBUST_ENSEMBLE", "cpu", len(rows),
                100.0, 0.0, "", False,
                "Advanced challenger waits for at least 30 training and 8 future validation observations.",
            )
            self._write_meta(result)
            return result

        X_train = [self._features(r) for r in train_rows]
        y_train = [max(0.0, _f(r.get("actual_total_qty"))) for r in train_rows]
        X_valid = [self._features(r) for r in valid_rows]
        y_valid = [max(0.0, _f(r.get("actual_total_qty"))) for r in valid_rows]

        xgb = self._detect_xgboost()
        estimator = None
        family = ""
        device = "cpu"
        model_path = ""

        if xgb is not None:
            cpu = max(1, int(os.cpu_count() or 1))
            params = dict(
                objective="reg:squarederror",
                n_estimators=500,
                max_depth=7,
                learning_rate=0.045,
                min_child_weight=2.0,
                subsample=0.88,
                colsample_bytree=0.88,
                reg_lambda=2.5,
                reg_alpha=0.05,
                n_jobs=cpu if cpu <= 4 else cpu - 1,
                random_state=42,
                tree_method="hist",
            )
            if self._gpu_available():
                params["device"] = "cuda"
                device = "cuda"
            try:
                estimator = xgb.XGBRegressor(**params)
                estimator.fit(X_train, y_train, verbose=False)
                family = "XGBOOST_GLOBAL_EXECUTION"
                estimator.save_model(str(self.xgb_path))
                model_path = str(self.xgb_path)
            except Exception:
                # GPU driver/CUDA mismatch must never stop factory planning.
                if params.get("device") == "cuda":
                    params.pop("device", None)
                    device = "cpu"
                    try:
                        estimator = xgb.XGBRegressor(**params)
                        estimator.fit(X_train, y_train, verbose=False)
                        family = "XGBOOST_GLOBAL_EXECUTION"
                        estimator.save_model(str(self.xgb_path))
                        model_path = str(self.xgb_path)
                    except Exception:
                        estimator = None

        if estimator is None:
            HGBR = self._detect_sklearn()
            if HGBR is not None:
                try:
                    estimator = HGBR(
                        max_iter=350,
                        learning_rate=0.055,
                        max_leaf_nodes=31,
                        l2_regularization=1.5,
                        random_state=42,
                    )
                    estimator.fit(X_train, y_train)
                    family = "SKLEARN_HIST_GRADIENT_BOOSTING"
                    device = "cpu"
                    with open(self.pickle_path, "wb") as fh:
                        pickle.dump(estimator, fh, protocol=pickle.HIGHEST_PROTOCOL)
                    model_path = str(self.pickle_path)
                except Exception:
                    estimator = None

        if estimator is None:
            result = AdvancedMLResult(
                False, "ROBUST_ENSEMBLE", "cpu", len(rows),
                100.0, 0.0, "", False,
                "Optional XGBoost/scikit-learn accelerator is not available. Robust ensemble remains active.",
            )
            self._write_meta(result)
            return result

        pred = [max(0.0, float(x)) for x in estimator.predict(X_valid)]
        wape = _wape(y_valid, pred)
        mae = mean(abs(a-b) for a,b in zip(y_valid,pred)) if y_valid else 0.0
        # Do not promote merely because a sophisticated model exists. It must
        # outperform the robust model by a meaningful margin on later unseen data.
        baseline = float(robust_wape if robust_wape is not None else 100.0)
        promoted = wape + 2.0 < baseline and wape < 35.0
        result = AdvancedMLResult(
            True, family, device, len(rows), round(wape,4), round(mae,4),
            model_path, promoted,
            (
                f"Challenger {'promoted' if promoted else 'retained for shadow validation'}; "
                f"future-period WAPE {wape:.2f}% vs robust {baseline:.2f}%."
            ),
        )
        self._write_meta(result)
        return result

    def _write_meta(self, result: AdvancedMLResult) -> None:
        payload = {
            "feature_version": self.FEATURE_VERSION,
            **result.to_dict(),
        }
        try:
            self.meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def metadata(self) -> dict[str, Any]:
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _load_model(self):
        meta = self.metadata()
        family = str(meta.get("model_family") or "")
        if family.startswith("XGBOOST") and self.xgb_path.exists():
            xgb = self._detect_xgboost()
            if xgb is None:
                return None, meta
            try:
                model = xgb.XGBRegressor()
                model.load_model(str(self.xgb_path))
                return model, meta
            except Exception:
                return None, meta
        if family.startswith("SKLEARN") and self.pickle_path.exists():
            try:
                with open(self.pickle_path, "rb") as fh:
                    return pickle.load(fh), meta
            except Exception:
                return None, meta
        return None, meta

    def predict(self, row: dict[str, Any]) -> dict[str, Any]:
        model, meta = self._load_model()
        if model is None or not bool(meta.get("promoted")):
            return {}
        try:
            value = max(0.0, float(model.predict([self._features(row)])[0]))
        except Exception:
            return {}
        return {
            "expected_actual_qty": int(round(value)),
            "model_family": meta.get("model_family"),
            "device": meta.get("device", "cpu"),
            "validation_wape_pct": meta.get("validation_wape_pct", 100.0),
            "feature_version": meta.get("feature_version", self.FEATURE_VERSION),
        }


__all__ = ["AdvancedCapacityML", "AdvancedMLResult"]
