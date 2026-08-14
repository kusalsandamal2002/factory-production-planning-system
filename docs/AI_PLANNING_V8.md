# MPPS AI Production Planning V8

## Operating principle

MPPS now uses a controlled **human-final / AI-shadow** workflow:

1. The operator imports the daily **OVEN SHEET PLAN `<DATE>`** workbook.
2. The workbook plan date is detected from `Daily Plan!C3` when available; otherwise the date embedded in the workbook file name is used.
3. The imported OVEN Day/Night schedule is stored as the **FINAL Excel plan**. AI never silently overwrites it.
4. In `PROD`, each dated column is interpreted as the **Day actual** for that date and its immediately following undated column as the **Night actual**. Only dates **before** the workbook plan date are promoted to verified actual production.
5. MPPS reconciles Final Plan vs Actual by date and SAP and records variance, achievement and error.
6. A leakage-safe adaptive model learns execution reliability for every SAP item. The model is an explainable ensemble of recent EWMA completion, robust historical median and same-weekday behavior, plus learned Day/Night share.
7. MPPS builds the next-day planning stock from monthly opening stock, verified production, confirmed shipment-out and—when the immediately preceding day has not closed yet—the **expected remainder of that day’s FINAL Excel plan**. The final plan is used only as an in-flight projection; it is never written as historical actual.
8. The next-day **AI Candidate** is generated from active shipment demand, planning stock, learned completion, due-date urgency and available daily capacity.
9. When later workbooks arrive, MPPS evaluates the previous AI candidate against both the human Final Excel plan and later verified actual production.

## Control modes

`SHADOW` is the default and safe mode. Excel remains the final execution authority.

Automatic planning is not enabled merely because a model has a high confidence score. Readiness requires a configured minimum number of **forward, end-to-end AI candidate days**, target validation accuracy and actual-data coverage. Retrospective historical backtests are displayed but do not count as forward validation days.

Even after the readiness gates pass, promotion requires an explicit authorized-user decision. `auto_write_enabled` stays false by default.

No statistical or machine-learning system can guarantee 100% future accuracy. MPPS therefore measures real out-of-sample accuracy, coverage and confidence instead of claiming certainty.

## Stock rule

The manually supplied monthly count is the opening-stock authority:

`Current Physical Stock = Monthly Opening Stock + Verified Actual Production - Confirmed Shipment Out`

For next-day AI planning, if yesterday/today has a Final Excel plan but its actual production is not complete yet:

`Planning Stock = Current Physical Stock + Model-Expected Remainder of Previous Final Plan`

Scrap and Blocked are separate non-usable physical/status buckets. They are not subtracted a second time from FG/QC, eliminating the artificial negative-stock behavior seen in the legacy formula.

## AI model and governance

Per SAP item the service stores:

- sample days
- adaptive completion ratio
- robust median completion ratio
- same-weekday completion pattern
- learned Day/Night share
- MAE and MAPE
- leakage-safe validation accuracy
- confidence score and confidence band

Candidate plans are also evaluated end-to-end:

- AI candidate vs Final Excel plan
- AI expected actual vs verified actual production
- forward validated vs retrospective status

The AI Planning Center shows readiness, candidate priorities, reconciliation history, evaluation results and model health.

## New database objects

- `mpps_ai_settings`
- `mpps_final_plan_history`
- `mpps_actual_production`
- `mpps_actual_production_dates`
- `mpps_plan_actual_reconciliation`
- `mpps_ai_model_state`
- `mpps_ai_plan_runs`
- `mpps_ai_plan_items`
- `mpps_ai_plan_evaluation`

They are created automatically with `CREATE TABLE IF NOT EXISTS` when AI Planning is first used.

## User-facing integration

- **Data → Monthly Opening Stock**: monthly physical opening-stock authority.
- **Data → Stock Control**: ledger-style current stock plus source stock buckets and audit corrections.
- **Planning → Daily Plan → AI Candidate - SHADOW**: compare live plan, Final Excel plan and AI candidate.
- **Reports & Admin → AI Planning Center**: AI readiness, Plan-vs-Actual, AI evaluation and model health.
- **Intelligent Excel Import**: every normal daily OVEN import automatically performs the learning/reconciliation cycle and creates the next-day advisory candidate.

## Historical backfill

Use `tools/backfill_ai_learning.py` to learn from old OVEN workbooks without altering live stock, shipments or the execution schedule.

Example:

```powershell
python tools\backfill_ai_learning.py `
  "C:\Data\OVEN SHEET PLAN SEPTEMBER 30-2025.xlsx" `
  "C:\Data\OVEN SHEET PLAN OCTOBER 31-2025.xlsx" `
  "C:\Data\OVEN SHEET PLAN NOVEMBER 30-2025.xlsx"
```

Historical backfill uses stable negative internal run IDs. Normal future Excel imports use positive import IDs and supersede matching historical revisions automatically.
