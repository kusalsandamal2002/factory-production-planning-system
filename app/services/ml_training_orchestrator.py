from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import hashlib
import json
import uuid
from typing import Any, Iterable

from sqlalchemy import text

from app.database import engine
from app.services.ml_training_spec import (
    MODEL_TRAINING_SPECS,
    ModelTrainingSpec,
    get_training_spec,
)


@dataclass(frozen=True)
class TrainingWindows:
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    test_start: date
    test_end: date
    embargo_days: int = 1


class MLTrainingOrchestrator:
    """Leakage-safe training gate and model-promotion authority.

    This layer does not fabricate training. It validates normalized history,
    feature/target contracts and chronological splits; records real estimator
    results; and only promotes a candidate when validation + unseen test metrics
    satisfy model-specific rules. Operational planning remains deterministic.
    """

    @staticmethod
    def _table_exists(connection, table_name: str) -> bool:
        return bool(
            connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"),
                {"name": f"public.{table_name}"},
            ).scalar()
        )

    @staticmethod
    def _columns(connection, table_name: str) -> set[str]:
        if not MLTrainingOrchestrator._table_exists(connection, table_name):
            return set()
        return {
            str(row[0])
            for row in connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=:table_name
                    """
                ),
                {"table_name": table_name},
            ).all()
        }

    @staticmethod
    def chronological_windows(
        first_day: date,
        last_day: date,
        *,
        train_ratio: float = 0.70,
        validation_ratio: float = 0.15,
        embargo_days: int = 1,
    ) -> TrainingWindows:
        if last_day <= first_day:
            raise ValueError(
                "Historical training requires more than one dated observation."
            )
        if not 0.50 <= float(train_ratio) < 0.90:
            raise ValueError("train_ratio must be between 0.50 and 0.90.")
        if not 0.05 <= float(validation_ratio) < 0.30:
            raise ValueError(
                "validation_ratio must be between 0.05 and 0.30."
            )

        embargo = max(0, int(embargo_days))
        total_days = (last_day - first_day).days + 1
        if total_days < 60 + embargo * 2:
            raise ValueError(
                "At least 60 chronological days are required for leakage-safe training."
            )

        usable_days = total_days - embargo * 2
        train_days = max(1, int(usable_days * float(train_ratio)))
        validation_days = max(
            1, int(usable_days * float(validation_ratio))
        )
        if train_days + validation_days >= usable_days:
            validation_days = max(1, usable_days - train_days - 1)

        train_end = first_day + timedelta(days=train_days - 1)
        validation_start = train_end + timedelta(days=embargo + 1)
        validation_end = validation_start + timedelta(
            days=validation_days - 1
        )
        test_start = validation_end + timedelta(days=embargo + 1)
        if test_start > last_day:
            raise ValueError("No unseen test window remains after split/embargo.")

        windows = TrainingWindows(
            train_start=first_day,
            train_end=train_end,
            validation_start=validation_start,
            validation_end=validation_end,
            test_start=test_start,
            test_end=last_day,
            embargo_days=embargo,
        )
        MLTrainingOrchestrator.validate_windows(windows)
        return windows

    @staticmethod
    def validate_windows(windows: TrainingWindows) -> None:
        if not (
            windows.train_start <= windows.train_end
            < windows.validation_start
            <= windows.validation_end
            < windows.test_start
            <= windows.test_end
        ):
            raise ValueError(
                "Train, validation and test windows must be strictly chronological and non-overlapping."
            )
        gap1 = (windows.validation_start - windows.train_end).days - 1
        gap2 = (windows.test_start - windows.validation_end).days - 1
        if gap1 < windows.embargo_days or gap2 < windows.embargo_days:
            raise ValueError("Configured split embargo is not respected.")

    @staticmethod
    def validate_feature_target_contract(
        model_key: str,
        *,
        feature_names: Iterable[str],
        target_name: str,
    ) -> dict[str, Any]:
        spec = get_training_spec(model_key)
        features = [str(value or "").strip() for value in feature_names]
        features = [value for value in features if value]
        target = str(target_name or "").strip()
        lowered = [value.lower() for value in features]
        issues: list[str] = []

        if not target:
            issues.append("Target column is empty.")
        if len(lowered) != len(set(lowered)):
            issues.append("Feature list contains duplicate columns.")
        if target.lower() in lowered:
            issues.append("Target column is also present in the feature list.")

        forbidden = {value.lower() for value in spec.forbidden_features}
        for feature in features:
            normalized = feature.lower()
            if normalized in forbidden:
                issues.append(
                    f"Feature '{feature}' is forbidden for {model_key}."
                )
            if normalized.startswith("future_") or normalized.endswith("_future"):
                issues.append(
                    f"Feature '{feature}' explicitly contains future information."
                )
            if normalized in {"label", "target", "target_value", "actual_target"}:
                issues.append(
                    f"Feature '{feature}' is label-like and cannot be used as an input."
                )

        signature_material = json.dumps(
            {
                "model_key": model_key,
                "features": sorted(features),
                "target": target,
            },
            sort_keys=True,
        )
        return {
            "model_key": model_key,
            "passed": not issues,
            "features": features,
            "target": target,
            "issues": issues,
            "feature_signature": hashlib.sha256(
                signature_material.encode("utf-8")
            ).hexdigest(),
        }

    @classmethod
    def model_readiness(cls, model_key: str) -> dict[str, Any]:
        spec = get_training_spec(model_key)
        best: dict[str, Any] | None = None

        with engine.connect() as connection:
            for candidate in spec.source_candidates:
                columns = cls._columns(connection, candidate.table)
                if not columns or candidate.date_column not in columns:
                    continue
                target = next(
                    (
                        value
                        for value in candidate.target_candidates
                        if value in columns
                    ),
                    None,
                )
                if not target:
                    continue
                features = [
                    value
                    for value in candidate.feature_candidates
                    if value in columns and value != target
                ]
                contract = cls.validate_feature_target_contract(
                    model_key,
                    feature_names=features,
                    target_name=target,
                )
                row = connection.execute(
                    text(
                        f"""
                        SELECT
                            MIN({candidate.date_column}),
                            MAX({candidate.date_column}),
                            COUNT(*),
                            COUNT(*) FILTER (
                                WHERE {target} IS NOT NULL
                                  AND NULLIF(TRIM(CAST({target} AS TEXT)),'') IS NOT NULL
                            )
                        FROM {candidate.table}
                        WHERE {candidate.date_column} IS NOT NULL
                        """
                    )
                ).one()
                first_day, last_day, total_rows, target_rows = row
                history_days = (
                    (last_day - first_day).days + 1
                    if first_day is not None and last_day is not None
                    else 0
                )
                score = (
                    int(target_rows or 0),
                    history_days,
                    len(features),
                )
                payload = {
                    "model_key": model_key,
                    "source_table": candidate.table,
                    "date_column": candidate.date_column,
                    "target": target,
                    "features": features,
                    "feature_signature": contract["feature_signature"],
                    "feature_validation_passed": contract["passed"],
                    "feature_issues": contract["issues"],
                    "first_date": first_day,
                    "last_date": last_day,
                    "history_days": history_days,
                    "total_rows": int(total_rows or 0),
                    "target_rows": int(target_rows or 0),
                    "score": score,
                }
                if best is None or payload["score"] > best["score"]:
                    best = payload

        if best is None:
            return {
                "model_key": model_key,
                "ready_to_train": False,
                "reason": "No compatible historical source/target is available.",
                "metric_name": spec.metric_name,
                "promotion_threshold": spec.promotion_threshold,
            }

        first_day = best.get("first_date")
        last_day = best.get("last_date")
        windows = None
        split_error = ""
        split_rows = {"training": 0, "validation": 0, "test": 0}
        if first_day and last_day:
            try:
                windows = cls.chronological_windows(
                    first_day, last_day, embargo_days=1
                )
                with engine.connect() as connection:
                    split_row = connection.execute(
                        text(
                            f"""
                            SELECT
                                COUNT(*) FILTER (
                                    WHERE {best['date_column']} BETWEEN :train_start AND :train_end
                                      AND {best['target']} IS NOT NULL
                                      AND NULLIF(TRIM(CAST({best['target']} AS TEXT)),'') IS NOT NULL
                                ),
                                COUNT(*) FILTER (
                                    WHERE {best['date_column']} BETWEEN :validation_start AND :validation_end
                                      AND {best['target']} IS NOT NULL
                                      AND NULLIF(TRIM(CAST({best['target']} AS TEXT)),'') IS NOT NULL
                                ),
                                COUNT(*) FILTER (
                                    WHERE {best['date_column']} BETWEEN :test_start AND :test_end
                                      AND {best['target']} IS NOT NULL
                                )
                            FROM {best['source_table']}
                            """
                        ),
                        {
                            "train_start": windows.train_start,
                            "train_end": windows.train_end,
                            "validation_start": windows.validation_start,
                            "validation_end": windows.validation_end,
                            "test_start": windows.test_start,
                            "test_end": windows.test_end,
                        },
                    ).one()
                split_rows = {
                    "training": int(split_row[0] or 0),
                    "validation": int(split_row[1] or 0),
                    "test": int(split_row[2] or 0),
                }
            except Exception as exc:
                split_error = str(exc)

        reasons: list[str] = []
        if int(best["history_days"]) < spec.min_history_days:
            reasons.append(
                f"history {best['history_days']} < {spec.min_history_days} days"
            )
        if windows is not None:
            if split_rows["training"] < spec.min_training_rows:
                reasons.append(
                    f"training rows {split_rows['training']} < {spec.min_training_rows}"
                )
            if split_rows["validation"] < spec.min_validation_rows:
                reasons.append(
                    f"validation rows {split_rows['validation']} < {spec.min_validation_rows}"
                )
            if split_rows["test"] < spec.min_test_rows:
                reasons.append(
                    f"test rows {split_rows['test']} < {spec.min_test_rows}"
                )
        elif int(best["target_rows"]) < (
            spec.min_training_rows
            + spec.min_validation_rows
            + spec.min_test_rows
        ):
            reasons.append(
                "not enough non-null target rows for train/validation/test"
            )
        if not best["feature_validation_passed"]:
            reasons.extend(best["feature_issues"])
        if not best["features"]:
            reasons.append("no usable feature columns")
        if split_error:
            reasons.append(split_error)

        dataset_material = json.dumps(
            {
                "model_key": model_key,
                "source_table": best.get("source_table"),
                "date_column": best.get("date_column"),
                "target": best.get("target"),
                "features": sorted(best.get("features") or []),
                "first_date": str(first_day or ""),
                "last_date": str(last_day or ""),
                "target_rows": int(best.get("target_rows") or 0),
                "split_rows": split_rows,
            },
            sort_keys=True,
        )
        dataset_signature = hashlib.sha256(
            dataset_material.encode("utf-8")
        ).hexdigest()

        result = dict(best)
        result.pop("score", None)
        result.update(
            {
                "ready_to_train": not reasons,
                "reason": "; ".join(reasons) if reasons else "READY TO TRAIN",
                "metric_name": spec.metric_name,
                "metric_direction": spec.metric_direction,
                "promotion_threshold": spec.promotion_threshold,
                "confidence_threshold": spec.confidence_threshold,
                "minimum_history_days": spec.min_history_days,
                "minimum_training_rows": spec.min_training_rows,
                "minimum_validation_rows": spec.min_validation_rows,
                "minimum_test_rows": spec.min_test_rows,
                "windows": asdict(windows) if windows else None,
                "split_rows": split_rows,
                "dataset_signature": dataset_signature,
            }
        )
        return result

    @classmethod
    def readiness_report(cls) -> dict[str, Any]:
        from app.services.historical_dataset_validation_service import (
            HistoricalDatasetValidationService,
        )

        data_report = HistoricalDatasetValidationService.validate(
            normalize=True,
            persist=True,
        )
        models = [
            cls.model_readiness(model_key)
            for model_key in MODEL_TRAINING_SPECS
        ]
        ready_count = sum(bool(row.get("ready_to_train")) for row in models)
        return {
            "ready_for_training": bool(
                data_report.get("ready_for_training")
                and ready_count > 0
            ),
            "dataset": data_report,
            "models": models,
            "ready_models": ready_count,
            "total_models": len(models),
            "all_models_ready": ready_count == len(models),
        }

    @classmethod
    def register_run(
        cls,
        model_key: str,
        windows: TrainingWindows,
        *,
        feature_names: Iterable[str],
        target_name: str,
        dataset_signature: str,
        message: str = "Queued for estimator-specific training",
    ) -> str:
        cls.validate_windows(windows)
        spec = get_training_spec(model_key)
        contract = cls.validate_feature_target_contract(
            model_key,
            feature_names=feature_names,
            target_name=target_name,
        )
        if not contract["passed"]:
            raise ValueError(
                "Feature/target validation failed: "
                + "; ".join(contract["issues"])
            )
        if not str(dataset_signature or "").strip():
            raise ValueError("A deterministic dataset signature is required.")

        run_key = f"R6-{model_key}-{uuid.uuid4().hex[:16]}"
        with engine.begin() as connection:
            if not cls._table_exists(connection, "mpps_ml_model_registry_v2"):
                raise RuntimeError("R6 ML registry schema is not installed.")
            existing = connection.execute(
                text(
                    "SELECT 1 FROM mpps_ml_model_registry_v2 WHERE model_key=:model_key"
                ),
                {"model_key": model_key},
            ).first()
            if existing is None:
                raise ValueError(f"Unknown/unregistered R6 model key: {model_key}")

            connection.execute(
                text(
                    """
                    INSERT INTO mpps_ml_training_runs_v2(
                        run_key,model_key,status,
                        train_start_date,train_end_date,
                        validation_start_date,validation_end_date,
                        test_start_date,test_end_date,message,
                        metric_name,leakage_check_passed,
                        feature_validation_passed,dataset_signature,
                        feature_signature,validation_report_json
                    ) VALUES(
                        :run_key,:model_key,'QUEUED',
                        :train_start,:train_end,
                        :validation_start,:validation_end,
                        :test_start,:test_end,:message,
                        :metric_name,TRUE,TRUE,:dataset_signature,
                        :feature_signature,CAST(:validation_report_json AS JSONB)
                    )
                    """
                ),
                {
                    "run_key": run_key,
                    "model_key": model_key,
                    "train_start": windows.train_start,
                    "train_end": windows.train_end,
                    "validation_start": windows.validation_start,
                    "validation_end": windows.validation_end,
                    "test_start": windows.test_start,
                    "test_end": windows.test_end,
                    "message": message,
                    "metric_name": spec.metric_name,
                    "dataset_signature": dataset_signature,
                    "feature_signature": contract["feature_signature"],
                    "validation_report_json": json.dumps(
                        {
                            "windows": asdict(windows),
                            "feature_contract": contract,
                        },
                        default=str,
                    ),
                },
            )
        return run_key

    @staticmethod
    def _metric_pass(spec: ModelTrainingSpec, score: float) -> bool:
        value = float(score)
        if spec.metric_direction == "min":
            return value <= float(spec.promotion_threshold)
        return value >= float(spec.promotion_threshold)

    @staticmethod
    def _better_than(
        spec: ModelTrainingSpec,
        candidate: float,
        incumbent: float,
        *,
        relative_margin: float = 0.01,
    ) -> bool:
        margin = max(0.0, float(relative_margin))
        if spec.metric_direction == "min":
            return float(candidate) <= float(incumbent) * (1.0 - margin)
        return float(candidate) >= float(incumbent) * (1.0 + margin)

    @classmethod
    def record_training_result(
        cls,
        run_key: str,
        *,
        model_version: str,
        training_rows: int,
        validation_rows: int,
        test_rows: int,
        validation_score: float,
        test_score: float,
        confidence_score: float,
        artifact_path: str,
        leakage_check_passed: bool,
        feature_validation_passed: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not model_version.strip():
            raise ValueError("Model version is required.")
        with engine.begin() as connection:
            run = connection.execute(
                text(
                    """
                    SELECT * FROM mpps_ml_training_runs_v2
                    WHERE run_key=:run_key
                    """
                ),
                {"run_key": run_key},
            ).mappings().first()
            if run is None:
                raise ValueError(f"Unknown training run: {run_key}")
            model_key = str(run["model_key"])
            spec = get_training_spec(model_key)

            validation_ok = (
                int(validation_rows) >= spec.min_validation_rows
                and cls._metric_pass(spec, float(validation_score))
            )
            test_ok = (
                int(test_rows) >= spec.min_test_rows
                and cls._metric_pass(spec, float(test_score))
            )
            confidence = max(0.0, min(1.0, float(confidence_score)))
            gate_passed = bool(
                int(training_rows) >= spec.min_training_rows
                and validation_ok
                and test_ok
                and confidence >= spec.confidence_threshold
                and leakage_check_passed
                and feature_validation_passed
            )
            status = "VALIDATED" if gate_passed else "REJECTED"
            message = (
                "Candidate passed validation/test promotion gates."
                if gate_passed
                else "Candidate failed one or more validation/test promotion gates."
            )

            connection.execute(
                text(
                    """
                    UPDATE mpps_ml_training_runs_v2
                    SET status=:status,
                        training_rows=:training_rows,
                        validation_rows=:validation_rows,
                        test_rows=:test_rows,
                        metric_name=:metric_name,
                        metric_value=:validation_score,
                        test_metric_value=:test_score,
                        artifact_path=:artifact_path,
                        leakage_check_passed=:leakage_check_passed,
                        feature_validation_passed=:feature_validation_passed,
                        message=:message,
                        completed_at=CURRENT_TIMESTAMP
                    WHERE run_key=:run_key
                    """
                ),
                {
                    "status": status,
                    "training_rows": int(training_rows),
                    "validation_rows": int(validation_rows),
                    "test_rows": int(test_rows),
                    "metric_name": spec.metric_name,
                    "validation_score": float(validation_score),
                    "test_score": float(test_score),
                    "artifact_path": str(artifact_path or ""),
                    "leakage_check_passed": bool(leakage_check_passed),
                    "feature_validation_passed": bool(feature_validation_passed),
                    "message": message,
                    "run_key": run_key,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO mpps_ml_model_versions_v2(
                        model_key,model_version,run_key,status,metric_name,
                        validation_score,test_score,confidence_score,artifact_path,
                        feature_signature,dataset_signature,leakage_check_passed,
                        feature_validation_passed,metadata_json,updated_at
                    ) VALUES(
                        :model_key,:model_version,:run_key,:status,:metric_name,
                        :validation_score,:test_score,:confidence_score,:artifact_path,
                        :feature_signature,:dataset_signature,:leakage_check_passed,
                        :feature_validation_passed,CAST(:metadata_json AS JSONB),CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(model_key,model_version) DO UPDATE SET
                        run_key=EXCLUDED.run_key,status=EXCLUDED.status,
                        metric_name=EXCLUDED.metric_name,
                        validation_score=EXCLUDED.validation_score,
                        test_score=EXCLUDED.test_score,
                        confidence_score=EXCLUDED.confidence_score,
                        artifact_path=EXCLUDED.artifact_path,
                        feature_signature=EXCLUDED.feature_signature,
                        dataset_signature=EXCLUDED.dataset_signature,
                        leakage_check_passed=EXCLUDED.leakage_check_passed,
                        feature_validation_passed=EXCLUDED.feature_validation_passed,
                        metadata_json=EXCLUDED.metadata_json,
                        updated_at=CURRENT_TIMESTAMP
                    """
                ),
                {
                    "model_key": model_key,
                    "model_version": model_version,
                    "run_key": run_key,
                    "status": "CANDIDATE" if gate_passed else "REJECTED",
                    "metric_name": spec.metric_name,
                    "validation_score": float(validation_score),
                    "test_score": float(test_score),
                    "confidence_score": confidence,
                    "artifact_path": str(artifact_path or ""),
                    "feature_signature": str(run.get("feature_signature") or ""),
                    "dataset_signature": str(run.get("dataset_signature") or ""),
                    "leakage_check_passed": bool(leakage_check_passed),
                    "feature_validation_passed": bool(feature_validation_passed),
                    "metadata_json": json.dumps(metadata or {}, default=str),
                },
            )

    @classmethod
    def promote_champion(
        cls,
        model_key: str,
        *,
        model_version: str,
        minimum_relative_improvement: float = 0.01,
    ) -> dict[str, Any]:
        spec = get_training_spec(model_key)
        with engine.begin() as connection:
            candidate = connection.execute(
                text(
                    """
                    SELECT * FROM mpps_ml_model_versions_v2
                    WHERE model_key=:model_key
                      AND model_version=:model_version
                    """
                ),
                {
                    "model_key": model_key,
                    "model_version": model_version,
                },
            ).mappings().first()
            if candidate is None:
                raise ValueError(
                    f"Unknown candidate {model_key}/{model_version}."
                )
            if str(candidate.get("status") or "").upper() not in {
                "CANDIDATE",
                "VALIDATED",
            }:
                raise ValueError("Only a validated candidate can be promoted.")
            if not bool(candidate.get("leakage_check_passed")):
                raise ValueError("Candidate failed leakage validation.")
            if not bool(candidate.get("feature_validation_passed")):
                raise ValueError("Candidate failed feature/target validation.")
            confidence = float(candidate.get("confidence_score") or 0)
            if confidence < spec.confidence_threshold:
                raise ValueError(
                    f"Confidence {confidence:.3f} is below {spec.confidence_threshold:.3f}."
                )
            validation_score = candidate.get("validation_score")
            test_score = candidate.get("test_score")
            if validation_score is None or test_score is None:
                raise ValueError("Validation and unseen test scores are required.")
            if not cls._metric_pass(spec, float(validation_score)):
                raise ValueError("Candidate validation metric is below the promotion gate.")
            if not cls._metric_pass(spec, float(test_score)):
                raise ValueError("Candidate unseen-test metric is below the promotion gate.")

            incumbent = connection.execute(
                text(
                    """
                    SELECT * FROM mpps_ml_model_versions_v2
                    WHERE model_key=:model_key AND status='CHAMPION'
                    ORDER BY promoted_at DESC NULLS LAST,id DESC
                    LIMIT 1
                    """
                ),
                {"model_key": model_key},
            ).mappings().first()
            if incumbent and incumbent.get("test_score") is not None:
                if not cls._better_than(
                    spec,
                    float(test_score),
                    float(incumbent["test_score"]),
                    relative_margin=minimum_relative_improvement,
                ):
                    raise ValueError(
                        "Candidate does not improve the current champion enough on the unseen test window."
                    )

            connection.execute(
                text(
                    """
                    UPDATE mpps_ml_model_versions_v2
                    SET status='RETIRED',retired_at=CURRENT_TIMESTAMP,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE model_key=:model_key AND status='CHAMPION'
                    """
                ),
                {"model_key": model_key},
            )
            connection.execute(
                text(
                    """
                    UPDATE mpps_ml_model_versions_v2
                    SET status='CHAMPION',promoted_at=CURRENT_TIMESTAMP,
                        retired_at=NULL,updated_at=CURRENT_TIMESTAMP
                    WHERE model_key=:model_key AND model_version=:model_version
                    """
                ),
                {
                    "model_key": model_key,
                    "model_version": model_version,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE mpps_ml_model_registry_v2
                    SET status='CHAMPION',champion=TRUE,
                        model_version=:model_version,
                        validation_metric=:metric_name,
                        validation_score=:validation_score,
                        confidence_score=:confidence_score,
                        training_rows=GREATEST(training_rows,:training_rows),
                        last_trained_at=CURRENT_TIMESTAMP,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE model_key=:model_key
                    """
                ),
                {
                    "model_key": model_key,
                    "model_version": model_version,
                    "metric_name": spec.metric_name,
                    "validation_score": float(validation_score),
                    "confidence_score": confidence,
                    "training_rows": int(
                        connection.execute(
                            text(
                                """
                                SELECT COALESCE(training_rows,0)
                                FROM mpps_ml_training_runs_v2
                                WHERE run_key=:run_key
                                """
                            ),
                            {"run_key": candidate.get("run_key")},
                        ).scalar()
                        or 0
                    ),
                },
            )
            if candidate.get("run_key"):
                connection.execute(
                    text(
                        """
                        UPDATE mpps_ml_training_runs_v2
                        SET status='PROMOTED',message='Promoted to champion after validation and unseen-test gates.'
                        WHERE run_key=:run_key
                        """
                    ),
                    {"run_key": candidate["run_key"]},
                )

        return {
            "model_key": model_key,
            "model_version": model_version,
            "status": "CHAMPION",
            "metric_name": spec.metric_name,
            "validation_score": float(validation_score),
            "test_score": float(test_score),
            "confidence_score": confidence,
        }
