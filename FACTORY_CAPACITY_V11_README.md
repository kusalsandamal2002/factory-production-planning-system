# MPPS Factory Resource & Capacity Intelligence V11

This upgrade replaces the fragmented/manual-first capacity path with one integrated capacity intelligence foundation.

## Core changes

- **One authoritative Real Capacity Resolver** for Production Planning, Stock Planning, Factory Can Out and Capacity views.
- **Lossless OVEN resource evidence**: plan allocations plus full physical line/cavity skeleton are captured before aggregation.
- **Self-learning Production Line / Cavity / Mold / Casing registries** with LEARNING → ACTIVE → DORMANT/RETIRED lifecycle; no silent destructive deletion.
- **Plan vs Actual execution observations** join final OVEN resource plans to verified PROD actual production.
- **Safe / Expected / Stretch** real capacity profiles with time-ordered validation, WAPE, confidence and drift.
- **Optional advanced nonlinear ML challenger** (XGBoost, GPU when available; scikit-learn fallback). It is promoted only if future-period validation beats the robust model.
- **Shared casing pressure / physical constraint adjustment** is included in the authoritative resolver and existing daily resource reservation engine.
- Manual Capacity Master is retained only as **Legacy / Technical Capacity Baseline**.
- Master Data Center decorative top cards are removed; Factory Capacity becomes an integrated Pro workspace.
- CPU thread/runtime tuning is enabled. NVIDIA GPU is detected automatically for optional XGBoost acceleration; CPU remains the safe fallback.

## OVEN workbook learning

The importer now preserves:

- physical line + cavity/press position skeleton, including positions with no current SAP plan;
- source allocation rows;
- Day/Night/Next-Day plan evidence;
- cavity count and allocation-slot count per SAP/day;
- Mold Key / casing evidence from existing technical mappings and Total Bead tyre-size references;
- verified PROD actual production as a separate truth source.

Repeated allocation rows are **not blindly treated as physical molds**. Stable resource usage is learned only from repeated historical evidence and current physical master constraints.

## Optional ML packages

`requirements-ml-optional.txt` includes NumPy, scikit-learn, joblib, XGBoost and psutil. The installer attempts to install them unless `-SkipOptionalML` is supplied. Failure to install optional packages does not disable the robust built-in capacity engine.

## Safety

The installer backs up every overwritten source file under:

`data_sources/upgrade_backups/factory_capacity_v11_<timestamp>`

It runs compile checks, a static/self-learning self-test, then the database V11 schema prepare/training step. Existing operational tables are extended non-destructively.
