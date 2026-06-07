# Real Oven Planning Design

## Scope

This design replaces the empty legacy minute scheduler on the Daily Oven
Schedule page with a quantity-based planning model derived from the MPPS and
OVEN workbooks. It does not delete or rewrite the legacy tables, source Excel
data, users, roles, or audit history.

## Verified Data Sources

| Purpose | Source |
|---|---|
| Opening stock | `mpps_stock_items` |
| Active shipment demand | `mpps_shipment_demand`, `orders`, `order_items` |
| Production transaction history | `tire_stock_movements` |
| Unit weight | `mpps_stock_items.average_weight` |
| BOM | `mpps_bom_items` |
| Compound | `mpps_compound_master` |
| Bead | `mpps_bead_master` |
| Band | `mpps_band_master` |
| Quantity capacity | `mpps_capacity_master` joined through `mpps_stock_items.bead_type` |
| Oven compatibility evidence | preserved rows in `mpps_oven_plan` |
| Active oven count | `ovens` |

The imported `mpps_oven_plan` rows are read-only evidence from the June 1, 2026
OVEN workbook. Recalculation does not delete or overwrite them.

## Production Requirement

For a selected planning date:

```text
Opening Available = FG + QC - Scrap - Blocked
Eligible Demand = active demand due by the planning date
Shortage = max(Eligible Demand - max(Opening Available, 0), 0)
Production Required = Shortage
Production Tons = Production Required * Unit Weight / 1000
```

Demand without a due date is included to avoid understating production and is
flagged as missing date data.

Daily production movements are reported separately. The current production
entry workflow posts the same quantity into FG stock and the movement ledger,
so movements are not added to available stock again. This prevents double
counting. Completed/cancelled/rejected demand is excluded by status.

## Material Requirement

```text
BOM Requirement = Production Required * Usage Per Unit * (1 + BOM Wastage %)
Compound Requirement = Production Required * Compound Weight * (1 + Allowance)
Bead Requirement = Production Required * Beads Per Tyre
Band Requirement = Production Required * Band Usage * (1 + Allowance)
```

Visible assumptions:

- Compound allowance: 25%, source `OVEN workbook`
- Band allowance: 15%, source `OVEN workbook`
- Day shift share: 50%, source `VISIBLE ASSUMPTION`

The day shift share is configurable through the service API. It is necessary
because the imported oven-plan table retained `TOTAL` quantities rather than
the workbook's separate day/night values. The UI labels this assumption.

## Capacity

Despite its name, `mpps_capacity_master.item_code` contains mould/category keys
such as `10.00-20 TR`, not SAP finished-item codes. The verified relationship is
`mpps_stock_items.bead_type = mpps_capacity_master.item_code`. There are no
direct SAP-code matches in the current data.

```text
Calculated Daily Capacity = Running Moulds * Pieces Per Mould Per Day
Effective Daily Capacity =
    Available Capacity Per Day, when positive,
    otherwise Calculated Daily Capacity
Required Days = ceiling(Production Required / Effective Daily Capacity)
```

No curing minutes, downtime, changeover minutes, or minute utilization are
calculated.

## Oven Schedule

1. Load dated production requirements ordered by earliest due date and shortage.
2. Load direct item capacity.
3. Find oven compatibility from the preserved `mpps_oven_plan` history.
4. Treat capacity records as shared mould/category capacity and allocate each
   capacity key only once per selected date.
5. Plan at most the remaining effective daily-capacity quantity.
6. Spread that quantity across historically used active ovens in proportion to their
   recorded quantities.
7. Split each allocation by the visible day-share assumption.
8. Leave items with missing capacity or compatibility unplanned and explain the
   reason.

Schedule output carries explicit flags/statuses for missing capacity, missing
compatibility, missing due date, and missing unit weight. Demand without a due
date remains included in production requirement calculations.

This is deterministic, preserves source data, and does not claim an optimized
minute-level sequence.

## Legacy Isolation

`app/services/scheduler.py`, `app/services/schedule_priority_service.py`, and
the `oven_schedule` table remain available for the existing order enquiry
workflow. The Daily Oven Schedule page no longer reads or rebuilds that
minute-based table.

## Known Data Gaps

- All 746 imported shipment-demand rows currently have no due date.
- Imported oven-plan rows contain `TOTAL`, not separate day/night values.
- Only 84 item codes have observed oven compatibility in the imported plan.
- There is no approved item/oven compatibility master.
- There is no shipment movement ledger connected to MPPS stock.
- No curing time, downtime, or changeover master exists.
- The 25% compound and 15% band allowances need business-owner approval.
