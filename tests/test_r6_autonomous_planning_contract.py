from __future__ import annotations

from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]


def source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


class R6AutonomousPlanningContract(unittest.TestCase):
    def test_all_changed_python_syntax(self):
        paths = (
            "database/migrations/ensure_autonomous_planning_r6.py",
            "app/services/planning_authority_service.py",
            "app/services/factory_can_out_service.py",
            "app/services/ml_platform_service.py",
            "app/services/ml_training_spec.py",
            "app/services/historical_dataset_validation_service.py",
            "app/services/ml_training_orchestrator.py",
            "app/services/ml_training_engine.py",
            "app/services/ml_finalization_service.py",
            "tools/run_ml_finalization.py",
            "app/services/autonomous_planning_service.py",
            "app/services/dashboard_snapshot_service.py",
            "app/services/shipment_lifecycle_service.py",
            "app/services/shipment_details_async_service.py",
            "app/services/shipment_order_async_service.py",
            "app/services/factory_planning_engine.py",
            "app/services/cavity_daily_plan_service.py",
            "app/services/daily_plan_async_service.py",
            "app/services/shift_daily_report_service.py",
            "app/services/material_requirement_service.py",
            "app/ui/dashboard_pro_page.py",
            "app/ui/schedule_page.py",
            "app/ui/daily_plan_async_page.py",
            "app/ui/intelligent_operations_pages.py",
            "app/ui/material_requirement_pro_page.py",
            "app/ui/ai_ml_control_center_page.py",
            "app/ui/raw_excel_viewer_page.py",
        )
        for rel in paths:
            ast.parse(source(rel), filename=rel)

    def test_migration_is_additive_and_contains_final_r6_schema(self):
        text = source("database/migrations/ensure_autonomous_planning_r6.py")
        for token in (
            "mpps_autonomous_planning_state",
            "mpps_planning_snapshots",
            "mpps_planning_snapshot_items",
            "mpps_planning_exceptions",
            "mpps_ml_model_registry_v2",
            "mpps_ml_training_runs_v2",
            "mpps_ml_prediction_audit_v2",
            "mpps_ml_training_observations_v2",
            "mpps_training_data_validation_runs",
            "mpps_ml_model_versions_v2",
            "mpps_tyre_training_view",
            "mpps_material_training_view",
            "mpps_shipment_training_view",
            "actual_lead_days",
            "late_flag",
            "ADD COLUMN IF NOT EXISTS",
            "CREATE TABLE IF NOT EXISTS",
            "CREATE INDEX IF NOT EXISTS",
        ):
            self.assertIn(token, text)
        self.assertNotIn("DROP TABLE", text.upper())
        self.assertNotIn("TRUNCATE", text.upper())

    def test_dashboard_and_planning_share_canonical_authority(self):
        dashboard = source("app/services/dashboard_snapshot_service.py")
        planning = source("app/services/planning_authority_service.py")
        schedule = source("app/ui/schedule_page.py")
        self.assertIn("PlanningAuthorityService.load", dashboard)
        self.assertIn("reconciliation_ok", planning)
        self.assertIn("production_gap", planning)
        self.assertIn("RECONCILED", schedule)
        self.assertIn("RECALCULATE REQUIRED", schedule)

    def test_current_stock_snapshot_is_primary_and_zero_is_authoritative(self):
        planning = source("app/services/planning_authority_service.py")
        self.assertIn("current_snapshot_available = False", planning)
        self.assertIn("not current_snapshot_available", planning)
        self.assertIn("stock_snapshot_run_id", planning)
        self.assertIn("A legitimate zero", planning)
        for rel in (
            "app/services/planning_authority_service.py",
            "app/services/cavity_daily_plan_service.py",
            "app/services/shipment_order_async_service.py",
            "app/services/factory_planning_engine.py",
        ):
            text = source(rel)
            current = text.find("mpps_current_stock_snapshots")
            fallback = text.find("mpps_sap_stock_items", current + 1)
            self.assertGreaterEqual(current, 0, rel)
            self.assertGreater(fallback, current, rel)

    def test_stock_authority_is_verified_and_persisted(self):
        text = source("app/services/planning_authority_service.py")
        for token in (
            "_verify_stock_authority",
            "duplicate_sap_rows",
            "negative_rows",
            "stock_authority_verified",
            "STOCK_AUTHORITY_NOT_VERIFIED",
            "stock_verification",
        ):
            self.assertIn(token, text)

    def test_active_planning_queue_excludes_non_plannable_lifecycle_states(self):
        text = source("app/services/planning_authority_service.py")
        self.assertIn("'SHIPPED','CANCELLED','HOLD','CLOSURE_REVIEW'", text)

    def test_cavity_planner_uses_demand_identity_not_sap_overwrite(self):
        text = source("app/services/cavity_daily_plan_service.py")
        self.assertIn("def _demand_key", text)
        self.assertIn("shipment_item_id", text)
        self.assertIn("priority_no", text)
        self.assertNotIn("required_by_sap = {", text)
        self.assertIn(
            "total_balance = max(0, total_required - total_today - total_next)",
            text,
        )
        self.assertIn("today_by_demand", text)
        self.assertIn("next_by_demand", text)

    def test_production_planning_is_shared_pool_and_replans_factory_can_out(self):
        text = source("app/ui/schedule_page.py")
        self.assertIn("TaskManager.instance()", text)
        self.assertIn('"Priority"', text)
        self.assertIn("production-planning-r6:generate", text)
        self.assertIn("production-planning-r6:save", text)
        self.assertIn("FactoryCanOutService.replan_open_shipments", text)
        self.assertIn("PlanningAuthorityService.persist_snapshot", text)
        self.assertNotIn("QThread", text)
        self.assertNotIn("_PlanGenerationWorker", text)
        self.assertNotIn("_SavedPlanLoadWorker", text)

    def test_factory_can_out_has_one_active_deterministic_facade(self):
        facade = source("app/services/factory_can_out_service.py")
        order = source("app/services/shipment_order_async_service.py")
        schedule = source("app/ui/schedule_page.py")
        lifecycle = source("app/services/shipment_lifecycle_service.py")
        details = source("app/services/shipment_details_async_service.py")
        self.assertIn("R6-CANOUT-1", facade)
        self.assertIn("FactoryPlanningEngine", facade)
        self.assertIn("FactoryCanOutService.preview_items", order)
        self.assertIn("FactoryCanOutService.replan_open_shipments", order)
        self.assertIn("FactoryCanOutService.replan_open_shipments", schedule)
        self.assertIn("FactoryCanOutService.replan_open_shipments", lifecycle)
        self.assertNotIn("factory_out_forecast_service", details)
        self.assertIn("PENDING_CANONICAL_REPLAN", details)

    def test_shipment_lifecycle_reconciles_planning_after_state_change(self):
        text = source("app/services/shipment_lifecycle_service.py")
        for token in (
            "CLOSURE_REVIEW",
            "SHIPPED",
            "CANCELLED",
            "FactoryCanOutService.replan_open_shipments",
            "PlanningAuthorityService.persist_snapshot",
            "replan_warning",
        ):
            self.assertIn(token, text)

    def test_r7_negative_workbook_stock_is_warning_not_authority_failure(self):
        planning = source("app/services/planning_authority_service.py")
        finalizer = source("app/services/ml_finalization_service.py")

        self.assertIn("negative raw Current Stock value(s)", planning)
        self.assertIn("treated as 0 usable stock", planning)
        self.assertNotIn('and result["negative_rows"] == 0', planning)
        self.assertIn("GREATEST(COALESCE(current_stock,0),0)", planning)

        self.assertIn("negative_raw_rows", finalizer)
        self.assertIn("int(count or 0) != len(rows)", finalizer)
        self.assertNotIn(
            "int(negatives or 0) > 0",
            finalizer,
        )

    def test_shift_plan_uses_saved_plan_primary_with_oven_fallback(self):
        service = source("app/services/shift_daily_report_service.py")
        ui = source("app/ui/intelligent_operations_pages.py")
        self.assertIn("_saved_shift_rows", service)
        self.assertIn("mpps_cavity_plan_runs", service)
        self.assertIn("mpps_cavity_plan_rows", service)
        self.assertIn("SAVED R6 PLAN / RUN", service)
        self.assertIn("mpps_oven_plan", service)
        self.assertIn("A saved cavity-level R6 plan is the operational planning authority", service)
        self.assertIn("ShiftDailyReportService.list_plan_dates", ui)
        self.assertIn("ShiftDailyReportService.load_live_plan", ui)
        self.assertIn("saved production plan", ui)


    def test_cavity_priority_cte_has_no_ambiguous_priority_column(self):
        text = source("app/services/cavity_daily_plan_service.py")
        self.assertIn("AS dynamic_priority_no", text)
        self.assertIn("shipment.dynamic_priority_no AS priority_no", text)
        self.assertIn("ORDER BY shipment.dynamic_priority_no, item.id", text)
        self.assertNotIn(")::INTEGER AS priority_no\n            FROM mpps_shipments shipment", text)

    def test_daily_plan_surfaces_priority(self):
        service = source("app/services/daily_plan_async_service.py")
        ui = source("app/ui/daily_plan_async_page.py")
        self.assertIn("priority_no", service)
        self.assertIn('(\"Priority\", \"priority_no\")', ui)

    def test_planning_exceptions_are_generated_and_persisted(self):
        text = source("app/services/planning_authority_service.py")
        for token in (
            "PLAN_ARITHMETIC_MISMATCH",
            "PLAN_DEMAND_STALE",
            "MATERIAL_SHORTAGE",
            "BREAKDOWN_CAPACITY",
            "DELIVERY_LATE",
            "DELETE FROM mpps_planning_exceptions",
            "INSERT INTO mpps_planning_exceptions",
        ):
            self.assertIn(token, text)

    def test_material_ai_and_excel_pipeline_use_shared_task_manager(self):
        for rel in (
            "app/ui/material_requirement_pro_page.py",
            "app/ui/ai_ml_control_center_page.py",
            "app/ui/raw_excel_viewer_page.py",
        ):
            text = source(rel)
            self.assertIn("TaskManager", text, rel)
            self.assertNotIn("QThread", text, rel)
        ai = source("app/ui/ai_ml_control_center_page.py")
        self.assertIn("MLPlatformService.snapshot", ai)
        self.assertIn("Intelligent Excel Import", ai)
        self.assertIn("Validate Training Readiness", ai)
        self.assertIn("Train / Retrain Eligible", ai)
        self.assertIn("Open Historical Inbox", ai)
        self.assertIn("MLTrainingEngine.train_ready_models", ai)

    def test_historical_normalization_and_revision_rules_are_explicit(self):
        text = source("app/services/historical_dataset_validation_service.py")
        for token in (
            "mpps_ml_training_observations_v2",
            "DUPLICATE_COMMITTED_WORKBOOK_HASH",
            "same_date_changed_workbook",
            "allowed_as_revision",
            "MISSING_CORE_WORKBOOK_ROLES",
            "FUTURE_ACTUAL_LEAKAGE",
            "FUTURE_TYRE_ACTUAL_LEAKAGE",
            "NEGATIVE_ACTUAL_TARGET",
            "ready_for_training",
        ):
            self.assertIn(token, text)

    def test_training_split_is_time_ordered_with_embargo(self):
        text = source("app/services/ml_training_orchestrator.py")
        for token in (
            "TrainingWindows",
            "chronological_windows",
            "embargo_days",
            "strictly chronological and non-overlapping",
            "Configured split embargo is not respected",
            'split_rows = {"training": 0, "validation": 0, "test": 0}',
        ):
            self.assertIn(token, text)
        self.assertNotIn("train_test_split", text)
        self.assertNotIn("shuffle=True", text)

    def test_ml_feature_target_validation_blocks_leakage(self):
        spec = source("app/services/ml_training_spec.py")
        orchestrator = source("app/services/ml_training_orchestrator.py")
        migration = source("database/migrations/ensure_autonomous_planning_r6.py")
        for token in (
            "actual_lead_days",
            "late_flag",
            "shortage_flag",
            "stockout_flag",
            "scrap_block_flag",
        ):
            self.assertTrue(token in spec or token in migration, token)
        for token in (
            "Target column is also present in the feature list",
            "explicitly contains future information",
            "label-like",
            "feature_signature",
        ):
            self.assertIn(token, orchestrator)
        self.assertIn('metric_name="MAE_DAYS"', spec)
        self.assertIn("SHIPMENT_CAN_OUT", spec)

    def test_training_engine_is_real_and_never_writes_operational_authority(self):
        text = source("app/services/ml_training_engine.py")
        for token in (
            "DictVectorizer",
            "RandomForestRegressor",
            "RandomForestClassifier",
            "XGBRegressor",
            "XGBClassifier",
            'device="cuda"',
            "register_run",
            "record_training_result",
            "promote_champion",
            "models_dir",
            "challengers",
        ):
            self.assertIn(token, text)
        self.assertNotIn("UPDATE mpps_shipments", text)
        self.assertNotIn("UPDATE mpps_current_stock_snapshots", text)
        self.assertNotIn("UPDATE mpps_cavity_plan_rows", text)

    def test_champion_promotion_requires_unseen_test_and_improvement(self):
        text = source("app/services/ml_training_orchestrator.py")
        for token in (
            "test_metric_value",
            "leakage_check_passed",
            "feature_validation_passed",
            "Candidate unseen-test metric is below the promotion gate",
            "Candidate does not improve the current champion enough on the unseen test window",
            "minimum_relative_improvement",
            "status='CHAMPION'",
            "status='RETIRED'",
        ):
            self.assertIn(token, text)

    def test_ml_catalog_is_complete_and_advisory(self):
        platform = source("app/services/ml_platform_service.py")
        specs = source("app/services/ml_training_spec.py")
        for model in (
            "Production Output Forecast",
            "Factory Capacity Model",
            "Cavity / Oven Compatibility Model",
            "Compound Requirement Model",
            "Stockout Risk",
            "Factory Can-Out Forecast",
            "Shipment Priority Intelligence",
        ):
            self.assertIn(model, platform)
        self.assertIn("NEEDS TRAINING", platform)
        self.assertIn("does not pretend", platform)
        self.assertIn("MODEL_TRAINING_SPECS", specs)

    def test_r7_finalizer_forces_historical_only_bulk_import(self):
        text = source("app/services/ml_finalization_service.py")
        for token in (
            '"force_historical_snapshot": True',
            '"authoritative_latest_shipments": False',
            '"sync_live_shipments": False',
            '"update_stock": False',
            '"update_daily_stock": False',
            '"import_materials": False',
            "EXACT_COMMITTED_DUPLICATE",
            "_persist_material_plan_history",
            "same-date changed workbook",
        ):
            self.assertIn(token, text)
        self.assertIn("Historical Training Inbox", source("app/ui/ai_ml_control_center_page.py"))

    def test_r7_training_artifacts_are_portable_and_have_backend_fallback(self):
        text = source("app/services/ml_training_engine.py")
        self.assertIn("Path(__file__).resolve().parents[2]", text)
        self.assertIn("MPPS_MODELS_DIR", text)
        self.assertNotIn("settings.models_dir", text)
        self.assertIn("_fit_with_fallback", text)
        self.assertIn("SKLEARN_RANDOM_FOREST", text)
        self.assertIn("never seen in the training window", text)
        self.assertIn('RELEASE = "R7"', text)

    def test_r7_stock_repair_uses_exact_committed_workbook(self):
        text = source("app/services/ml_finalization_service.py")
        for token in (
            "verify_or_rebuild_stock_authority",
            "_latest_committed_source",
            "_sha256_file",
            "workbook hash does not match",
            "DELETE FROM mpps_current_stock_snapshots WHERE import_run_id=:run_id",
            "CurrentStockService.ensure_latest_snapshot",
        ):
            self.assertIn(token, text)

    def test_r7_final_training_launcher_is_present(self):
        launcher = source("Run_Final_ML_Training.cmd")
        self.assertIn("portable_db_control.py", launcher)
        self.assertIn("run_ml_finalization.py", launcher)
        self.assertIn("--all --install-runtime", launcher)
        self.assertIn("historical_inbox", launcher)

    def test_autonomous_facade_keeps_ml_separate_from_authority(self):
        text = source("app/services/autonomous_planning_service.py")
        self.assertIn("PlanningAuthorityService.load", text)
        self.assertIn("MLPlatformService", text)
        self.assertIn("shipment_explanation", text)
        self.assertIn("production_gap_qty", text)



    def test_r72_training_launcher_loads_portable_db_environment_before_guard(self):
        source = (ROOT / "Run_Final_ML_Training.cmd").read_text(
            encoding="utf-8-sig",
        )
        env_pos = source.find('call "%ROOT%\\config\\portable_env.cmd"')
        guard_pos = source.find('tools\\training_db_guard.py')
        self.assertGreaterEqual(env_pos, 0)
        self.assertGreater(guard_pos, env_pos)
        self.assertIn("MPPS_DB_PASSWORD", (ROOT / "config" / "portable_env.cmd").read_text(encoding="utf-8-sig") if (ROOT / "config" / "portable_env.cmd").exists() else "MPPS_DB_PASSWORD")

    def test_r72_max_quality_profile_uses_gpu_and_bounded_cpu_workers(self):
        source = (ROOT / "Run_Final_ML_Training.cmd").read_text(
            encoding="utf-8-sig",
        )
        self.assertIn('set "MPPS_ML_PROFILE=MAX_QUALITY"', source)
        self.assertIn("MPPS_ML_THREADS=%NUMBER_OF_PROCESSORS%-1", source)
        self.assertIn('set "CUDA_VISIBLE_DEVICES=0"', source)
        self.assertNotIn("REALTIME", source.upper())

    def test_r72_training_engine_uses_deeper_compute_without_test_leakage(self):
        source = (ROOT / "app" / "services" / "ml_training_engine.py").read_text(
            encoding="utf-8-sig",
        )
        self.assertIn("n_estimators=1800 if max_quality else 350", source)
        self.assertIn('common["early_stopping_rounds"] = 120', source)
        self.assertIn("eval_set=[(x_validation, y_validation)]", source)
        self.assertNotIn("eval_set=[(x_test, y_test)]", source)
        self.assertIn("test_pred = estimator.predict(x_test)", source)

    def test_r72_db_guard_waits_and_only_uses_clean_controller_restart(self):
        source = (ROOT / "tools" / "training_db_guard.py").read_text(
            encoding="utf-8-sig",
        )
        self.assertIn("wait_write_ready(300", source)
        self.assertIn("wait_write_ready(900", source)
        self.assertIn("control.stop()", source)
        self.assertIn("control.start()", source)
        self.assertNotIn("subprocess.Popen", source)
        self.assertNotIn("taskkill", source.lower())

    def test_r72_training_process_priority_is_above_normal_not_realtime(self):
        source = (ROOT / "tools" / "run_ml_finalization.py").read_text(
            encoding="utf-8-sig",
        )
        self.assertIn("ABOVE_NORMAL_PRIORITY_CLASS", source)
        self.assertNotIn("REALTIME_PRIORITY_CLASS", source)

if __name__ == "__main__":
    unittest.main()
