# Developer Notes

## Working On Planning Logic
- Keep the central planning engine in `app/services/factory_planning_engine.py` as the source of truth.
- Avoid duplicating allocation or delivery logic in UI code.
- Update tests when changing planning order, stock handling, or resource reservation behavior.

## UI Flow Notes
- Shipment Entry saves a shipment, triggers replanning, and then opens the saved shipment in Shipment Details.
- Shipment Details supports review of target/plan date, receive date, progress, delivery status, and planning notes.
- Double-clicking the shipment name opens the full shipment detail view.
- Double-clicking the target/plan date should edit that date and trigger replanning.

## Safe Database Practices
- Use short lock/statement timeouts around schema upgrade work.
- Prefer idempotent schema changes.
- Keep errors user-readable so lock conflicts can be recovered from.

## Test Strategy
- Run the planning engine tests before merging.
- Verify Python compilation on touched files.
- Add regression tests for any rule that changes planning order, progress math, or resource reservation behavior.

## Known Gaps
- Some UI areas still mix legacy and new planning fields.
- Reporting and calendar visualization remain opportunities for follow-up work.
- The planning engine currently prioritizes correctness and determinism over advanced optimization.
