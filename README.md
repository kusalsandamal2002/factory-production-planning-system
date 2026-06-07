# MPPS Factory Production Planning System

Professional desktop application for Excel-derived factory production planning.
The system imports and traces MPPS and OVEN workbook data, converts shipment
demand and stock into production requirements, calculates material needs, and
supports quantity-based oven and mould/category capacity planning.

## Technology Stack

- Desktop UI: Python + PySide6
- Database: PostgreSQL
- ORM: SQLAlchemy
- Database driver: psycopg
- Future migration support: Alembic-ready project structure

## Current Planning Scope

The current application direction is driven by the structure and formulas found
in the MPPS and OVEN Excel workbooks:

- Finished-goods stock planning against shipment demand
- Production required quantity after available stock is considered
- Production required tons using Excel-derived product weights
- Compound, bead, and band material requirements
- Quantity-based oven planning
- Mould/category capacity planning
- Day/night production quantity allocation
- Shipment risk and shortage visibility
- Administrative data-quality review
- Raw workbook, worksheet, row, and cell traceability

Planning outputs retain source references so imported values and derived results
can be investigated against the original workbooks. See
[docs/excel_logic_discovery.md](docs/excel_logic_discovery.md) and
[docs/real_oven_planning_design.md](docs/real_oven_planning_design.md) for the
documented source logic and current planning design.

## Legacy Prototype Assumptions

The earlier prototype used hard-coded oven counts, Tire Type 1-5 curing times,
minute-based scheduling, fixed day/night hours, and a 20-minute production
break. Those assumptions are not the basis of the current Excel-derived
quantity planning workflow and must not be treated as current business rules.

Minute-level curing, changeover, downtime, and utilization planning would
require approved source master data that is not currently available in the
workbooks.

## Project Structure

Runtime application code is in `app/`. Database migrations, support tools,
documentation, source data, and retained backups are separated into dedicated
top-level folders. See [docs/project_structure.md](docs/project_structure.md)
for the complete layout and maintenance rules.

## How to Run

### 1. Install Python

Use Python 3.11 or later.

### 2. Create virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install packages

```bash
pip install -r requirements.txt
```

### 4. Start PostgreSQL

Install Docker Desktop, then run:

```bash
docker compose up -d
```

### 5. Create environment file

Copy `.env.example` to `.env`.

```bash
copy .env.example .env
```

### 6. Run the app

```bash
python run.py
```

## Development/Demo Login Details

These credentials are for local development or demonstration data only. They
must not be used in a production deployment.

```text
Admin:              admin / admin123
Operation Manager:  manager / manager123
Owner Viewer:       owner / owner123
```

## Data Safety

The following files contain local configuration, source data, or generated
database content and must not be committed:

- `.env`
- `data_sources/`
- Excel or CSV source files
- virtual environment folders such as `venv/` or `.venv/`
- database dumps, exports, or credential files

Use `.env.example` for documented configuration keys. Keep source workbook
files under the ignored `data_sources/` directory. Historical backup ownership
and storage rules are documented in
[backups/README.md](backups/README.md).
