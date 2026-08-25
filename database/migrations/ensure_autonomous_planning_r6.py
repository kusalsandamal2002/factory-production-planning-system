from __future__ import annotations

from sqlalchemy import text

from app.database import engine


STATEMENTS = (
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS priority_no INTEGER
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS priority_reason TEXT NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS priority_updated_at TIMESTAMP
    """,
    """
    DO $$
    BEGIN
        IF to_regclass('public.mpps_cavity_plan_rows') IS NOT NULL THEN
            ALTER TABLE mpps_cavity_plan_rows
            ADD COLUMN IF NOT EXISTS priority_no INTEGER;
        END IF;
    END $$
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_autonomous_planning_state (
        id INTEGER PRIMARY KEY,
        architecture_version VARCHAR(40) NOT NULL DEFAULT 'MPPS-R6',
        planning_mode VARCHAR(32) NOT NULL DEFAULT 'ASSISTED_AUTO',
        excel_dependency_stage VARCHAR(32) NOT NULL DEFAULT 'HYBRID_AUTHORITY',
        last_source_date DATE,
        last_snapshot_id BIGINT,
        last_reconciled_at TIMESTAMP,
        last_optimizer_run_at TIMESTAMP,
        last_training_run_at TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    INSERT INTO mpps_autonomous_planning_state(id)
    VALUES (1)
    ON CONFLICT (id) DO NOTHING
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_planning_snapshots (
        id BIGSERIAL PRIMARY KEY,
        snapshot_key VARCHAR(160) NOT NULL UNIQUE,
        snapshot_date DATE NOT NULL,
        source_date DATE,
        source_workbook TEXT NOT NULL DEFAULT '',
        shipment_count INTEGER NOT NULL DEFAULT 0,
        shipment_qty INTEGER NOT NULL DEFAULT 0,
        stock_covered_qty INTEGER NOT NULL DEFAULT 0,
        production_gap_qty INTEGER NOT NULL DEFAULT 0,
        fg_stock_qty INTEGER NOT NULL DEFAULT 0,
        planned_today_qty INTEGER NOT NULL DEFAULT 0,
        planned_next_day_qty INTEGER NOT NULL DEFAULT 0,
        unscheduled_qty INTEGER NOT NULL DEFAULT 0,
        active_cavities INTEGER NOT NULL DEFAULT 0,
        breakdown_cavities INTEGER NOT NULL DEFAULT 0,
        estimated_daily_capacity_qty INTEGER NOT NULL DEFAULT 0,
        material_exception_count INTEGER NOT NULL DEFAULT 0,
        reconciliation_ok BOOLEAN NOT NULL DEFAULT FALSE,
        reconciliation_note TEXT NOT NULL DEFAULT '',
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_planning_snapshot_items (
        id BIGSERIAL PRIMARY KEY,
        snapshot_id BIGINT NOT NULL REFERENCES mpps_planning_snapshots(id) ON DELETE CASCADE,
        shipment_id INTEGER,
        shipment_item_id INTEGER,
        priority_no INTEGER,
        shipment_name TEXT NOT NULL DEFAULT '',
        sap_code TEXT NOT NULL DEFAULT '',
        item_description TEXT NOT NULL DEFAULT '',
        target_date DATE,
        factory_can_out_date DATE,
        demand_qty INTEGER NOT NULL DEFAULT 0,
        produced_qty INTEGER NOT NULL DEFAULT 0,
        stock_covered_qty INTEGER NOT NULL DEFAULT 0,
        production_gap_qty INTEGER NOT NULL DEFAULT 0,
        operational_status VARCHAR(40) NOT NULL DEFAULT '',
        explanation TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(snapshot_id, shipment_item_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_planning_exceptions (
        id BIGSERIAL PRIMARY KEY,
        snapshot_id BIGINT REFERENCES mpps_planning_snapshots(id) ON DELETE CASCADE,
        entity_type VARCHAR(40) NOT NULL DEFAULT '',
        entity_id TEXT NOT NULL DEFAULT '',
        exception_code VARCHAR(80) NOT NULL,
        severity VARCHAR(20) NOT NULL DEFAULT 'WARNING',
        message TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_ml_model_registry_v2 (
        model_key VARCHAR(120) PRIMARY KEY,
        area VARCHAR(80) NOT NULL,
        model_name VARCHAR(180) NOT NULL,
        model_role VARCHAR(40) NOT NULL DEFAULT 'ADVISORY',
        status VARCHAR(32) NOT NULL DEFAULT 'REGISTERED',
        training_rows BIGINT NOT NULL DEFAULT 0,
        history_days INTEGER NOT NULL DEFAULT 0,
        validation_metric VARCHAR(40) NOT NULL DEFAULT '',
        validation_score NUMERIC(14,6),
        confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0,
        model_version VARCHAR(80) NOT NULL DEFAULT 'R6-UNTRAINED',
        champion BOOLEAN NOT NULL DEFAULT FALSE,
        last_trained_at TIMESTAMP,
        last_data_update TIMESTAMP,
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_ml_training_runs_v2 (
        id BIGSERIAL PRIMARY KEY,
        run_key VARCHAR(120) NOT NULL UNIQUE,
        model_key VARCHAR(120) NOT NULL REFERENCES mpps_ml_model_registry_v2(model_key),
        status VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
        train_start_date DATE,
        train_end_date DATE,
        validation_start_date DATE,
        validation_end_date DATE,
        test_start_date DATE,
        test_end_date DATE,
        training_rows BIGINT NOT NULL DEFAULT 0,
        validation_rows BIGINT NOT NULL DEFAULT 0,
        test_rows BIGINT NOT NULL DEFAULT 0,
        metric_name VARCHAR(40) NOT NULL DEFAULT '',
        metric_value NUMERIC(14,6),
        artifact_path TEXT NOT NULL DEFAULT '',
        message TEXT NOT NULL DEFAULT '',
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_ml_prediction_audit_v2 (
        id BIGSERIAL PRIMARY KEY,
        model_key VARCHAR(120) NOT NULL,
        prediction_date DATE,
        entity_type VARCHAR(40) NOT NULL DEFAULT '',
        entity_key TEXT NOT NULL DEFAULT '',
        prediction_value NUMERIC(18,6),
        confidence_score NUMERIC(10,6),
        actual_value NUMERIC(18,6),
        features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        explanation TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_operational_actual_events (
        id BIGSERIAL PRIMARY KEY,
        event_date DATE NOT NULL,
        shift_name VARCHAR(40) NOT NULL DEFAULT '',
        sap_code VARCHAR(120) NOT NULL DEFAULT '',
        line_name VARCHAR(180) NOT NULL DEFAULT '',
        cavity_no VARCHAR(120) NOT NULL DEFAULT '',
        produced_qty INTEGER NOT NULL DEFAULT 0,
        scrap_qty INTEGER NOT NULL DEFAULT 0,
        blocked_qty INTEGER NOT NULL DEFAULT 0,
        source VARCHAR(40) NOT NULL DEFAULT 'APP',
        source_ref TEXT NOT NULL DEFAULT '',
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_shipments_r6_priority
    ON mpps_shipments(priority_no, target_date, created_at, id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_shipment_items_r6_open
    ON mpps_shipment_items(shipment_id, sap_code, id)
    """,
    """
    DO $$
    BEGIN
        IF to_regclass('public.mpps_cavity_plan_rows') IS NOT NULL THEN
            CREATE INDEX IF NOT EXISTS ix_mpps_cavity_plan_rows_r6_priority
            ON mpps_cavity_plan_rows(plan_date, priority_no, shipment_id, shipment_item_id);
        END IF;
    END $$
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_planning_snapshot_items_priority
    ON mpps_planning_snapshot_items(snapshot_id, priority_no, shipment_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_planning_exceptions_snapshot
    ON mpps_planning_exceptions(snapshot_id, severity, exception_code)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_ml_prediction_audit_v2_lookup
    ON mpps_ml_prediction_audit_v2(model_key, prediction_date, entity_key)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_operational_actual_events_date_sap
    ON mpps_operational_actual_events(event_date, sap_code, shift_name)
    """,    """
    CREATE TABLE IF NOT EXISTS mpps_ml_training_observations_v2 (
        id BIGSERIAL PRIMARY KEY,
        observation_key VARCHAR(160) NOT NULL UNIQUE,
        observation_date DATE NOT NULL,
        entity_type VARCHAR(40) NOT NULL,
        entity_key TEXT NOT NULL,
        source_table VARCHAR(120) NOT NULL,
        source_row_key TEXT NOT NULL DEFAULT '',
        features_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        targets_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_hash VARCHAR(64) NOT NULL DEFAULT '',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_ml_training_obs_date_entity
    ON mpps_ml_training_observations_v2(
        observation_date, entity_type, entity_key
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_ml_training_obs_source
    ON mpps_ml_training_observations_v2(source_table, observation_date)
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_training_data_validation_runs (
        id BIGSERIAL PRIMARY KEY,
        run_key VARCHAR(120) NOT NULL UNIQUE,
        status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
        first_date DATE,
        last_date DATE,
        history_days INTEGER NOT NULL DEFAULT 0,
        observation_days INTEGER NOT NULL DEFAULT 0,
        total_rows BIGINT NOT NULL DEFAULT 0,
        critical_issue_count INTEGER NOT NULL DEFAULT 0,
        warning_count INTEGER NOT NULL DEFAULT 0,
        ready_for_training BOOLEAN NOT NULL DEFAULT FALSE,
        report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_training_data_validation_issues (
        id BIGSERIAL PRIMARY KEY,
        validation_run_id BIGINT NOT NULL
            REFERENCES mpps_training_data_validation_runs(id)
            ON DELETE CASCADE,
        severity VARCHAR(20) NOT NULL,
        issue_code VARCHAR(80) NOT NULL,
        source_name VARCHAR(120) NOT NULL DEFAULT '',
        message TEXT NOT NULL,
        detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_training_validation_issues
    ON mpps_training_data_validation_issues(
        validation_run_id, severity, issue_code
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mpps_ml_model_versions_v2 (
        id BIGSERIAL PRIMARY KEY,
        model_key VARCHAR(120) NOT NULL
            REFERENCES mpps_ml_model_registry_v2(model_key),
        model_version VARCHAR(80) NOT NULL,
        run_key VARCHAR(120),
        status VARCHAR(32) NOT NULL DEFAULT 'CANDIDATE',
        metric_name VARCHAR(40) NOT NULL DEFAULT '',
        validation_score NUMERIC(14,6),
        test_score NUMERIC(14,6),
        confidence_score NUMERIC(10,6) NOT NULL DEFAULT 0,
        artifact_path TEXT NOT NULL DEFAULT '',
        feature_signature VARCHAR(64) NOT NULL DEFAULT '',
        dataset_signature VARCHAR(64) NOT NULL DEFAULT '',
        leakage_check_passed BOOLEAN NOT NULL DEFAULT FALSE,
        feature_validation_passed BOOLEAN NOT NULL DEFAULT FALSE,
        promoted_at TIMESTAMP,
        retired_at TIMESTAMP,
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(model_key, model_version)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_ml_model_versions_lookup
    ON mpps_ml_model_versions_v2(model_key, status, created_at DESC)
    """,
    """
    ALTER TABLE mpps_ml_training_runs_v2
    ADD COLUMN IF NOT EXISTS test_metric_value NUMERIC(14,6)
    """,
    """
    ALTER TABLE mpps_ml_training_runs_v2
    ADD COLUMN IF NOT EXISTS leakage_check_passed BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE mpps_ml_training_runs_v2
    ADD COLUMN IF NOT EXISTS feature_validation_passed BOOLEAN NOT NULL DEFAULT FALSE
    """,
    """
    ALTER TABLE mpps_ml_training_runs_v2
    ADD COLUMN IF NOT EXISTS dataset_signature VARCHAR(64) NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE mpps_ml_training_runs_v2
    ADD COLUMN IF NOT EXISTS feature_signature VARCHAR(64) NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE mpps_ml_training_runs_v2
    ADD COLUMN IF NOT EXISTS validation_report_json JSONB NOT NULL DEFAULT '{}'::jsonb
    """,
    """
    DO $$
    BEGIN
        IF to_regclass('public.mpps_tyre_workbook_observation') IS NOT NULL THEN
            EXECUTE $view$
                CREATE OR REPLACE VIEW mpps_tyre_training_view AS
                SELECT
                    id, plan_date, sap_code, description, line, oven_no,
                    heel, soft, tread, weight_kg, day_plan, night_plan,
                    day_produced, night_produced, next_day_plan, total_to_produce,
                    today_qty, total_stock, current_stock, scrap, blocked,
                    (COALESCE(day_plan,0)+COALESCE(night_plan,0))::NUMERIC AS plan_qty,
                    (COALESCE(day_produced,0)+COALESCE(night_produced,0))::NUMERIC AS actual_qty,
                    GREATEST(COALESCE(total_to_produce,0)-COALESCE(today_qty,0),0)::NUMERIC AS production_gap_qty,
                    CASE WHEN COALESCE(current_stock,0)<=0 AND COALESCE(total_to_produce,0)>0 THEN 1 ELSE 0 END::INTEGER AS stockout_flag,
                    CASE WHEN COALESCE(scrap,0)>0 OR COALESCE(blocked,0)>0 THEN 1 ELSE 0 END::INTEGER AS scrap_block_flag,
                    CASE
                        WHEN (COALESCE(day_plan,0)+COALESCE(night_plan,0))>0
                         AND (COALESCE(day_produced,0)+COALESCE(night_produced,0))
                             < (COALESCE(day_plan,0)+COALESCE(night_plan,0))*0.80
                        THEN 1 ELSE 0
                    END::INTEGER AS underperformance_flag
                FROM mpps_tyre_workbook_observation
                WHERE plan_date IS NOT NULL
            $view$;
        END IF;
    END $$
    """,
    """
    DO $$
    BEGIN
        IF to_regclass('public.excel_import_material_plans') IS NOT NULL THEN
            EXECUTE $view$
                CREATE OR REPLACE VIEW mpps_material_training_view AS
                SELECT
                    id, plan_date, material_type, material_key, unit,
                    day_qty, night_qty, produced_qty, stock_qty, total_qty, next_day_qty,
                    GREATEST(COALESCE(total_qty,0)-COALESCE(stock_qty,0)-COALESCE(produced_qty,0),0)::NUMERIC AS shortage_qty,
                    CASE
                        WHEN GREATEST(COALESCE(total_qty,0)-COALESCE(stock_qty,0)-COALESCE(produced_qty,0),0)>0
                        THEN 1 ELSE 0
                    END::INTEGER AS shortage_flag,
                    ABS(COALESCE(total_qty,0)-COALESCE(day_qty,0)-COALESCE(night_qty,0))::NUMERIC AS plan_variance_qty
                FROM excel_import_material_plans
                WHERE plan_date IS NOT NULL
            $view$;
        END IF;
    END $$
    """,
    """
    DO $$
    BEGIN
        IF to_regclass('public.mpps_planning_snapshot_items') IS NOT NULL
           AND to_regclass('public.mpps_planning_snapshots') IS NOT NULL
           AND to_regclass('public.mpps_shipments') IS NOT NULL THEN
            EXECUTE $view$
                CREATE OR REPLACE VIEW mpps_shipment_training_view AS
                SELECT
                    i.id AS snapshot_item_id,
                    s.snapshot_date,
                    i.shipment_id, i.shipment_item_id, i.priority_no,
                    i.shipment_name, i.sap_code, i.item_description,
                    i.target_date, i.factory_can_out_date AS planned_factory_can_out_date,
                    i.demand_qty, i.produced_qty, i.stock_covered_qty, i.production_gap_qty,
                    i.operational_status,
                    sh.actual_factory_out_date,
                    CASE
                        WHEN sh.actual_factory_out_date IS NOT NULL
                        THEN (sh.actual_factory_out_date-s.snapshot_date)
                        ELSE NULL
                    END::INTEGER AS actual_lead_days,
                    CASE
                        WHEN sh.actual_factory_out_date IS NOT NULL AND i.target_date IS NOT NULL
                        THEN (sh.actual_factory_out_date-i.target_date)
                        ELSE NULL
                    END::INTEGER AS delivery_variance_days,
                    CASE
                        WHEN sh.actual_factory_out_date IS NOT NULL AND i.target_date IS NOT NULL
                         AND sh.actual_factory_out_date>i.target_date
                        THEN 1 ELSE 0
                    END::INTEGER AS late_flag,
                    CASE
                        WHEN COALESCE(i.demand_qty,0)>0
                        THEN (COALESCE(i.stock_covered_qty,0)::NUMERIC/NULLIF(i.demand_qty,0))
                        ELSE 0
                    END::NUMERIC AS stock_coverage_ratio
                FROM mpps_planning_snapshot_items i
                JOIN mpps_planning_snapshots s ON s.id=i.snapshot_id
                JOIN mpps_shipments sh ON sh.id=i.shipment_id
                WHERE s.snapshot_date IS NOT NULL
            $view$;
        END IF;
    END $$
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_mpps_ml_training_runs_model_status
    ON mpps_ml_training_runs_v2(model_key, status, created_at DESC)
    """,
)


def main() -> None:
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout='5s'"))
        connection.execute(text("SET LOCAL statement_timeout='90s'"))
        for statement in STATEMENTS:
            connection.execute(text(statement))
    print("MPPS R6 autonomous planning schema ready.")


if __name__ == "__main__":
    main()
