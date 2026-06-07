# Excel Logic Discovery

## 1. Scope

This report documents the planning logic found in the two source workbooks under
`data_sources/`. The workbooks were inspected read-only. No application business
logic, database data, or workbook content was changed.

Files inspected:

- `MPPS Ver-04  MAY 2026.xlsx`
- `OVEN SHEET PLAN  JUNE 01-2026.xlsx`

Both workbooks use the Excel 1900 date system and are saved with calculation mode
set to **manual**. Cached values can therefore be stale until Excel recalculates
the workbook.

## 2. Executive Findings

1. The MPPS workbook is the medium-term stock, shipment, production requirement,
   BOM, material requirement, weight, and broad capacity model.
2. The OVEN workbook is the operational daily planning model. It contains the
   product shortage snapshot, manual oven/press assignments, day/night plans,
   production entry forms, and daily compound/bead/band/core requirements.
3. The two workbooks contain almost the same product population: 3,206 item codes
   overlap, covering about 99.7% of the unique codes in each workbook.
4. The MPPS workbook still contains external formulas pointing to older files:
   `OVEN SHEET PLAN  MAY 19-2026.xlsx` and
   `OVEN SHEET PLAN  MAY 04-2026.xlsx`. It does not point to the current June 1
   workbook.
5. The OVEN workbook has no external workbook links. It is a self-contained
   operational snapshot that appears to have been copied or refreshed from the
   same planning data.
6. Current Excel "capacity" is primarily **quantity per mould per day**, not
   cycle-time or minute-based capacity. No reliable curing-time, planned-minute,
   available-minute, or downtime model was found.
7. The operational schedule is manually assigned to oven/press slots. Excel then
   totals the assigned day and night quantities and derives weights and material
   requirements.
8. Several formulas, dates, and lookup ranges are inconsistent or broken. These
   issues must be treated as data-quality findings, not reproduced blindly.

## 3. Workbook Inventory

### 3.1 MPPS workbook

| Sheet | State | Used range | Formula count | Purpose |
|---|---:|---:|---:|---|
| `Stock` | Visible | `A1:NN6244` | 13,963 | FG/QC/scrap/blocked stock, dated production, customer shipment demand, shortage, shipment readiness, product classification |
| `BOM` | Visible | `A1:GX3338` | 10,477 | Product BOM coefficients, stock/demand lookup, production requirement, compound/bead/band/weight totals |
| `compound ` | Visible | `A1:LF3222` | 312,093 | Product-by-compound expansion and total first/second-stage compound requirement |
| `Weight` | Visible | `A1:GX3233` | 106,756 | Production tonnage by date and total unit weight lookup |
| `Capacity` | Visible | `A1:GX3047` | 7,232 | Mould/category capacity, daily quantity spreading, production days, line tonnage and utilization |
| `Total Bead` | Visible | `A1:GX3036` | 119 | Bead pieces required by tyre group and bead type |
| `TOTAL BAND` | Visible | `A1:JS3036` | 201 | Steel-band production requirement by tyre group |
| `summery ` | Visible | `A1:GX3036` | 252 | Band, bead, production-piece, and production-ton summaries |
| `Capacity 2` | Hidden | `A1:J22` | 21 | Heating-unit/oven list for selected large tyres |
| `tonnage` | Visible | `A1:GX3036` | 70 | Historical monthly tonnage, budget, growth, and maximum-day reporting |

Important workbook structure:

- `Capacity 2` is the only hidden sheet.
- `Weight`, `Total Bead`, `TOTAL BAND`, `summery `, and `tonnage` contain a
  large hidden helper range from `AO:GR`.
- `BOM` has 3,208 hidden rows and `Capacity` has 200 hidden rows, primarily from
  saved filter states.
- Meaningful merged cells are limited: one each in `compound `, `Capacity`,
  `Total Bead`, and `summery `, plus nine in `tonnage`.

### 3.2 OVEN workbook

| Sheet | State | Used range | Formula count | Purpose |
|---|---:|---:|---:|---|
| `PROD` | Visible | `A1:IL6357` | 3,790 | Stock, scrap, blocked stock, day/night production history, shipment demand, shortage, and remaining-to-plan |
| `Daily  Plan` | Visible | `A1:EJ3143` | 5,120 | Printable daily oven plan and actual day/night production entry |
| `OVEN` | Visible | `A1:AF3143` | 4,762 | Manual line/oven/item allocation, day/night quantities, weights, and remaining balance |
| `Total Bead` | Visible | `A1:H134` | 110 | Daily bead requirement from the selected oven plan |
| `compound ` | Visible | `A1:LK6492` | 14,879 | BOM coefficients plus daily day/night compound and core requirement |
| `BAND ` | Visible | `A1:K157` | 381 | Daily steel-band plan and next-day demand |
| `Core` | Visible | `A2:N184` | 328 | Inner-core day/night production plan and stock entry |
| `WGT` | Visible | `A1:BS3270` | 206,263 | Day/night production weight by item and date |
| `Day` | Visible | `B2:L114` | 15 | Day-shift production/defect/achievement form |
| `Night` | Visible | `B2:N116` | 15 | Night-shift production/defect/achievement form |
| `Hourly Plan Day` | Visible | `A2:I21` | 22 | Cumulative 12-hour day-shift targets by line |
| `Hourly Plan Night` | Visible | `A2:I21` | 22 | Cumulative 12-hour night-shift targets by line |

Important workbook structure:

- All sheets are visible.
- `PROD` hides most intermediate production columns.
- `Daily  Plan` hides helper/key columns and 400 filtered rows.
- `OVEN` hides its concatenated lookup-key column `A`.
- `Day`, `Night`, `Core`, and the hourly sheets use many merged cells because
  they are printable forms.
- The workbook contains 441 defined names, mostly saved filter/slicer state for
  the `OVEN` table rather than business master data.

## 4. MPPS Stock and Demand Logic

### 4.1 Important `Stock` columns

| Columns | Meaning |
|---|---|
| `A:B` | Material code and description |
| `C` | FG stock |
| `D` | QC stock |
| `E` | Scrap |
| `F` | Blocked stock |
| `G:AL` | Daily production quantities from May 1 through June 1, 2026 |
| `AQ:GS` | Customer/order/shipment quantity columns |
| `GU` | Total stock |
| `GV` | Total to be shipped |
| `GW` | Stock minus shipment demand |
| `GX` | Ready-for-shipment quantity |
| `GZ` | Pending production weight in tons |
| `HA:HP` | Production version, category, compound/band/bead classification and helper keys |
| `HQ:HR` | Compound weight and total production weight |

Shipment columns have a customer/order label in row 3, a date in row 2, and an
`OK`/`NO` status in row 1. Many unused dates use the sentinel values
December 31, 2060 or December 31, 2061.

Representative formulas for item row 4:

```text
GU4 = SUM(C4:D4) + SUM(G4:AN4) - SUM(E4:F4)
GV4 = SUMIF($1:$1, "ok", 4:4)
GW4 = GU4 - GV4
GX4 = IF(GU4-GV4>0, GV4, GU4)
GZ4 = GW4 * HC4 / 1000
```

Interpretation:

- Excel total stock includes FG, QC, and accumulated dated production, then
  subtracts scrap and blocked stock.
- Shipment demand includes only order columns whose row-1 status is `OK`.
- A negative `GW` is a shortage. The absolute shortage becomes production demand
  in the downstream BOM sheet.
- `GX` is effectively `MIN(total stock, shipment demand)`.

This differs from the proposed software definition
`FG + QC - Scrap - Blocked` because Excel also adds dated production. Software
should store opening stock and confirmed production separately, then calculate
availability as of a selected date.

### 4.2 Shipment status/date logic

Representative row-1 formula:

```text
AQ1 = IF($GW$1="SHIP",
         IF($GX$1<AQ2, "NO", "OK"),
         IF($GX$1<AQ3226, "NO", "OK"))
```

The shipment column becomes eligible when a control date is not earlier than its
shipment date. The control cells and the purpose of the alternate row-3226 date
set are not clearly labelled. This should become an explicit planning cut-off or
scenario date in software.

## 5. MPPS Production and Material Requirement Logic

### 5.1 BOM production requirement

Important `BOM` columns:

| Columns | Meaning |
|---|---|
| `A:B` | Product grouping keys |
| `C:D` | Material code and description |
| `E` | Alternative BOM |
| `F` | Total stock from `Stock!GU` |
| `G` | Total shipment demand from `Stock!GV` |
| `H` | Total quantity to produce |
| `I:CZ` | Compound/component quantities per tyre |
| `DA` | Compound weight |
| `DB` | Bead-wire weight |
| `DC` | Total tyre weight |
| `DD:DE` | Band and bead attributes |

Representative formulas:

```text
F2  = SUMIF(Stock!A:A, C2, Stock!GU:GU)
G2  = SUMIF(Stock!A:A, C2, Stock!GV:GV)
H2  = IF(F2-G2>0, 0, G2-F2)
DA2 = SUM(I2:CZ2)
DB2 = DE2/100*65
DC2 = DA2+DB2
```

Therefore:

```text
Production Required Qty = MAX(Shipment Demand - Total Stock, 0)
Production Required Tons = Production Required Qty * Total Tyre Weight / 1000
```

### 5.2 Compound requirement

The MPPS `compound ` sheet expands every product shortage through every compound
BOM coefficient:

```text
D4 = SUMIF(BOM!C:C, A4, BOM!H:H)
E4 = D4 * SUMIF(BOM!C:C, A4, BOM!I:I)
```

The same multiplication pattern continues across the compound columns.

The summary block beginning near `CY1` calculates:

```text
Second-stage requirement = total product-by-compound requirement
First-stage requirement  = second-stage requirement / batch gross weight
                           * batch base weight
```

Example:

```text
CZ4 = HLOOKUP(CY4, $E$3:$CV$3222, 3220, 0)
DA4 = CZ4 / DB4 * DC4
```

Some batch-weight columns are not labelled clearly and must be confirmed with
the compound planning owner before migration.

### 5.3 Bead requirement

`Total Bead` groups production by tyre size and multiplies by beads per tyre:

```text
C5 = SUMIF(BOM!B:B, A5, BOM!H:H)
D5 = C5 * B5
```

The master values observed are typically two, three, five, or six beads per tyre,
depending on the tyre group.

### 5.4 Band requirement

`TOTAL BAND` groups required production by steel-band/tyre description:

```text
C5 = SUMIF(BOM!B:B, A5, BOM!H:H)
```

The sheet also contains band material codes. Unlike bead requirement, the MPPS
sheet generally treats one grouped production unit as one band requirement and
does not show an explicit per-tyre multiplier.

### 5.5 Weight and tonnage

`Weight` calculates item/date tonnage:

```text
Daily Tons = Daily Production Qty * Total Tyre Weight / 1000
Total Tyre Weight = lookup from BOM total tyre weight
```

Example:

```text
C3  = SUMIF(Stock!A:A, A3, Stock!G:G) * AK3 / 1000
AJ3 = SUM(C3:AI3)
AK3 = SUMIF(BOM!C:C, A3, BOM!DC:DC)
```

The visible date headers in `Weight` show December 2024 and January 2025 while
the formulas point to May/June 2026 production columns in `Stock`. The headers
are stale and must not be used as authoritative dates.

## 6. MPPS Capacity Logic

### 6.1 Item/category capacity

Important `Capacity` columns:

| Columns | Meaning |
|---|---|
| `A:D` | Product key, mould category, casing type, group/assigned unit |
| `E` | Average weight |
| `F:G` | Available moulds and casings |
| `H` | Required production quantity |
| `I` | Required production tons |
| `J` | Calculated production days |
| `L/N/P` | Planned mould count on Line 400, Line 800, and press line |
| `M/O/Q` | Corresponding planned tonnage |
| `R` | Total running moulds |
| `S` | Per-mould daily capacity in pieces |
| `T:BA` | Date-wise planned quantity |
| `BB:BD` | Start date, proposed completion date, adjusted date |

Representative formulas:

```text
H3 = SUMIF(BOM!B:B, A3, BOM!H:H)
I3 = H3 * E3 / 1000
R3 = L3 + N3 + P3
J3 = ROUNDUP(H3 / (R3*S3), 0)
T3 = IF(H3>S3*R3, S3*R3, H3)
U3 = IF(H3-SUM($T3:T3)>$S3*$R3,
        $S3*$R3,
        H3-SUM($T3:T3))
```

The daily plan is a forward fill:

```text
Daily Capacity Qty = Running Moulds * Per-Mould Capacity
Daily Planned Qty  = MIN(Remaining Qty, Daily Capacity Qty)
Production Days    = CEILING(Required Qty / Daily Capacity Qty)
```

### 6.2 Line capacity/utilization summary

The capacity summary uses Excel constants such as:

```text
200 Line available tons/day = 3535 * 80% / 1000
400 Line available tons/day = 5303 * 80% / 1000
800 Line available tons/day = 5240 * 80% / 1000
Spacer available tons/day   =  759 * 100% / 1000
Utilization                 = Planned Tons / Available Tons
```

These constants are evidence from Excel, but they are not explained by oven
cycle time or available minutes. They must become dated configuration records,
not hardcoded Python values.

The cached workbook shows utilization above 100% for several groups, which is a
capacity overload signal rather than a valid schedule.

### 6.3 Heating-unit list

The hidden `Capacity 2` sheet lists 21 heating units named
`LA/OV/ T 800/01` through `LA/OV/ T 800/21`. It maps selected tyre sizes to
total production requirement and sometimes a per-mould capacity. The
`No Of Days` column is present but not calculated.

### 6.4 Capacity limitations

No dependable fields were found for:

- curing/cycle minutes;
- planned minutes;
- shift available minutes;
- maintenance or breakdown downtime;
- changeover time;
- mould change constraints;
- oven active/inactive effective dates;
- item/oven cycle-time compatibility;
- true 24-hour minute-level utilization.

The current Excel capacity model is therefore quantity-based and mould-based.
Minute-based scheduling must wait for verified master data.

## 7. OVEN Workbook Planning Logic

### 7.1 `PROD`: operational stock and shortage

`PROD` is structurally similar to MPPS `Stock`, but production dates are paired
into day (`D`) and night (`N`) columns.

Important columns:

| Columns | Meaning |
|---|---|
| `B:C` | SAP/material code and description |
| `D` | Stock |
| `E:F` | Scrap and blocked stock |
| `G:BT` | Day/night production columns from May 1 through June 2, 2026 |
| `BY:HP` | Customer/order/shipment quantities |
| `HR` | Total to be shipped |
| `HS` | Total stock/production available |
| `HT` | Balance to produce |
| `HU` | Quantity already planned today in `OVEN` |
| `HV` | Remaining quantity to plan |
| `HW:IB` | Product key/category and heel/soft/tread compound attributes |

Representative formulas:

```text
HR4 = SUMIF($1:$1, "ok", 4:4)
HS4 = SUMIF($2:$2, "P", 4:4) - (E4+F4)
HT4 = IF(HS4-HR4>0, 0, HR4-HS4)
HU4 = SUMIF(OVEN!D:D, B4, OVEN!K:K)
HV4 = HT4-HU4
```

Unlike MPPS, this sheet has no separately labelled QC column. Its `TOTAL STOCK`
is the sum of all columns marked `P`, less scrap and blocked stock.

### 7.2 `OVEN`: manual oven/press allocation

Important columns:

| Column | Meaning |
|---|---|
| `B` | Production line |
| `C` | Oven/press number |
| `D:E` | Item code and description |
| `F:H` | Heel, soft, and tread compound attributes |
| `I` | Remark |
| `J` | Total quantity required |
| `K` | Today plan |
| `L:M` | Day and night plan pieces |
| `N` | Core |
| `O` | Next-day plan |
| `P` | Today plus next-day total |
| `Q` | Unit weight |
| `R:S` | Day and night plan weight |
| `T` | Total planned quantity |
| `U` | Remaining balance |
| `V` | Casing type |

Representative formulas:

```text
J3 = lookup required quantity from PROD!HT
P3 = K3 + O3
R3 = L3 * Q3
S3 = M3 * Q3
T3 = K3 + O3
U3 = J3 - SUMIF(D:D, D3, T:T)
```

The line/oven/item assignment and the values in `K`, `L`, `M`, and `O` are
primarily manual inputs. Excel validates and totals the plan but does not
automatically choose the best oven.

Observed current slot structure:

- 510 allocation rows;
- 102 unique oven/press identifiers;
- 205 populated allocation rows;
- 161 unique planned item codes.

The cached June 1 plan totals:

- Day plan: 376 pieces;
- Night plan: 374 pieces;
- Total: 750 pieces;
- Total planned weight: about 20.275 tons.

These are cached workbook values, not independently approved capacity limits.

### 7.3 Line and shift summaries

The `OVEN` summary groups the plan into:

- 200 line;
- 400 line;
- 800 line;
- super-solid/large presses;
- 600 presses;
- O-ring/Bard presses.

`Hourly Plan Day` and `Hourly Plan Night` take the line totals and divide them
evenly into 12 cumulative hourly targets:

```text
Hourly increment = Shift Target / 12
```

Both sheets show time buckets from `07:00` to `19:00`. This is plausible for the
day shift but unclear for the night shift and must be confirmed.

### 7.4 Daily production entry

`Daily  Plan` copies every oven slot and provides:

- day plan;
- produced quantity;
- produced weight;
- night plan;
- produced quantity;
- produced weight;
- tomorrow plan.

Planned values are looked up from `OVEN`; actual produced quantities are manual
entry cells. Actual weights are calculated as produced quantity times unit
weight.

`Day` and `Night` are printable shift forms for line targets, actual quantities,
compound targets, defects, operators, and achievement reporting.

## 8. OVEN Material Requirement Logic

### 8.1 Daily compound

The lower half of `compound ` calculates day and night item quantities from the
`OVEN` sheet, then multiplies them by BOM coefficients:

```text
Day Qty   = SUMIF(OVEN item code, item code, OVEN day plan)
Night Qty = SUMIF(OVEN item code, item code, OVEN night plan)
Component Requirement = (Day Qty + Night Qty) * BOM coefficient
```

The printable compound summary applies a 25% uplift:

```text
Second-stage requirement = calculated requirement * 1.25
First-stage requirement  = second-stage requirement / batch gross weight
                           * batch base weight
```

The 25% factor is present in Excel but is not labelled as scrap, process loss,
safety stock, or batch-rounding allowance. It must be confirmed before becoming
a software rule.

### 8.2 Daily bead

`Total Bead` groups total planned tyre quantity and multiplies it by the bead
count per tyre:

```text
Total Bead Requirement = Planned Tyres * Beads Per Tyre
```

### 8.3 Daily band

`BAND ` obtains day and night quantities by band/tyre group and applies a 15%
uplift:

```text
Band Production Plan = (Day Qty + Night Qty) * 1.15
```

The 15% factor must be confirmed as an approved process allowance.

### 8.4 Inner core

`Core` groups day and night quantities by core description:

```text
Total Core Plan = Day Core Plan + Night Core Plan + Closing Stock
```

Produced quantities and stock are intended as shift-entry fields.

## 9. Cross-Workbook Dependency

The logical flow is:

```text
Stock + QC + production - scrap - blocked
                    |
                    v
Eligible shipment demand by shipment date/status
                    |
                    v
Production shortage by item
                    |
        +-----------+-----------+
        |           |           |
        v           v           v
      BOM       Item weight   Mould/category capacity
        |                         |
        v                         v
Compound/bead/band/core       Date-wise quantity plan
        |                         |
        +------------+------------+
                     v
             Manual oven/press assignment
                     |
                     v
        Day/night plan and production entry
```

Physical workbook linkage is currently unsafe:

- MPPS `Stock!HB` uses formulas such as
  `VLOOKUP(A4,[1]PROD!$B:$C,2,0)`.
- MPPS `Weight!AL` contains 526 formulas such as
  `SUMIF([2]WGT!$B:$B,A7,[2]WGT!$BR:$BR)`.
- Link `[1]` points to an OVEN workbook dated May 19, 2026.
- Link `[2]` points to an OVEN workbook dated May 4, 2026.
- The current June 1 OVEN workbook is not the linked source.

Software must replace these file-path links with database relationships keyed by
material code and effective date.

## 10. Data Quality and Unclear Logic

### 10.1 Cached formula errors

Because calculation mode is manual, these are cached workbook errors and may
change after recalculation. They still identify fragile areas.

MPPS:

- `Stock`: 73 `#N/A` cells;
- `BOM`: 2 `#N/A` cells;
- `Weight`: 526 `#VALUE!` cells caused by the obsolete external `WGT` link;
- `Capacity`: 38 `#DIV/0!` cells;
- `tonnage`: 1 `#DIV/0!` cell.

OVEN:

- `PROD`: 8 `#N/A` cells;
- `Daily  Plan`: 2,142 `#N/A` cells, mainly lookups on blank oven-slot rows;
- `OVEN`: 915 `#N/A`, 306 `#VALUE!`, and 6 `#REF!` cells;
- `compound `: 22 `#N/A` and 3 `#DIV/0!` cells;
- `Core`: 1 `#N/A` cell.

### 10.2 Specific inconsistencies

1. MPPS `Weight` date headers do not match the source production dates used by
   its formulas.
2. MPPS `Capacity` dates jump from June 12 to June 18, 2026, omitting June 13-17.
3. The OVEN `PROD` sheet includes paired production dates through June 2, while
   `WGT` ends at June 1.
4. Several OVEN formulas calculate against blank slot rows and intentionally
   produce `#N/A`/`#VALUE!` rather than a clean blank.
5. Six `OVEN` formulas contain broken `#REF!` references.
6. Some copied compound formulas use a fixed item reference such as `$A$3224`
   where a row-relative item reference appears to be intended.
7. Some `Total Bead` `SUMIF` ranges shift downward on every row rather than using
   one fixed source range.
8. Several cells contain mixed Sinhala text and mojibake/incorrectly decoded
   legacy text.
9. The meaning of `HEEL`, `SOFT`, `Tred`, `CORE`, and some category keys is not
   defined in the workbook.
10. There is no explicit active/inactive flag for ovens or moulds.
11. The current plan contains no curing-time or cycle-minute source.
12. Night-shift hourly buckets repeat the day-shift `07:00-19:00` labels.
13. The 25% compound uplift and 15% band uplift are not documented.
14. Capacity constants such as 3,535 kg/day, 5,303 kg/day, and 5,240 kg/day are
   not linked to a calculation master.
15. `Capacity 2` contains a `No Of Days` column but no completed formula logic.

## 11. Proposed Software Logic

### 11.1 Preserve source data

Keep every imported workbook, sheet, raw row, raw cell, formula, cached value,
hidden state, merge range, and source file checksum. Never use raw Excel tables
as the live planning model.

### 11.2 Normalize master and transaction data

The clean software model should separate:

- product/material master;
- unit weight and effective date;
- FG, QC, scrap, and blocked stock snapshots;
- confirmed production transactions;
- customer orders and shipment lines with due dates and status;
- product BOM and component quantities;
- compound/bead/band/core masters;
- oven/press master and active status;
- mould master and oven compatibility;
- per-mould/per-shift throughput;
- shift calendar and planned downtime;
- daily oven allocation;
- actual shift production and audit history.

### 11.3 Production requirement

Recommended date-aware calculation:

```text
Opening Available Stock = FG + QC - Scrap - Blocked

Available Stock At Date =
    Opening Available Stock
    + Confirmed Production up to the planning date
    - Previously Allocated/Completed Shipments

Shortage Qty =
    MAX(Cumulative Eligible Shipment Demand - Available Stock At Date, 0)

Production Required Tons =
    Shortage Qty * Effective Unit Weight / 1000
```

Shipment demand should be processed in due-date and manager-priority order. The
Excel `OK`/`NO` row should become an explicit eligibility rule, not a hidden
formula.

### 11.4 Material requirement

```text
Component Requirement =
    Planned Production Qty * Effective BOM Quantity
```

Process allowances must be separately configured:

- compound allowance: currently 25% in the OVEN workbook;
- band allowance: currently 15% in the OVEN workbook;
- batch rounding: round to approved compound batch sizes;
- bead requirement: planned quantity times beads per tyre.

No allowance should be hardcoded until approved by the responsible planner.

### 11.5 Capacity and oven planning

Until cycle-time master data is supplied, reproduce only the verified
quantity-based logic:

```text
Daily Item Capacity =
    Active Compatible Moulds * Approved Pieces Per Mould Per Shift/Day

Daily Planned Qty =
    MIN(Remaining Required Qty, Daily Item Capacity)
```

The service should then assign quantities by:

1. shipment due date;
2. manager priority;
3. shortage severity;
4. compatible oven/press and mould;
5. available day/night capacity;
6. remaining requirement;
7. changeover and continuity rules once those masters exist.

Minute-based fields should be enabled only after verified data exists:

```text
Available Minutes = Shift Minutes - Planned Downtime
Planned Minutes   = Planned Cycles * Cycle Minutes + Changeover Minutes
Utilization       = Planned Minutes / Available Minutes
```

### 11.6 Risk output

For every shipment/item, calculate:

- available stock;
- shortage;
- planned completion date;
- capacity-constrained completion date;
- unplanned quantity;
- missing BOM/weight/capacity/compatibility data;
- shipment risk status and reason.

## 12. Phase 2 Preconditions

Before replacing the application scheduler, confirm:

1. whether production after the stock snapshot should be included in available
   stock exactly as Excel does;
2. the approved meaning of shipment `OK`/`NO`;
3. the 25% compound and 15% band allowances;
4. line capacity constants and their effective dates;
5. actual day/night shift hours;
6. oven/press active status and mould compatibility;
7. per-item curing/cycle time, if minute-based scheduling is required;
8. whether the June 1 OVEN workbook supersedes both old external OVEN links;
9. which broken or shifting formulas are accepted business rules versus copy
   errors.

No schedule replacement should be implemented until these items are either
confirmed or represented as visible configuration assumptions.
