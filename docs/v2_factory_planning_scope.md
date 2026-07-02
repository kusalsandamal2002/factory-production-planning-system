# Factory Production Planning System V2

## Main Direction

Existing MPPS / Excel-based factory planning app will be updated into a complete database-driven production planning system.

Excel upload will no longer be the main workflow. Excel import can remain only as a legacy/admin tool for historical migration.

## New Main Workflow

Marketing Order
→ Order Entry
→ Tyre Item Master
→ Stock Check
→ Production Required Qty
→ Production Line Routing
→ Mold / Casing / Cavity Check
→ Production Scheduling
→ Daily Plan
→ Day / Night Shift Plan
→ Material Requirement
→ Delivery Date Calculation
→ Reports

## Main Modules

1. Dashboard
2. Customer Order Management
3. Tyre Product Tree Master
4. Tyre Item Master
5. Production Line Master
6. Mold Master
7. Casing Master
8. Capacity / Time Master
9. Production Planning
10. Delivery Date Calculation
11. Daily Plan
12. Shift Plan
13. Material Requirement
14. Reports
15. Admin Settings
16. Legacy Excel Import

## Tyre Types

1. Resilient Tyre
2. Press-On Tyre
3. Cured-On Tyre

## Production Lines

### 200T Line
- Cavities: 19
- Molds: 48
- Casing required: No

### 400T Line
- Cavities: 38
- Molds: 117
- Casing required: Yes
- Casing types: Mono, B2, B3, B4

### 800T Line
- Cavities: 26
- Molds: 78
- Casing required: Yes
- Casing types: Mono, B7, B5 SP3, B5 SP2, B5 SP1, B5

### SuperSolid Line
- Cavities: 3

## V2 Rule

Main app must work from direct data entry and database master data. Old Excel upload screens should be moved away from the main workflow.
