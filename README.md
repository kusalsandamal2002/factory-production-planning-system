# Factory Oven Production Planning System

Professional desktop prototype for factory oven capacity planning, customer order entry, live company receive-date calculation, operation manager confirmation, and daily oven schedule control.

## Technology Stack

- Desktop UI: Python + PySide6
- Database: PostgreSQL
- ORM: SQLAlchemy
- Database driver: psycopg
- Future migration support: Alembic-ready project structure

## Business Rules Included

1. Factory has 25 ovens.
2. Tire type curing times:
   - Tire Type 1: 30 minutes
   - Tire Type 2: 45 minutes
   - Tire Type 3: 90 minutes
   - Tire Type 4: 180 minutes
   - Tire Type 5: 300 minutes
3. Day shift max work time: 10 hours.
4. Night shift max work time: 8 hours.
5. Break between two tire productions: 20 minutes.
6. One customer order can contain multiple tire types.
7. Company Can Receive Date is calculated live while tire quantities are added.
8. Operation manager must confirm the receive date before order is saved.
9. Manager confirmed date cannot be earlier than the system calculated date.
10. Existing production capacity is considered before scheduling a new order.
11. Free oven capacity is used while other orders are still in production.
12. Daily oven schedule can be manually changed by operation manager.
13. Manual changes are saved in schedule change log.

## Current Shift Time Assumption

Because exact clock times were not provided, the prototype uses these editable master data values:

- Day Shift: 08:00 to 18:00
- Night Shift: 20:00 to 04:00

These values are stored in the PostgreSQL `shifts` table and can be changed later.

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

## Demo Login Details

```text
Admin:              admin / admin123
Operation Manager:  manager / manager123
Owner Viewer:       owner / owner123
```

## Owner Demo Flow

1. Login as `manager / manager123`.
2. Open `New Order`.
3. Select a customer.
4. Add Tire Type 1 quantity.
5. Watch Company Can Receive Date update.
6. Add Tire Type 3 and Tire Type 5 quantities.
7. The Company Can Receive Date moves forward based on total oven capacity.
8. Manager selects a confirmed receive date on or after the calculated date.
9. Click `Confirm & Save Order`.
10. Open `Daily Oven Schedule` to view assigned ovens, shift, start time, end time, and break slots.
11. Select a schedule row and test a manual change with a reason.

## Important Notes

This is a professional prototype using the final database approach. It is not a toy web demo.
The database model can be expanded later for:

- stock balance
- raw material availability
- machine maintenance
- production approval workflow
- Excel/PDF reports
- audit log dashboard
- shipment and delivery tracking
