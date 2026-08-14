# MPPS AI V9 — Operational Source + Historical Learning

## Authority rule
- The newest committed LIVE OVEN workbook by plan date is the operational source of truth.
- Stock, shipment demand, planning defaults and AI next-day planning use that latest LIVE date.
- An older workbook is never ignored: it is imported as HISTORICAL evidence for final-plan history, PROD actuals, plan-vs-actual reconciliation, audit and ML training.
- HISTORICAL workbooks cannot roll live shipments, stock, weights or material/BOM masters backwards.

## Stock date semantics
The Stock Control table now shows `OVEN Plan Date` instead of the local database `updated_at` timestamp. Current Ledger is calculated as-of that OVEN date.

## AI V9
AI V9 keeps Excel final authority and remains SHADOW by default. Per SAP it runs a leakage-safe champion/challenger walk-forward competition across:
- factory-prior shrinkage,
- robust median,
- EWMA recency,
- same-weekday ensemble,
- bounded local trend ensemble.

The winning model is selected by walk-forward WAPE. V9 stores a conservative completion ratio, recent WAPE, drift score, weekday/day-night behavior and a confidence band. Urgent or uncertain shortages use the conservative completion estimate to create a visible safety buffer. Drifted models are flagged for human review.

No historical workbook can become live simply because it is imported later. The next AI candidate is always generated for the day after the latest LIVE OVEN plan date.
