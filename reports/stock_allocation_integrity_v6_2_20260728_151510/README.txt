MPPS STOCK ALLOCATION INTEGRITY AUDIT V6.2
=============================================

Repair run: 1
total_shipment_items_audited: 915
invalid_rows_before: 81
invalid_rows_after: 0
imported_review_rows_recalculated: 915
non_review_invalid_rows_repaired: 0
negative_stock_allocations_fixed: 81
production_required_over_quantity_fixed: 81
live_reserved_sap_codes: 0
stock_master_sap_codes: 3539

Core invariant:
0 <= stock_allocated_qty <= quantity
0 <= production_required_qty <= quantity

Imported-review shipments were recalculated cumulatively.
Negative source stock was treated as zero physical stock.
Approved/live reservations were subtracted before preview allocation.