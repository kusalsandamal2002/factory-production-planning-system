# Planning Logic

## Goals
The planning engine turns shipment demand into a dated production plan while respecting stock, SMDS approval, and capacity constraints.

## Core Rules
- Target date is optional.
- Shipments with earlier target dates are planned first.
- Shipments without a target date are ordered after dated shipments.
- Finished stock is allocated before production.
- Remaining demand is scheduled against mold, casing, and line cavity availability.
- Item progress is `stock_allocated_qty + produced_qty`.
- Shipment progress is a quantity-weighted completion percentage.
- Factory can receive date is the latest item receive date.
- Delay and early days are derived from the difference between target date and factory can receive date.

## Resource Reservation Model
The engine writes reservations into `planning_resource_reservations` for:
- `mold`
- `casing`
- `line_cavity`

Reservations are tracked by date and resource key so the plan can be replayed safely after a re-run.

## Stock Allocation and Reallocation
Stock is allocated sequentially by SAP code across open shipments. When the planner reruns:
- previous reservations are cleared
- stock allocation is recalculated
- shipments are processed again in priority order

This ensures later orders do not consume stock already assigned to earlier shipments.

## Shipment Timing
- If the shipment has a target date, delivery status is computed against that date.
- If no target date is present, the shipment remains flexible.
- If the factory can receive date is before target date, the shipment is early.
- If it is after target date, the shipment is delayed.

## Horizon Search
When immediate capacity is unavailable, the planner searches forward across the configured planning horizon until it finds a feasible production day.

## Schema Upgrade Safety
Schema upgrades use safe PostgreSQL DDL checks and bounded lock/statement timeouts so the application does not wait indefinitely on idle or stale locks.
