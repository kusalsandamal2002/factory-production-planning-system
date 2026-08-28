from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.ml_platform_service import MLPlatformService
from app.services.ml_training_orchestrator import MLTrainingOrchestrator, TrainingWindows
from app.services.ml_training_spec import get_training_spec


class MLTrainingEngine:
    """Estimator runner for leakage-safe R6 model training.

    The orchestration layer owns chronology, feature/target validation and
    promotion gates. This class only trains models that have already passed those
    gates. It prefers XGBoost (CUDA when supported) and falls back to scikit-learn.
    Official planning values are never written by this service.
    """

    RELEASE = "R7"
    TRAINING_PROFILE_RELEASE = "R7.2-MAX"

    @staticmethod
    def _max_quality() -> bool:
        return str(os.environ.get("MPPS_ML_PROFILE") or "").strip().upper() in {
            "MAX",
            "MAX_QUALITY",
            "HIGH",
            "HIGH_QUALITY",
        }

    @staticmethod
    def _worker_threads() -> int:
        configured = str(os.environ.get("MPPS_ML_THREADS") or "").strip()
        if configured:
            try:
                return max(1, int(configured))
            except ValueError:
                pass
        cores = max(1, int(os.cpu_count() or 1))
        return max(1, cores - 1)

    @staticmethod
    def _models_dir() -> Path:
        project_root = Path(__file__).resolve().parents[2]
        configured = str(os.environ.get("MPPS_MODELS_DIR") or "").strip()
        path = Path(configured).expanduser() if configured else project_root / "models"
        if not path.is_absolute():
            path = project_root / path
        path = path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _clean_feature(value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        text_value = str(value).strip()
        return text_value

    @staticmethod
    def _windows(payload: dict[str, Any]) -> TrainingWindows:
        raw = dict(payload.get("windows") or {})
        if not raw:
            raise ValueError("Model readiness has no chronological windows.")
        for key in (
            "train_start", "train_end", "validation_start", "validation_end",
            "test_start", "test_end",
        ):
            value = raw.get(key)
            if isinstance(value, str):
                raw[key] = date.fromisoformat(value)
        return TrainingWindows(**raw)

    @classmethod
    def _load_rows(cls, readiness: dict[str, Any]) -> list[dict[str, Any]]:
        table = str(readiness["source_table"])
        date_col = str(readiness["date_column"])
        target = str(readiness["target"])
        features = [str(value) for value in readiness.get("features") or []]
        windows = cls._windows(readiness)

        columns = [date_col, target, *features]
        select_sql = ",".join(f'"{name}"' for name in columns)
        query = text(
            f'''SELECT {select_sql}
                FROM "{table}"
                WHERE "{date_col}" BETWEEN :first_day AND :last_day
                  AND "{target}" IS NOT NULL
                  AND NULLIF(TRIM(CAST("{target}" AS TEXT)),'') IS NOT NULL
                ORDER BY "{date_col}" ASC'''
        )
        with engine.connect() as connection:
            rows = connection.execute(
                query,
                {
                    "first_day": windows.train_start,
                    "last_day": windows.test_end,
                },
            ).mappings().all()
        return [dict(row) for row in rows]

    @classmethod
    def _split(
        cls,
        readiness: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        windows = cls._windows(readiness)
        date_col = str(readiness["date_column"])
        result = {"train": [], "validation": [], "test": []}
        for row in rows:
            day = row.get(date_col)
            if isinstance(day, datetime):
                day = day.date()
            if not isinstance(day, date):
                continue
            if windows.train_start <= day <= windows.train_end:
                result["train"].append(row)
            elif windows.validation_start <= day <= windows.validation_end:
                result["validation"].append(row)
            elif windows.test_start <= day <= windows.test_end:
                result["test"].append(row)
        return result

    @staticmethod
    def _confidence(metric_name: str, validation_score: float, test_score: float) -> float:
        metric = str(metric_name or "").upper()
        worst = max(float(validation_score), float(test_score))
        if metric in {"F1", "COMPAT_RECALL", "TOP1_HIT", "TOP5_HIT"}:
            return max(0.0, min(1.0, min(float(validation_score), float(test_score))))
        if metric == "MAE_DAYS":
            return max(0.0, min(1.0, 1.0 / (1.0 + worst / 10.0)))
        return max(0.0, min(1.0, 1.0 - worst))

    @staticmethod
    def _metric(metric_name: str, y_true, y_pred) -> float:
        import numpy as np

        metric = str(metric_name or "").upper()
        if metric == "F1":
            from sklearn.metrics import f1_score

            return float(f1_score(y_true, y_pred, average="macro", zero_division=0))
        if metric == "MAE_DAYS":
            from sklearn.metrics import mean_absolute_error

            return float(mean_absolute_error(y_true, y_pred))

        true = np.asarray(y_true, dtype=float)
        pred = np.asarray(y_pred, dtype=float)
        denominator = float(np.abs(true).sum())
        if denominator <= 1e-9:
            denominator = max(1.0, float(len(true)))
        return float(np.abs(true - pred).sum() / denominator)

    @classmethod
    def _build_estimator(
        cls,
        *,
        classification: bool,
        class_count: int | None = None,
    ):
        # MAX_QUALITY deliberately spends more compute on each eligible model.
        # The chronological validation/test gates remain unchanged, so extra
        # compute cannot turn future observations into training leakage.
        max_quality = cls._max_quality()
        threads = cls._worker_threads()

        try:
            import xgboost as xgb

            common = dict(
                n_estimators=1800 if max_quality else 350,
                max_depth=8,
                learning_rate=0.025 if max_quality else 0.05,
                subsample=0.92 if max_quality else 0.9,
                colsample_bytree=0.92 if max_quality else 0.9,
                min_child_weight=2 if max_quality else 1,
                reg_alpha=0.01 if max_quality else 0.0,
                reg_lambda=1.5 if max_quality else 1.0,
                max_bin=512 if max_quality else 256,
                tree_method="hist",
                n_jobs=threads,
                random_state=42,
            )
            if max_quality:
                common["early_stopping_rounds"] = 120

            if classification:
                return (
                    xgb.XGBClassifier(
                        **common,
                        eval_metric="mlogloss" if (class_count or 0) > 2 else "logloss",
                        device="cuda",
                    ),
                    "XGBOOST_CUDA_MAX" if max_quality else "XGBOOST_CUDA",
                )
            return (
                xgb.XGBRegressor(
                    **common,
                    eval_metric="mae",
                    device="cuda",
                ),
                "XGBOOST_CUDA_MAX" if max_quality else "XGBOOST_CUDA",
            )
        except Exception:
            pass

        return (
            cls._sklearn_estimator(classification=classification),
            "SKLEARN_RANDOM_FOREST_MAX" if max_quality else "SKLEARN_RANDOM_FOREST",
        )

    @classmethod
    def _sklearn_estimator(cls, *, classification: bool):
        threads = cls._worker_threads()
        max_quality = cls._max_quality()
        trees = 1200 if max_quality else 300

        if classification:
            from sklearn.ensemble import RandomForestClassifier

            return RandomForestClassifier(
                n_estimators=trees,
                min_samples_leaf=2,
                max_features="sqrt",
                n_jobs=threads,
                random_state=42,
                class_weight="balanced_subsample",
            )

        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(
            n_estimators=trees,
            min_samples_leaf=2,
            max_features=0.8,
            n_jobs=threads,
            random_state=42,
        )

    @classmethod
    def _fit_estimator(
        cls,
        estimator,
        backend: str,
        x_train,
        y_train,
        x_validation,
        y_validation,
    ):
        if str(backend).startswith("XGBOOST_"):
            # Validation is used only for early stopping. The chronological test
            # window stays untouched until final evaluation.
            try:
                estimator.fit(
                    x_train,
                    y_train,
                    eval_set=[(x_validation, y_validation)],
                    verbose=False,
                )
                return estimator
            except TypeError:
                # Compatibility fallback for an older XGBoost sklearn API.
                estimator.fit(x_train, y_train)
                return estimator

        estimator.fit(x_train, y_train)
        return estimator

    @classmethod
    def _fit_with_fallback(
        cls,
        estimator,
        backend: str,
        x_train,
        y_train,
        x_validation,
        y_validation,
        *,
        classification: bool,
    ):
        try:
            fitted = cls._fit_estimator(
                estimator,
                backend,
                x_train,
                y_train,
                x_validation,
                y_validation,
            )
            return fitted, backend
        except Exception as first_exc:
            if str(backend).startswith("XGBOOST_CUDA"):
                try:
                    params = estimator.get_params()
                    params["device"] = "cpu"
                    estimator.set_params(**params)
                    cpu_backend = (
                        "XGBOOST_CPU_MAX"
                        if cls._max_quality()
                        else "XGBOOST_CPU"
                    )
                    fitted = cls._fit_estimator(
                        estimator,
                        cpu_backend,
                        x_train,
                        y_train,
                        x_validation,
                        y_validation,
                    )
                    return fitted, cpu_backend
                except Exception:
                    pass

            # CUDA/CPU XGBoost can be unavailable on a particular portable
            # runtime. The fallback still uses all configured CPU workers.
            try:
                fallback = cls._sklearn_estimator(
                    classification=classification,
                )
                fallback.fit(x_train, y_train)
                return (
                    fallback,
                    "SKLEARN_RANDOM_FOREST_MAX"
                    if cls._max_quality()
                    else "SKLEARN_RANDOM_FOREST",
                )
            except Exception:
                raise first_exc

    @classmethod
    def _classification_complete_split(
        cls,
        readiness: dict[str, Any],
        rows: list[dict[str, Any]],
        *,
        target: str,
        spec,
    ) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """Move the classification cutoff only when the original holdout has new labels.

        The refit remains strictly chronological: every target class must first exist in
        the training window, then validation and test are rebuilt entirely after that
        class-universe stabilization boundary with the configured embargo preserved.
        No holdout row is copied into training and no synthetic label is created.
        """
        original_windows = cls._windows(readiness)
        original_split = cls._split(readiness, rows)
        date_col = str(readiness["date_column"])

        first_seen: dict[str, date] = {}
        for row in rows:
            day = row.get(date_col)
            if isinstance(day, datetime):
                day = day.date()
            if not isinstance(day, date):
                continue
            label = str(row.get(target))
            previous = first_seen.get(label)
            if previous is None or day < previous:
                first_seen[label] = day

        original_train_labels = {
            str(row.get(target)) for row in original_split["train"]
        }
        holdout_labels = {
            str(row.get(target))
            for group_name in ("validation", "test")
            for row in original_split[group_name]
        }
        unseen = sorted(holdout_labels - original_train_labels)
        audit: dict[str, Any] = {
            "policy": "classification_class_universe_stabilization_v1",
            "adjusted": False,
            "original_windows": {
                "train_start": original_windows.train_start.isoformat(),
                "train_end": original_windows.train_end.isoformat(),
                "validation_start": original_windows.validation_start.isoformat(),
                "validation_end": original_windows.validation_end.isoformat(),
                "test_start": original_windows.test_start.isoformat(),
                "test_end": original_windows.test_end.isoformat(),
                "embargo_days": original_windows.embargo_days,
            },
            "original_unseen_classes": unseen,
        }
        if not unseen:
            return readiness, original_split, audit

        missing_first_seen = [label for label in unseen if label not in first_seen]
        if missing_first_seen:
            raise ValueError(
                "Unable to locate first historical occurrence for target classes: "
                + ", ".join(missing_first_seen[:8])
            )

        required_train_end = max(first_seen[label] for label in unseen)
        embargo = max(0, int(original_windows.embargo_days))
        validation_start = required_train_end + timedelta(days=embargo + 1)
        last_day = original_windows.test_end
        if validation_start >= last_day:
            raise ValueError(
                "Target class universe becomes complete too late to leave an unseen "
                "validation/test period after the chronology embargo."
            )

        counts_by_day: dict[date, int] = {}
        for row in rows:
            day = row.get(date_col)
            if isinstance(day, datetime):
                day = day.date()
            if not isinstance(day, date) or day < validation_start or day > last_day:
                continue
            counts_by_day[day] = counts_by_day.get(day, 0) + 1

        candidate_days = sorted(counts_by_day)
        best_choice: tuple[tuple[int, int, int], date, date, int, int] | None = None
        for validation_end in candidate_days:
            test_start = validation_end + timedelta(days=embargo + 1)
            if test_start > last_day:
                continue
            validation_rows = sum(
                count
                for day, count in counts_by_day.items()
                if validation_start <= day <= validation_end
            )
            test_rows = sum(
                count
                for day, count in counts_by_day.items()
                if test_start <= day <= last_day
            )
            if validation_rows < spec.min_validation_rows or test_rows < spec.min_test_rows:
                continue
            # Prefer a balanced, large holdout while keeping the earliest viable split.
            score = (
                min(validation_rows, test_rows),
                validation_rows + test_rows,
                -abs(validation_rows - test_rows),
            )
            if best_choice is None or score > best_choice[0]:
                best_choice = (score, validation_end, test_start, validation_rows, test_rows)

        if best_choice is None:
            raise ValueError(
                "All target classes can be placed in the chronological training window, "
                "but not enough later rows remain for leakage-safe validation and test."
            )

        _, validation_end, test_start, _, _ = best_choice
        adjusted_windows = TrainingWindows(
            train_start=original_windows.train_start,
            train_end=required_train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            test_start=test_start,
            test_end=last_day,
            embargo_days=embargo,
        )
        MLTrainingOrchestrator.validate_windows(adjusted_windows)

        adjusted = dict(readiness)
        adjusted["windows"] = {
            "train_start": adjusted_windows.train_start,
            "train_end": adjusted_windows.train_end,
            "validation_start": adjusted_windows.validation_start,
            "validation_end": adjusted_windows.validation_end,
            "test_start": adjusted_windows.test_start,
            "test_end": adjusted_windows.test_end,
            "embargo_days": adjusted_windows.embargo_days,
        }
        split = cls._split(adjusted, rows)
        if len(split["train"]) < spec.min_training_rows:
            raise ValueError("Adjusted classification training window has too few rows.")
        if len(split["validation"]) < spec.min_validation_rows:
            raise ValueError("Adjusted classification validation window has too few rows.")
        if len(split["test"]) < spec.min_test_rows:
            raise ValueError("Adjusted classification test window has too few rows.")

        trained_labels = {str(row.get(target)) for row in split["train"]}
        final_holdout_labels = {
            str(row.get(target))
            for group_name in ("validation", "test")
            for row in split[group_name]
        }
        still_unseen = sorted(final_holdout_labels - trained_labels)
        if still_unseen:
            raise ValueError(
                "Chronology-safe split still has unseen target classes: "
                + ", ".join(still_unseen[:8])
            )

        audit.update(
            {
                "adjusted": True,
                "class_first_seen": {
                    label: first_seen[label].isoformat() for label in unseen
                },
                "adjusted_windows": {
                    "train_start": adjusted_windows.train_start.isoformat(),
                    "train_end": adjusted_windows.train_end.isoformat(),
                    "validation_start": adjusted_windows.validation_start.isoformat(),
                    "validation_end": adjusted_windows.validation_end.isoformat(),
                    "test_start": adjusted_windows.test_start.isoformat(),
                    "test_end": adjusted_windows.test_end.isoformat(),
                    "embargo_days": adjusted_windows.embargo_days,
                },
                "adjusted_rows": {
                    "training": len(split["train"]),
                    "validation": len(split["validation"]),
                    "test": len(split["test"]),
                },
            }
        )
        adjusted["split_rows"] = dict(audit["adjusted_rows"])
        return adjusted, split, audit

    CAT5_HISTORY_RANKERS = {
        "line_compatibility": {"mode": "compatibility", "top_k": None},
        "cavity_compatibility": {"mode": "compatibility", "top_k": None},
        "line_recommendation": {"mode": "recommendation", "top_k": 1},
        "cavity_recommendation": {"mode": "recommendation", "top_k": 5},
    }

    _CAT5_RANKER_CACHE: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _rank_text(value: Any) -> str:
        return " ".join(str(value or "").strip().upper().split())

    @classmethod
    def _rank_primary_key(cls, model_key: str, row: dict[str, Any]) -> str:
        sap = cls._rank_text(row.get("sap_code"))
        if model_key.startswith("cavity_"):
            line = cls._rank_text(row.get("line"))
            return f"{sap}\x1f{line}" if sap and line else ""
        return sap

    @classmethod
    def _rank_secondary_key(cls, model_key: str, row: dict[str, Any]) -> str:
        description = cls._rank_text(row.get("description"))
        if not description:
            return ""
        if model_key.startswith("cavity_"):
            line = cls._rank_text(row.get("line"))
            return f"{description}\x1f{line}" if line else ""
        return description

    @classmethod
    def _rank_fallback_key(cls, model_key: str, row: dict[str, Any]) -> str:
        if model_key.startswith("cavity_"):
            line = cls._rank_text(row.get("line"))
            return line
        return "__GLOBAL__"

    @classmethod
    def _history_ranker_payload(
        cls,
        model_key: str,
        train_rows: list[dict[str, Any]],
        *,
        target: str,
        date_column: str,
        train_end: date,
    ) -> dict[str, Any]:
        """Learn chronology-safe ranked historical evidence from training rows only."""
        recent_start = train_end - timedelta(days=540)

        def add(bucket: dict[str, dict[str, dict[str, Any]]], key: str,
                value: str, day: date | None) -> None:
            if not key or not value:
                return
            per_key = bucket.setdefault(key, {})
            stat = per_key.setdefault(
                value, {"count": 0, "recent_count": 0, "last_seen": None}
            )
            stat["count"] += 1
            if isinstance(day, date):
                if day >= recent_start:
                    stat["recent_count"] += 1
                previous = stat.get("last_seen")
                if previous is None or day > previous:
                    stat["last_seen"] = day

        primary: dict[str, dict[str, dict[str, Any]]] = {}
        secondary: dict[str, dict[str, dict[str, Any]]] = {}
        fallback: dict[str, dict[str, dict[str, Any]]] = {}
        global_bucket: dict[str, dict[str, dict[str, Any]]] = {}

        for row in train_rows:
            value = cls._rank_text(row.get(target))
            if not value:
                continue
            day = row.get(date_column)
            if isinstance(day, datetime):
                day = day.date()
            if not isinstance(day, date):
                day = None

            add(primary, cls._rank_primary_key(model_key, row), value, day)
            add(secondary, cls._rank_secondary_key(model_key, row), value, day)
            add(fallback, cls._rank_fallback_key(model_key, row), value, day)
            add(global_bucket, "__GLOBAL__", value, day)

        def freeze(bucket: dict[str, dict[str, dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
            result: dict[str, list[dict[str, Any]]] = {}
            for key, values in bucket.items():
                ranked = sorted(
                    values.items(),
                    key=lambda item: (
                        -int(item[1].get("recent_count") or 0),
                        -(item[1].get("last_seen").toordinal()
                          if isinstance(item[1].get("last_seen"), date) else 0),
                        -int(item[1].get("count") or 0),
                        item[0],
                    ),
                )
                result[key] = [
                    {
                        "value": value,
                        "count": int(stat.get("count") or 0),
                        "recent_count": int(stat.get("recent_count") or 0),
                        "last_seen": (
                            stat.get("last_seen").isoformat()
                            if isinstance(stat.get("last_seen"), date) else None
                        ),
                    }
                    for value, stat in ranked
                ]
            return result

        return {
            "ranker_release": "CAT5-HISTORY-RANKER-V1",
            "primary_rankings": freeze(primary),
            "secondary_rankings": freeze(secondary),
            "fallback_rankings": freeze(fallback),
            "global_rankings": freeze(global_bucket),
            "recent_window_days": 540,
        }

    @classmethod
    def _history_ranker_values(
        cls,
        model_key: str,
        row: dict[str, Any],
        payload: dict[str, Any],
        *,
        compatibility: bool,
    ) -> list[str]:
        primary_key = cls._rank_primary_key(model_key, row)
        primary = (payload.get("primary_rankings") or {}).get(primary_key) or []
        if primary:
            return [str(item.get("value") or "") for item in primary if item.get("value")]

        # Compatibility must not broaden "compatible" to a generic global list.
        # No item-specific historical evidence means UNKNOWN, not compatible.
        if compatibility:
            return []

        secondary_key = cls._rank_secondary_key(model_key, row)
        secondary = (payload.get("secondary_rankings") or {}).get(secondary_key) or []
        if secondary:
            return [str(item.get("value") or "") for item in secondary if item.get("value")]

        fallback_key = cls._rank_fallback_key(model_key, row)
        fallback = (payload.get("fallback_rankings") or {}).get(fallback_key) or []
        if fallback:
            return [str(item.get("value") or "") for item in fallback if item.get("value")]

        global_ranked = (payload.get("global_rankings") or {}).get("__GLOBAL__") or []
        return [str(item.get("value") or "") for item in global_ranked if item.get("value")]

    @classmethod
    def _score_history_ranker(
        cls,
        model_key: str,
        rows: list[dict[str, Any]],
        *,
        target: str,
        payload: dict[str, Any],
    ) -> tuple[float, dict[str, Any]]:
        config = dict(cls.CAT5_HISTORY_RANKERS[model_key])
        compatibility = config["mode"] == "compatibility"
        top_k = config.get("top_k")
        hits = 0
        evidence_rows = 0
        for row in rows:
            truth = cls._rank_text(row.get(target))
            if not truth:
                continue
            candidates = cls._history_ranker_values(
                model_key, row, payload, compatibility=compatibility
            )
            if candidates:
                evidence_rows += 1
            if compatibility:
                hit = truth in candidates
            else:
                limit = max(1, int(top_k or 1))
                hit = truth in candidates[:limit]
            if hit:
                hits += 1
        total = len(rows)
        score = float(hits / total) if total else 0.0
        return score, {
            "rows": total,
            "hits": hits,
            "evidence_rows": evidence_rows,
            "evidence_coverage": float(evidence_rows / total) if total else 0.0,
            "top_k": top_k,
            "mode": config["mode"],
        }

    @classmethod
    def _train_history_ranker(
        cls,
        model_key: str,
        *,
        readiness: dict[str, Any],
        spec,
        features: list[str],
        target: str,
        dataset_signature: str,
        contract: dict[str, Any],
        auto_promote: bool,
    ) -> dict[str, Any]:
        try:
            import joblib
        except Exception as exc:
            raise RuntimeError("joblib is required for CAT5 ranking artifacts.") from exc

        windows = cls._windows(readiness)
        date_column = str(readiness["date_column"])
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "source_table": readiness.get("source_table"),
                    "date_column": date_column,
                    "target": target,
                    "windows": {
                        "train_start": windows.train_start.isoformat(),
                        "train_end": windows.train_end.isoformat(),
                        "validation_start": windows.validation_start.isoformat(),
                        "validation_end": windows.validation_end.isoformat(),
                        "test_start": windows.test_start.isoformat(),
                        "test_end": windows.test_end.isoformat(),
                        "embargo_days": windows.embargo_days,
                    },
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        cached = cls._CAT5_RANKER_CACHE.get(cache_key)
        if cached is None:
            rows = cls._load_rows(readiness)
            split = cls._split(readiness, rows)
            if not all(split.values()):
                raise ValueError("Chronological train/validation/test split contains an empty window.")
            ranker = cls._history_ranker_payload(
                model_key,
                split["train"],
                target=target,
                date_column=date_column,
                train_end=windows.train_end,
            )
            cls._CAT5_RANKER_CACHE[cache_key] = {
                "split": split,
                "ranker": ranker,
            }
        else:
            split = cached["split"]
            ranker = cached["ranker"]

        if len(split["train"]) < spec.min_training_rows:
            raise ValueError("CAT5 ranking training window has too few rows.")
        if len(split["validation"]) < spec.min_validation_rows:
            raise ValueError("CAT5 ranking validation window has too few rows.")
        if len(split["test"]) < spec.min_test_rows:
            raise ValueError("CAT5 ranking test window has too few rows.")

        validation_score, validation_audit = cls._score_history_ranker(
            model_key, split["validation"], target=target, payload=ranker
        )
        test_score, test_audit = cls._score_history_ranker(
            model_key, split["test"], target=target, payload=ranker
        )
        confidence = cls._confidence(spec.metric_name, validation_score, test_score)

        dataset_signature = hashlib.sha256(
            json.dumps(
                {
                    "base_signature": dataset_signature,
                    "cat5_ranker_release": ranker["ranker_release"],
                    "metric_name": spec.metric_name,
                    "split_rows": {
                        "training": len(split["train"]),
                        "validation": len(split["validation"]),
                        "test": len(split["test"]),
                    },
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        run_key = MLTrainingOrchestrator.register_run(
            model_key,
            windows,
            feature_names=features,
            target_name=target,
            dataset_signature=dataset_signature,
            message="CAT5 chronology-safe historical ranking training started.",
        )

        version = cls.RELEASE + "-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        artifact_dir = cls._models_dir() / "challengers" / model_key
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{version}.joblib"
        artifact = {
            "model_key": model_key,
            "model_version": version,
            "backend": "HISTORY_RANKER_MAX",
            "training_profile": "MAX_QUALITY",
            "model_type": ranker["ranker_release"],
            "ranker": ranker,
            "features": features,
            "target": target,
            "metric_name": spec.metric_name,
            "windows": readiness.get("windows"),
            "dataset_signature": dataset_signature,
            "feature_signature": contract["feature_signature"],
            "validation_audit": validation_audit,
            "test_audit": test_audit,
            "created_at": datetime.now().isoformat(),
        }
        joblib.dump(artifact, artifact_path, compress=3)

        MLTrainingOrchestrator.record_training_result(
            run_key,
            model_version=version,
            training_rows=len(split["train"]),
            validation_rows=len(split["validation"]),
            test_rows=len(split["test"]),
            validation_score=validation_score,
            test_score=test_score,
            confidence_score=confidence,
            artifact_path=str(artifact_path),
            leakage_check_passed=True,
            feature_validation_passed=True,
            metadata={
                "backend": "HISTORY_RANKER_MAX",
                "training_profile": "MAX_QUALITY",
                "metric_name": spec.metric_name,
                "ranker_release": ranker["ranker_release"],
                "validation_audit": validation_audit,
                "test_audit": test_audit,
                "split_rows": {
                    "training": len(split["train"]),
                    "validation": len(split["validation"]),
                    "test": len(split["test"]),
                },
            },
        )

        promoted = False
        promotion_message = ""
        if auto_promote:
            try:
                MLTrainingOrchestrator.promote_champion(
                    model_key,
                    model_version=version,
                )
                promoted = True
                champion_dir = cls._models_dir() / "production" / model_key
                champion_dir.mkdir(parents=True, exist_ok=True)
                champion_path = champion_dir / "champion.joblib"
                temp_path = champion_dir / "champion.joblib.tmp"
                shutil.copy2(artifact_path, temp_path)
                os.replace(temp_path, champion_path)
            except Exception as exc:
                promotion_message = str(exc)

        return {
            "model_key": model_key,
            "model_version": version,
            "backend": "HISTORY_RANKER_MAX",
            "training_rows": len(split["train"]),
            "validation_rows": len(split["validation"]),
            "test_rows": len(split["test"]),
            "metric_name": spec.metric_name,
            "validation_score": validation_score,
            "test_score": test_score,
            "confidence_score": confidence,
            "artifact_path": str(artifact_path),
            "promoted": promoted,
            "promotion_message": promotion_message,
            "run_key": run_key,
            "validation_audit": validation_audit,
            "test_audit": test_audit,
        }

    @classmethod
    def train_model(
        cls,
        model_key: str,
        *,
        auto_promote: bool = True,
    ) -> dict[str, Any]:
        # Ensure the registry exists/populates before run registration.
        MLPlatformService.snapshot()
        readiness = MLTrainingOrchestrator.model_readiness(model_key)
        if not readiness.get("ready_to_train"):
            raise ValueError(
                f"{model_key} is not ready to train: {readiness.get('reason') or 'data gate failed'}"
            )

        spec = get_training_spec(model_key)
        windows = cls._windows(readiness)
        features = list(readiness.get("features") or [])
        target = str(readiness["target"])
        dataset_signature = str(readiness.get("dataset_signature") or "")
        contract = MLTrainingOrchestrator.validate_feature_target_contract(
            model_key,
            feature_names=features,
            target_name=target,
        )
        if not contract["passed"]:
            raise ValueError("Feature/target leakage gate failed: " + "; ".join(contract["issues"]))

        if model_key in cls.CAT5_HISTORY_RANKERS:
            return cls._train_history_ranker(
                model_key,
                readiness=readiness,
                spec=spec,
                features=features,
                target=target,
                dataset_signature=dataset_signature,
                contract=contract,
                auto_promote=auto_promote,
            )

        rows = cls._load_rows(readiness)
        split = cls._split(readiness, rows)
        classification = spec.metric_name.upper() == "F1"
        classification_split_audit: dict[str, Any] = {
            "policy": "not_applicable", "adjusted": False
        }
        if classification:
            readiness, split, classification_split_audit = cls._classification_complete_split(
                readiness, rows, target=target, spec=spec
            )
            windows = cls._windows(readiness)
            dataset_signature = hashlib.sha256(
                json.dumps(
                    {
                        "base_signature": dataset_signature,
                        "windows": {
                            key: (value.isoformat() if isinstance(value, date) else value)
                            for key, value in dict(readiness.get("windows") or {}).items()
                        },
                        "split_rows": {
                            "training": len(split["train"]),
                            "validation": len(split["validation"]),
                            "test": len(split["test"]),
                        },
                        "class_policy": classification_split_audit,
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
        if not all(split.values()):
            raise ValueError("Chronological train/validation/test split contains an empty window.")

        try:
            import joblib
            import numpy as np
            from sklearn.feature_extraction import DictVectorizer
            from sklearn.preprocessing import LabelEncoder
        except Exception as exc:
            raise RuntimeError(
                "ML runtime is missing. Install requirements-ml-optional.txt in the portable Python runtime."
            ) from exc

        def feature_dict(row: dict[str, Any]) -> dict[str, Any]:
            return {name: cls._clean_feature(row.get(name)) for name in features}

        vectorizer = DictVectorizer(sparse=True)
        x_train = vectorizer.fit_transform([feature_dict(row) for row in split["train"]])
        x_validation = vectorizer.transform([feature_dict(row) for row in split["validation"]])
        x_test = vectorizer.transform([feature_dict(row) for row in split["test"]])

        label_encoder = None
        if classification:
            label_encoder = LabelEncoder()
            train_labels = [str(row.get(target)) for row in split["train"]]
            label_encoder.fit(train_labels)
            if len(label_encoder.classes_) < 2:
                raise ValueError("Classification training requires at least two target classes in the training window.")
            known_labels = set(str(value) for value in label_encoder.classes_)
            validation_labels = [str(row.get(target)) for row in split["validation"]]
            test_labels = [str(row.get(target)) for row in split["test"]]
            unseen = sorted((set(validation_labels) | set(test_labels)) - known_labels)
            if unseen:
                preview = ", ".join(unseen[:8])
                raise ValueError(
                    "Chronological holdout contains target classes never seen in the training window: "
                    + preview
                )
            y_train = label_encoder.transform(train_labels)
            y_validation = label_encoder.transform(validation_labels)
            y_test = label_encoder.transform(test_labels)
            class_count = len(label_encoder.classes_)
        else:
            def numeric(group):
                try:
                    return np.asarray([float(row.get(target)) for row in group], dtype=float)
                except Exception as exc:
                    raise ValueError(f"Regression target {target} contains non-numeric values.") from exc
            y_train = numeric(split["train"])
            y_validation = numeric(split["validation"])
            y_test = numeric(split["test"])
            class_count = None

        run_key = MLTrainingOrchestrator.register_run(
            model_key,
            windows,
            feature_names=features,
            target_name=target,
            dataset_signature=dataset_signature,
            message="R6 estimator training started after chronological/leakage validation.",
        )

        estimator, backend = cls._build_estimator(
            classification=classification,
            class_count=class_count,
        )
        estimator, backend = cls._fit_with_fallback(
            estimator,
            backend,
            x_train,
            y_train,
            x_validation,
            y_validation,
            classification=classification,
        )
        validation_pred = estimator.predict(x_validation)
        test_pred = estimator.predict(x_test)
        validation_score = cls._metric(spec.metric_name, y_validation, validation_pred)
        test_score = cls._metric(spec.metric_name, y_test, test_pred)
        confidence = cls._confidence(spec.metric_name, validation_score, test_score)

        version = cls.RELEASE + "-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        artifact_dir = cls._models_dir() / "challengers" / model_key
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{version}.joblib"
        joblib.dump(
            {
                "model_key": model_key,
                "model_version": version,
                "backend": backend,
                "training_profile": (
                    "MAX_QUALITY" if cls._max_quality() else "STANDARD"
                ),
                "worker_threads": cls._worker_threads(),
                "model": estimator,
                "vectorizer": vectorizer,
                "label_encoder": label_encoder,
                "features": features,
                "target": target,
                "metric_name": spec.metric_name,
                "windows": readiness.get("windows"),
                "dataset_signature": dataset_signature,
                "feature_signature": contract["feature_signature"],
                "classification_split_audit": classification_split_audit,
                "created_at": datetime.now().isoformat(),
            },
            artifact_path,
            compress=3,
        )

        MLTrainingOrchestrator.record_training_result(
            run_key,
            model_version=version,
            training_rows=len(split["train"]),
            validation_rows=len(split["validation"]),
            test_rows=len(split["test"]),
            validation_score=validation_score,
            test_score=test_score,
            confidence_score=confidence,
            artifact_path=str(artifact_path),
            leakage_check_passed=True,
            feature_validation_passed=True,
            metadata={
                "backend": backend,
                "training_profile": (
                    "MAX_QUALITY" if cls._max_quality() else "STANDARD"
                ),
                "worker_threads": cls._worker_threads(),
                "best_iteration": getattr(estimator, "best_iteration", None),
                "source_table": readiness.get("source_table"),
                "date_column": readiness.get("date_column"),
                "classification_split_audit": classification_split_audit,
                "split_rows": {
                    "training": len(split["train"]),
                    "validation": len(split["validation"]),
                    "test": len(split["test"]),
                },
            },
        )

        promoted = False
        promotion_message = ""
        if auto_promote:
            try:
                MLTrainingOrchestrator.promote_champion(
                    model_key,
                    model_version=version,
                )
                promoted = True
                champion_dir = cls._models_dir() / "production" / model_key
                champion_dir.mkdir(parents=True, exist_ok=True)
                champion_path = champion_dir / "champion.joblib"
                temp_path = champion_dir / "champion.joblib.tmp"
                shutil.copy2(artifact_path, temp_path)
                os.replace(temp_path, champion_path)
            except Exception as exc:
                promotion_message = str(exc)

        return {
            "model_key": model_key,
            "model_version": version,
            "backend": backend,
            "training_rows": len(split["train"]),
            "validation_rows": len(split["validation"]),
            "test_rows": len(split["test"]),
            "metric_name": spec.metric_name,
            "validation_score": validation_score,
            "test_score": test_score,
            "confidence_score": confidence,
            "artifact_path": str(artifact_path),
            "promoted": promoted,
            "promotion_message": promotion_message,
            "run_key": run_key,
        }

    @classmethod
    def train_ready_models(
        cls,
        *,
        auto_promote: bool = True,
        max_models: int | None = None,
    ) -> dict[str, Any]:
        readiness = MLTrainingOrchestrator.readiness_report()
        if int(readiness.get("dataset", {}).get("critical_issue_count") or 0) > 0:
            raise RuntimeError(
                "Historical dataset contains CRITICAL validation issues. Training is blocked."
            )

        ready = [row for row in readiness.get("models") or [] if row.get("ready_to_train")]
        if max_models is not None:
            ready = ready[: max(0, int(max_models))]

        results = []
        failures = []
        for row in ready:
            model_key = str(row.get("model_key") or "")
            try:
                results.append(cls.train_model(model_key, auto_promote=auto_promote))
            except Exception as exc:
                failures.append({"model_key": model_key, "error": str(exc)})

        return {
            "attempted": len(ready),
            "trained": len(results),
            "promoted": sum(bool(row.get("promoted")) for row in results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
            "readiness": readiness,
        }
