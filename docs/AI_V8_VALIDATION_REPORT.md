# MPPS AI V8 Validation Report

## Workbook semantics validated against supplied factory files

The `PROD` date-pair structure was checked directly in the supplied OVEN workbooks:

| Workbook plan date | Verified prior actual date headers | Current plan-date header excluded from actual |
|---|---|---|
| 2025-09-30 | `BK=2025-09-28`, `BM=2025-09-29` | `BO=2025-09-30` |
| 2025-10-31 | `BK=2025-10-29`, `BM=2025-10-30` | `BO=2025-10-31` |
| 2025-11-30 | `BI=2025-11-28`, `BK=2025-11-29` | `BM=2025-11-30` |
| 2026-06-01 | `BM=2026-05-30`, `BO=2026-05-31` | `BQ=2026-06-01` |

For each dated Day column, the immediately following undated column is treated as the Night column. This matches the operator-confirmed example that `BI:BJ` represents 2025-11-28 actual Day/Night production.

## Safety invariants

- Final OVEN Excel plan remains the execution authority in SHADOW mode.
- Plan data is never inserted into the verified actual-production ledger.
- Only `PROD` dated pairs strictly before the workbook plan date are accepted as historical actuals.
- A complete actual date can represent zero production for a planned SAP; zero rows are not silently excluded from Plan-vs-Actual accuracy.
- Historical backfill does not update live stock, shipments or live execution schedules.
- Retrospective AI runs do not count toward the forward automation-readiness gate.
- Scrap and Blocked are not double-subtracted from FG/QC usable stock.
- Current physical stock uses monthly opening + verified actual production - confirmed shipment-out.
- Next-day planning can use an expected remainder from the immediately preceding Final Excel plan while actual is still pending, without recording it as actual production.

## Automated validation

The release passes Python compilation for the application/tests and the targeted automated suite covering Stock Control, AI model behavior, `PROD` actual extraction, Material Requirement and Day/Night shift-report behavior.

Database-backed integration must still be executed on the operator's PostgreSQL installation after patch installation because the release build environment does not contain that live factory database.
