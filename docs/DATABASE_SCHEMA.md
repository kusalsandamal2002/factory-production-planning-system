# Database Schema

## Core Planning Tables

### `mpps_shipments`
Stores the shipment header and planning result summary.
- `target_date`: optional requested due date
- `plan_date`: planning date used by the UI
- `factory_can_receive_date`: latest calculated item receive date
- `factory_out_date`: legacy-compatible outbound date field
- `delivery_status`: on time / early / delayed / flexible
- `delay_days`, `early_days`: schedule delta in days
- `total_qty`, `completed_qty`, `progress_pct`: shipment progress summary
- `planning_status`, `planning_note`: planner output and explanation
- `planning_version`, `last_replanned_at`: audit trail fields

### `mpps_shipment_items`
Stores item-level shipment demand and planning results.
- `stock_allocated_qty`
- `produced_qty`
- `completed_qty`
- `production_required_qty`
- `remaining_qty`
- `allocated_cavity_count`
- `daily_capacity`
- `production_days`
- `item_receive_date`
- `receive_date`
- `progress_pct`
- `item_status`
- `schedule_reason`
- `factory_out_reason`

### `planning_runs`
Stores each planning execution.
- run start and finish time
- trigger reason
- planning version
- status and message

### `planning_resource_reservations`
Stores per-day reservations for molds, casings, and line cavities.
- `reservation_date`
- `resource_type`
- `resource_key`
- `reserved_qty`
- `capacity_qty`
- `sap_code`

### `shipment_stock_allocations`
Stores stock allocation results tied to a planning run.

## Upgrade Behavior
The schema upgrade routines are idempotent and use `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... IF NOT EXISTS` patterns where possible. Where PostgreSQL needs stronger DDL changes, the code now uses bounded timeouts so the app fails fast with a clearer error instead of hanging on locks.
