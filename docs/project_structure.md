# Project Structure

This repository separates runtime code from database maintenance, data tools,
documentation, and historical backups. The visible application uses MPPS stock,
shipment demand, material requirements, and Excel-derived quantity capacity.

## Top-Level Layout

```text
factory_oven_planner/
  app/                  Runtime application code
  database/             Database migrations and targeted schema fixes
  tools/                Reusable import, maintenance, and diagnostic utilities
  docs/                 Design, discovery, and project documentation
  backups/              Historical source snapshots, excluded from runtime
  data_sources/         Local source workbooks, ignored by Git
  run.py                Application entry point
  requirements.txt      Python dependencies
  docker-compose.yml    Local PostgreSQL service
  .env.example          Environment variable template
```

## Folder Responsibilities

### `app/`

Contains all code required by the running desktop application:

- `app/ui/` contains PySide6 pages, windows, dialogs, and styles.
- `app/services/` contains MPPS demand, quantity scheduling, capacity, stock,
  material, and shipment-risk services.
- `app/utils/` contains reusable runtime formatting and export helpers.
- `app/models.py`, `app/database.py`, `app/config.py`, and `app/main.py`
  provide the core data model, database connection, configuration, and startup.

Historical copies must not be stored inside `app/`, because that makes runtime
ownership unclear and can interfere with code searches and packaging.

### `database/`

Contains manually executed database setup and upgrade scripts:

- `database/migrations/` retains migrations that may be required for a fresh
  setup or an existing installation upgrade.
- `database/schema_fixes/` retains targeted column-width and schema correction
  utilities.

These scripts are not run automatically. Run a reviewed migration from the
project root with module syntax, for example:

```powershell
python -m database.migrations.create_audit_logs_migration
```

Future database migrations belong in `database/migrations/`. Narrow corrective
scripts belong in `database/schema_fixes/`.

### `tools/`

Contains reusable operator and development utilities:

- `tools/importers/` loads source workbooks and maps raw Excel data.
- `tools/diagnostics/` contains read-only quality and consistency checks.
- `tools/maintenance/` contains explicit administrative operations.

Run tools from the project root with module syntax. Examples:

```powershell
python -m tools.importers.load_excel_raw_to_db
python -m tools.importers.map_raw_excel_to_clean_mpps
python -m tools.diagnostics.check_mpps_mapping_quality
```

The dummy-data cleanup utility remains available under `tools/maintenance/`.
It is destructive and retains its required confirmation argument.

Future import scripts belong in `tools/importers/`. Future read-only checks
belong in `tools/diagnostics/`. Reusable administrative tasks belong in
`tools/maintenance/`.

### `docs/`

Contains maintained project knowledge:

- `excel_logic_discovery.md` documents the source workbook structure and logic.
- `real_oven_planning_design.md` documents the real planning design.
- `project_structure.md` documents repository ownership and cleanup decisions.

### `backups/`

Contains historical code snapshots kept only for reference:

- `backups/code_backups/` contains tracked source copies moved out of runtime.
- `backups/code_backups/legacy_minute_scheduler/` contains retired prototype
  scheduling and related UI modules that are no longer imported by the app.
- `backups/code_backups/local_snapshots/` contains generated local snapshots
  and is ignored by Git.

Backup code must not be imported by the application. New temporary backups
should be placed under the ignored local snapshots folder rather than the
repository root.

### `data_sources/`

Contains the local MPPS and OVEN source workbooks. The directory and spreadsheet
files are ignored by Git because they are local source data. Import tools read
from this folder; cleanup tasks must not delete or overwrite it.

## Cleanup Decisions

The following reusable files were retained and moved:

- `load_excel_raw_to_db.py` and `map_raw_excel_to_clean_mpps.py` moved to
  `tools/importers/`.
- `check_mpps_mapping_quality.py` moved to `tools/diagnostics/`.
- `clean_dummy_data.py` moved to `tools/maintenance/`.
- Audit-log, Excel foundation, MPPS stock, priority, and tire-stock migration
  scripts moved to `database/migrations/`.
- MPPS and oven column-width scripts moved to `database/schema_fixes/`.
- Three tracked `*_before_*` source copies moved from `app/ui/` to
  `backups/code_backups/`.
- Existing ignored `backup_*` directories moved from the repository root to
  `backups/code_backups/local_snapshots/`.

The following completed one-time source patchers were removed because they were
not imported by the application and their resulting changes are already present
in the maintained source files:

- `connect_antigravity_pages_to_main_window.py`
- `connect_bead_master_page.py`
- `connect_bom_master_page.py`
- `connect_compound_master_page.py`
- `connect_product_master_page.py`
- `connect_stock_master_page.py`
- `fix_antigravity_page_imports.py`
- `fix_bead_master_column_name.py`
- `fix_mapper_duplicates.py`
- `fix_mapper_negative_values.py`
- `fix_product_master_table_polish.py`
- `fix_shipment_details_current_user.py`
- `fix_sidebar_polish.py`
- `fix_weight_column_mapping.py`
- `main_window_current.txt`

Runtime application files, source workbooks, environment files, documentation,
database models, services, planning logic, and Excel-derived calculations were
kept unchanged.

## Running the Application

From the project root:

```powershell
python run.py
```

The environment file, PostgreSQL service, and dependencies described in the
main `README.md` must be available.
