# MPPS Factory Intelligence V10

## Purpose

MPPS V10 upgrades the production planner from a static Excel-import application into a controlled, explainable factory decision-support system. The system learns from the planner's FINAL OVEN workbooks and verified PROD actuals while keeping the newest OVEN workbook as operational authority.

## Non-negotiable authority rules

1. **Newest OVEN workbook by plan date = LIVE / FINAL operational truth.**
2. **Older OVEN workbooks are never discarded.** They are historical evidence and ML training data, but may not move live operations backwards.
3. **PROD column D (`STOCK` / `TOTAL STOCK`) = monthly opening-stock evidence.** It is not a fresh daily physical-stock snapshot.
4. **Dated PROD DAY/NIGHT column pairs = verified actual production.**
5. **Excel remains FINAL while AI is in SHADOW / supervised-learning mode.** AI recommendations never silently replace the human final plan.

## V10 intelligence architecture

### 1. Operational Source Authority

The latest committed OVEN plan date drives live shipments, stock-as-of date, shortage calculations, production planning, delivery planning, MRP and next-day AI candidate generation. Older workbook imports are forced to historical behavior.

### 2. Data Identity / Auto-Heal

SAP and description mismatches are resolved with a confidence-gated hierarchy:

- exact canonical SAP
- human-approved learned alias
- historical learned alias
- within-workbook consensus
- exact unique normalized description
- high-threshold fuzzy description similarity
- review queue when evidence is ambiguous

Only very-high-confidence mappings auto-correct. Ambiguous data remains visible for review. A planner can approve a suggested mapping or map a description to a canonical SAP; that correction becomes supervised evidence for future imports.

### 3. Monthly Opening Stock Evidence

Every OVEN workbook contributes PROD column-D opening-stock evidence with workbook, plan date, SAP, raw value and normalized operational value. Negative raw values are preserved for audit but are not allowed to create artificial negative physical stock. The newest LIVE workbook within a month may establish/revise that month's opening-stock authority; historical imports add evidence only.

Current physical stock is derived as:

`Monthly Opening + Verified Actual Production - Confirmed Shipment Out +/- approved adjustments`

Planned production is never posted as physical stock.

### 4. Verified Production History

For each production date and SAP, MPPS stores DAY actual, NIGHT actual and total actual. When historical files overlap the same production date, evidence from the workbook with the newest plan date wins independent of import order. This makes a three-year archive safe to bulk-load even when filenames are not chronological.

### 5. Plan vs Actual Learning

Each FINAL Excel plan is reconciled with later verified actual production. MPPS learns:

- completion ratio by SAP
- DAY/NIGHT execution share
- weekday behavior
- recent drift
- plan achievement and under/over production patterns
- execution confidence

### 6. Real Factory Capacity Learning

V10 learns capacity from verified actual output instead of relying only on static theoretical values. The model uses robust quantiles, exponentially weighted recent behavior, weekday signals, walk-forward validation and drift/stability metrics.

Outputs include:

- safe capacity
- expected capacity
- stretch capacity
- recent capacity
- validation WAPE
- trend/stability
- confidence band
- DAY share

Models exist at factory level and SAP level where sufficient evidence is available.

### 7. Human Planner Policy Learning

The system learns how the planner converts shipment/stock shortage into the FINAL Excel production quantity. Per-SAP and global policy models estimate a planning ratio and conservative ratio using walk-forward validation. This lets AI learn not only *what was produced* but *how the experienced planner made the decision*.

### 8. V10 Hybrid AI Candidate

The next-day candidate combines:

- shipment demand and due-date pressure
- physical/projected stock
- execution completion model
- learned real capacity
- human planner policy model
- DAY/NIGHT behavior
- recent drift and confidence
- safety buffers

The result remains explainable: the candidate stores the execution ratio, learned capacity, planner-policy ratio, confidence and rationale used to produce the recommendation.

## AI control progression

- **SHADOW** — Excel is FINAL; AI observes and scores itself.
- **ASSISTED** — AI creates a candidate; planner edits/approves.
- **SUPERVISED AUTO** — only high-confidence normal cases can be delegated.
- **AUTO** — only after sufficient forward validation, data coverage and stable model performance.

No model can honestly guarantee 100% future accuracy in a factory environment. The V10 design therefore uses measured forward accuracy, confidence calibration, drift detection and human approval gates rather than an unsafe accuracy claim.

## Future three-year historical backfill

V10 includes `tools/backfill_factory_intelligence_v10.py`. It accepts a folder, ZIP or individual workbook. Historical mode is forced so old files train models without changing the latest live operational state. Exact duplicates are skipped by SHA-256 before expensive Excel analysis.

Example:

```powershell
& ".\.venv\Scripts\python.exe" tools\backfill_factory_intelligence_v10.py "D:\MPPS_3_YEAR_OVEN_HISTORY.zip"
```

After ingestion, the tool rebuilds execution, capacity and planner-policy models once.

## Supplied August validation

The supplied August 2026 OVEN workbooks confirm the intended data semantics:

- PROD column B contains SAP code.
- PROD column C contains material description.
- PROD column D is `STOCK` / `TOTAL STOCK` opening-stock evidence.
- PROD columns E/F contain scrap/block evidence.
- dated DAY/NIGHT pairs contain verified actual production for prior dates.
- the latest actual date in each daily workbook is normally the previous production day.
- the two supplied `AUGUEST 07-2026` files are exact duplicates by SHA-256 and should count only once in historical learning.

The current fast semantic analyzer processed the supplied `AUGUEST 10-2026` workbook in approximately 23 seconds in the build environment, mapping 3,252 opening-stock rows, 1,117 shipment rows, 283 oven-plan rows and 1,237 production-history rows at 99.76% workbook confidence. Actual timing varies by PC and disk.

## New UI

`Factory Intelligence Center` provides:

- historical workbook/actual-day coverage
- capacity confidence and model count
- real capacity models
- factory capacity history
- data identity / auto-heal review
- supervised mapping approval
- opening-stock evidence
- model rebuild and state refresh

The AI Planning Center also exposes learned safe capacity and planner-policy ratios in candidate decisions.
