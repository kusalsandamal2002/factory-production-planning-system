# APP REPORT

## Purpose
This application is a factory production planning and shipment coordination system for tyre manufacturing operations. It combines shipment entry, stock allocation, SMDS approval rules, resource reservation, and shipment detail tracking in one PostgreSQL-backed desktop workflow.

## Current Architecture
- `app/ui/order_entry_page.py` handles shipment capture and cart-style item entry.
- `app/ui/shipment_orders_page.py` is the shipment planning and detail review workspace.
- `app/services/factory_planning_engine.py` is the central planning engine and schema upgrader.
- `app/services/factory_out_date_logic.py` provides the shipment entry calculation path and lightweight compatibility logic.
- `app/ui/main_window.py` owns page navigation and post-save routing.

## Tech Stack
- Python 3
- PySide6
- SQLAlchemy
- PostgreSQL
- Pytest / unittest

## Workflow Summary
1. User creates or edits a shipment.
2. Approved SMDS items are added to the shipment.
3. Stock is allocated first, then production is scheduled.
4. The planning engine reserves mold, casing, and line cavities by date.
5. Shipment and item records are updated with receive dates, progress, and delivery status.
6. Saved shipments are opened in the Shipment Details page for review.

## How To Run
- Start the desktop app from the project entry point.
- Ensure PostgreSQL is running and the application database credentials are valid.

## How To Test
- Run the targeted planning tests with pytest.
- Run Python compile checks against the touched modules.

## Known Limitations
- Planning is date- and resource-driven, but it still depends on data quality in SMDS, molds, casings, and cavity master tables.
- A small number of legacy pages still use compatibility columns and fallback logic.
- Replanning is centralized, but the UI can still be improved for bulk editing and validation feedback.

## Roadmap
- Add richer planning exception diagnostics.
- Add calendar visualization for resource reservations.
- Improve shipment-level editing with inline controls.
- Add exportable planning reports.
