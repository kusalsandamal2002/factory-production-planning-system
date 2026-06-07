# Old Logic Removal Report

## Scope

This report records the removal of the prototype minute-based scheduler from
the visible application. No database tables or source workbooks were deleted.
Legacy schema classes remain available for compatibility, but the current UI
does not import or execute the retired scheduling services.

## Findings and Actions

| File or area | Old logic found | Runtime-used before change | Decision | Safe action taken |
|---|---|---:|---|---|
| `app/ui/dashboard_page.py` | Planned minutes, available minutes, slot count, shift-minute utilization, legacy order metrics | Yes | Update | Replaced with selected-date planned quantity, quantity capacity, capacity usage, active compatible ovens, plan status, production requirement, and warning metrics. |
| `app/ui/order_entry_page.py` | Tire-type search, curing minutes, live Company Can Receive Date, minute scheduler preview, legacy order confirmation | Yes | Replace | Rebuilt as a read-only MPPS shipment-demand register. It no longer imports the scheduler or order service. |
| `app/ui/details/shipment_details_page.py` and legacy shipment tabs | System Can Receive, manager-confirmed receive date, legacy `orders` records | Yes | Replace/archive | Main page now shows MPPS shipment demand. Five dependent legacy order tabs were moved to the archive. |
| `app/ui/tire_stock_page.py` | Stock calculated from `tire_stock_movements` and tire types; destructive movement deletion | Yes | Replace | Rebuilt as a read-only `mpps_stock_items` view showing FG, QC, scrap, blocked, available stock, and status. |
| `app/ui/login_window.py` | "25 Ovens", "2 Shifts", and live receive-date marketing text | Yes | Update | Replaced with MPPS stock, quantity capacity, and Excel traceability wording. |
| `app/ui/main_window.py` | Visible Daily Production Entry and Tire Details/production-time navigation | Yes | Update | Removed those navigation entries and imports. Their stack positions use isolated placeholders only, preserving index compatibility. |
| `app/ui/schedule_page.py` | Some generic planned/unplanned labels | Yes | Update | Kept the quantity service and renamed metrics/columns to selected-date planned quantity and remaining quantity after selected date. |
| `app/services/oven_schedule_service.py` | No old slot scheduler, but active oven count included every active oven | Yes | Update | Kept quantity/mould/day logic. Active ovens now count active ovens observed in `mpps_oven_plan`; the required no-cycle-time note is shown. |
| `app/services/production_requirement_service.py` | Combined MPPS demand with legacy orders and read legacy tire movements | Yes | Update | Current production requirement now uses `mpps_shipment_demand` and `mpps_stock_items` only. |
| `app/services/shipment_risk_service.py` | Combined MPPS demand with legacy orders | Yes | Update | Shipment risk now allocates only current MPPS shipment-demand rows. |
| `app/services/stock_planning_service.py` | Item demand breakdown included legacy orders | Not in the current main navigation path | Update | Removed the old order query so future item details use MPPS shipment demand only. |
| `app/ui/product_master_page.py` | Created/updated `tire_types` with a hard-coded 30-minute curing value | Yes through Factory Data Center | Update | Product saves now write only `mpps_stock_items`; no curing-time record is created. |
| `app/ui/capacity_master_page.py` | "Mould curing production capacity" wording | Yes | Update | Reworded as mould/category production capacity. |
| `app/seed_data.py` | Seeded Tire Type 1-5, 25 ovens, fixed shifts, and a 20-minute break rule | Yes at startup | Update | Fresh-start seeding now creates development roles/users only. Existing database rows were not changed or deleted. |
| `app/services/scheduler.py` | Minute slots, curing duration, breaks, shift windows, receive-date preview | Only through old order entry | Archive | Moved to `backups/code_backups/legacy_minute_scheduler/services/`. |
| `app/services/schedule_priority_service.py` | Priority-based destructive schedule rebuild using curing/break minutes | No after UI replacement | Archive | Moved to the legacy archive. |
| `app/services/order_service.py` | Company Can Receive Date and writing legacy `oven_schedule` slots | No after UI replacement | Archive | Moved to the legacy archive. |
| `app/services/tire_stock_service.py` | Legacy tire movement stock and movement deletion | No after stock-page replacement | Archive | Moved to the legacy archive. |
| `app/ui/production_entry_page.py` | Legacy tire movement mapping and day/night text entry | No after navigation removal | Archive | Moved to the legacy archive. |
| `app/ui/details/tire_*`, `machine_details_page.py`, `table_page_base.py` | Tire-type and curing-time master UI | No after navigation removal | Archive | Moved as a dependency-complete UI group to the legacy archive. |
| `app/models.py` | Legacy tire, shift, production-rule, order, and `oven_schedule` schema classes | Yes during metadata initialization | Keep | Retained to avoid schema deletion or compatibility breakage. Current visible planning does not query these classes. |
| `app/ui/backup_restore_page.py` | Includes `oven_schedule` in backup inventory | Yes | Keep | Backup coverage is not scheduling logic; retaining it protects existing legacy records. |
| `tools/importers/` and `database/migrations/` | Historical mappings/schema for legacy tables | Manual tools only | Keep | Retained for reproducibility and migration history. They are not imported by the app. |
| Planning documentation | References minute planning as unsupported or historical | Documentation only | Keep/update | Kept factual data-gap explanations and updated the design to point to the archive. |

## Current Visible Workflow

The visible application now uses:

- `mpps_shipment_demand` for customer/shipment demand;
- `mpps_stock_items` for FG, QC, scrap, blocked, and available stock;
- `production_requirement_service.py` for required quantity and tons;
- `material_requirement_service.py` for BOM, compound, bead, and band needs;
- `oven_capacity_service.py` for mould/category daily capacity;
- `oven_schedule_service.py` for selected-date quantity allocation and day/night split;
- `mpps_oven_plan` for historical active oven compatibility;
- shipment-risk, data-quality, and raw-Excel traceability pages for warnings and audit.

## Remaining Legacy Items

The database/ORM still contains legacy tables and columns such as
`tire_types.curing_minutes`, `shifts.max_working_minutes`, `orders`,
`order_items`, and `oven_schedule`. They were deliberately left intact because
this task prohibited destructive schema or data changes.

Existing rows created by earlier versions, including any prototype ovens or
tire types, may still be present in the database. They are no longer seeded on
fresh startup and are not used by the current visible planning workflow.
