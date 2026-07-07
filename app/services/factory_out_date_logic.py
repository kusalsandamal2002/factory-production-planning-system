from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from sqlalchemy import text

from app.database import engine


OPEN_SHIPMENT_STATUSES = {"planned", "pending", "open", "saved", "in progress", "processing"}
CLOSED_SHIPMENT_STATUSES = {"cancelled", "canceled", "closed", "complete", "completed", "shipped", "done"}
NO_CASING_VALUES = {"", "-", "no casing", "none", "n/a", "na", "not required"}


@dataclass
class FactoryOutItemResult:
    sap_code: str
    description: str
    order_qty: int
    stock_allocated_qty: int
    production_required_qty: int
    allocated_cavity_count: int
    daily_capacity: int
    production_days: int
    receive_date: date | None
    status: str
    reason: str
    mold_key_code: str = ""
    casing_type: str = ""
    line: str = ""
    smds_total_plan: int = 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.receive_date is not None:
            data["receive_date"] = self.receive_date.isoformat()
        return data


class FactoryOutDateCalculator:
    """Factory-out-date calculator used by Shipment Entry.

    This implementation follows the current business rule:
      1) Approved SMDS items only.
      2) Allocate unallocated finished stock before production.
      3) Balance quantity uses SMDS Total Plan as daily per-cavity capacity.
      4) Allocated cavities are limited by mold, casing and line/cavity availability.
      5) Item receive date is calculated per cart item; shipment date is latest item date.
    """

    def __init__(self, start_date: date | None = None) -> None:
        self.start_date = start_date or date.today()

    # ----------------------------- schema helpers -----------------------------
    def ensure_schema(self) -> None:
        with engine.begin() as conn:
            # Shipment compatibility columns. Existing columns are not removed.
            conn.execute(text("ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS shipment_name TEXT NOT NULL DEFAULT ''"))
            conn.execute(text("ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_out_date DATE"))
            conn.execute(text("ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_out_status VARCHAR(80) NOT NULL DEFAULT ''"))
            conn.execute(text("ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_out_note TEXT NOT NULL DEFAULT ''"))

            conn.execute(text("ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS stock_allocated_qty INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_required_qty INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS allocated_cavity_count INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS daily_capacity INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_days INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS receive_date DATE"))
            conn.execute(text("ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS factory_out_reason TEXT NOT NULL DEFAULT ''"))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shipment_stock_allocations (
                    id BIGSERIAL PRIMARY KEY,
                    shipment_id INTEGER NOT NULL REFERENCES mpps_shipments(id) ON DELETE CASCADE,
                    shipment_item_id INTEGER REFERENCES mpps_shipment_items(id) ON DELETE CASCADE,
                    sap_code VARCHAR(100) NOT NULL,
                    allocated_stock_qty INTEGER NOT NULL DEFAULT 0,
                    production_required_qty INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

    def table_exists(self, conn, table_name: str) -> bool:
        try:
            return bool(conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
            """), {"table_name": table_name}).scalar())
        except Exception:
            return False

    def column_exists(self, conn, table_name: str, column_name: str) -> bool:
        try:
            return bool(conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                      AND column_name = :column_name
                )
            """), {"table_name": table_name, "column_name": column_name}).scalar())
        except Exception:
            return False

    # ----------------------------- public methods -----------------------------
    def calculate_cart_items(
        self,
        cart_items: list[dict[str, Any]],
        exclude_shipment_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Calculate and enrich every cart item sequentially.

        Sequential stock consumption ensures that two cart rows of the same SAP code
        do not use the same finished stock twice.
        """
        self.ensure_schema()
        stock_remaining_by_sap: dict[str, int] = {}
        results: list[dict[str, Any]] = []

        with engine.begin() as conn:
            for source_item in cart_items:
                sap_code = str(source_item.get("sap_code") or "").strip()
                qty = self._int(source_item.get("quantity"), 0)

                if not sap_code or qty <= 0:
                    enriched = dict(source_item)
                    enriched.update(FactoryOutItemResult(
                        sap_code=sap_code,
                        description=str(source_item.get("item_description") or ""),
                        order_qty=max(qty, 0),
                        stock_allocated_qty=0,
                        production_required_qty=max(qty, 0),
                        allocated_cavity_count=0,
                        daily_capacity=0,
                        production_days=0,
                        receive_date=None,
                        status="Blocked",
                        reason="Invalid SAP code or quantity.",
                    ).to_dict())
                    results.append(enriched)
                    continue

                if sap_code not in stock_remaining_by_sap:
                    stock_remaining_by_sap[sap_code] = self._available_unallocated_stock(conn, sap_code, exclude_shipment_id)

                result = self._calculate_one_item(conn, source_item, stock_remaining_by_sap[sap_code])
                stock_remaining_by_sap[sap_code] = max(0, stock_remaining_by_sap[sap_code] - result.stock_allocated_qty)

                enriched = dict(source_item)
                enriched.update(result.to_dict())
                # Keep historical key used by OrderEntryPage.
                enriched["item_description"] = result.description or str(source_item.get("item_description") or "")
                enriched["quantity"] = result.order_qty
                results.append(enriched)

        return results

    def final_shipment_date(self, cart_items: list[dict[str, Any]]) -> date | None:
        dates: list[date] = []
        for item in cart_items:
            value = item.get("receive_date")
            parsed = self._date(value)
            if parsed is not None:
                dates.append(parsed)
        return max(dates) if dates else None

    # ----------------------------- item logic -----------------------------
    def _calculate_one_item(self, conn, item: dict[str, Any], available_stock: int) -> FactoryOutItemResult:
        sap_code = str(item.get("sap_code") or "").strip()
        order_qty = max(0, self._int(item.get("quantity"), 0))
        smds = self._load_smds_item(conn, sap_code)

        description = str(item.get("item_description") or "")
        if smds:
            description = str(smds.get("material_description") or smds.get("tyre_description") or description)

        if not smds:
            return FactoryOutItemResult(
                sap_code=sap_code,
                description=description,
                order_qty=order_qty,
                stock_allocated_qty=0,
                production_required_qty=order_qty,
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                receive_date=None,
                status="Blocked",
                reason="SMDS item data not found.",
            )

        approval = self._norm(str(smds.get("planning_manager_approval_status") or "Pending"))
        if approval != "approved":
            return FactoryOutItemResult(
                sap_code=sap_code,
                description=description,
                order_qty=order_qty,
                stock_allocated_qty=0,
                production_required_qty=order_qty,
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                receive_date=None,
                status="Blocked",
                reason="Planning Manager Approval Status is not Approved.",
                mold_key_code=str(smds.get("key_code") or ""),
                casing_type=str(smds.get("casing_type") or ""),
                line=str(smds.get("line") or ""),
                smds_total_plan=self._int(smds.get("total_plan"), 0),
            )

        stock_alloc = min(order_qty, max(0, available_stock))
        balance_qty = max(0, order_qty - stock_alloc)

        mold_key = str(smds.get("key_code") or "").strip()
        casing_type = str(smds.get("casing_type") or "").strip()
        line = str(smds.get("line") or "").strip()
        total_plan = max(0, self._int(smds.get("total_plan"), 0))

        if balance_qty <= 0:
            return FactoryOutItemResult(
                sap_code=sap_code,
                description=description,
                order_qty=order_qty,
                stock_allocated_qty=stock_alloc,
                production_required_qty=0,
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                receive_date=self.start_date,
                status="Stock Ready",
                reason="Order quantity covered by unallocated finished stock.",
                mold_key_code=mold_key,
                casing_type=casing_type,
                line=line,
                smds_total_plan=total_plan,
            )

        if total_plan <= 0:
            return FactoryOutItemResult(
                sap_code=sap_code,
                description=description,
                order_qty=order_qty,
                stock_allocated_qty=stock_alloc,
                production_required_qty=balance_qty,
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                receive_date=None,
                status="Blocked",
                reason="SMDS Total Plan is missing or zero.",
                mold_key_code=mold_key,
                casing_type=casing_type,
                line=line,
                smds_total_plan=total_plan,
            )

        resource = self._allocated_cavity_count(conn, mold_key, casing_type, line)
        cavities = int(resource["allocated_cavity_count"])
        if cavities <= 0:
            return FactoryOutItemResult(
                sap_code=sap_code,
                description=description,
                order_qty=order_qty,
                stock_allocated_qty=stock_alloc,
                production_required_qty=balance_qty,
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                receive_date=None,
                status="Blocked",
                reason=resource["reason"],
                mold_key_code=mold_key,
                casing_type=casing_type,
                line=line,
                smds_total_plan=total_plan,
            )

        daily_capacity = max(0, total_plan * cavities)
        if daily_capacity <= 0:
            production_days = 0
            receive_date = None
            status = "Blocked"
            reason = "Daily production capacity is zero."
        else:
            production_days = int(ceil(balance_qty / daily_capacity))
            receive_date = self.start_date + timedelta(days=max(0, production_days - 1))
            status = "Calculated"
            reason = (
                f"Stock {stock_alloc}; production {balance_qty}; "
                f"capacity {total_plan} × {cavities} cavities = {daily_capacity}/day."
            )

        return FactoryOutItemResult(
            sap_code=sap_code,
            description=description,
            order_qty=order_qty,
            stock_allocated_qty=stock_alloc,
            production_required_qty=balance_qty,
            allocated_cavity_count=cavities,
            daily_capacity=daily_capacity,
            production_days=production_days,
            receive_date=receive_date,
            status=status,
            reason=reason,
            mold_key_code=mold_key,
            casing_type=casing_type,
            line=line,
            smds_total_plan=total_plan,
        )

    # ----------------------------- data loaders -----------------------------
    def _load_smds_item(self, conn, sap_code: str) -> dict[str, Any] | None:
        if not self.table_exists(conn, "smds"):
            return None

        # Keep query conservative: these columns are created by previous SMDS updates.
        sql = """
            SELECT
                sap_code,
                material_description,
                COALESCE(line, '') AS line,
                COALESCE(key_code, '') AS key_code,
                COALESCE(casing_type, '') AS casing_type,
                COALESCE(day_plan, 0) AS day_plan,
                COALESCE(night_plan, 0) AS night_plan,
                COALESCE(total_plan, 0) AS total_plan,
                COALESCE(planning_manager_approval_status, 'Pending') AS planning_manager_approval_status
            FROM smds
            WHERE TRIM(sap_code) = :sap_code
            LIMIT 1
        """
        try:
            row = conn.execute(text(sql), {"sap_code": sap_code}).mappings().first()
            return dict(row) if row else None
        except Exception:
            # Some old installs may not yet have approval/status columns.
            try:
                row = conn.execute(text("""
                    SELECT
                        sap_code,
                        material_description,
                        COALESCE(line, '') AS line,
                        COALESCE(key_code, '') AS key_code,
                        COALESCE(casing_type, '') AS casing_type,
                        COALESCE(day_plan, 0) AS day_plan,
                        COALESCE(night_plan, 0) AS night_plan,
                        COALESCE(total_plan, 0) AS total_plan,
                        'Pending' AS planning_manager_approval_status
                    FROM smds
                    WHERE TRIM(sap_code) = :sap_code
                    LIMIT 1
                """), {"sap_code": sap_code}).mappings().first()
                return dict(row) if row else None
            except Exception:
                return None

    def _available_unallocated_stock(self, conn, sap_code: str, exclude_shipment_id: int | None = None) -> int:
        current_stock = self._current_available_stock(conn, sap_code)
        allocated = self._already_allocated_stock(conn, sap_code, exclude_shipment_id)
        return max(0, current_stock - allocated)

    def _current_available_stock(self, conn, sap_code: str) -> int:
        if not self.table_exists(conn, "mpps_sap_stock_items"):
            return 0
        try:
            row = conn.execute(text("""
                SELECT COALESCE(fg_stock, 0) + COALESCE(qc_stock, 0)
                     - COALESCE(scrap_stock, 0) - COALESCE(blocked_stock, 0) AS available_stock
                FROM mpps_sap_stock_items
                WHERE TRIM(sap_code) = :sap_code
                LIMIT 1
            """), {"sap_code": sap_code}).mappings().first()
            return max(0, self._int(row["available_stock"] if row else 0, 0))
        except Exception:
            return 0

    def _already_allocated_stock(self, conn, sap_code: str, exclude_shipment_id: int | None = None) -> int:
        if not self.table_exists(conn, "mpps_shipment_items") or not self.table_exists(conn, "mpps_shipments"):
            return 0
        params: dict[str, Any] = {"sap_code": sap_code}
        exclude_clause = ""
        if exclude_shipment_id is not None:
            exclude_clause = "AND s.id <> :exclude_shipment_id"
            params["exclude_shipment_id"] = exclude_shipment_id
        try:
            return max(0, self._int(conn.execute(text(f"""
                SELECT COALESCE(SUM(i.stock_allocated_qty), 0)
                FROM mpps_shipment_items i
                JOIN mpps_shipments s ON s.id = i.shipment_id
                WHERE TRIM(i.sap_code) = :sap_code
                  {exclude_clause}
                  AND LOWER(COALESCE(s.status, 'planned')) NOT IN ('cancelled', 'canceled', 'closed', 'complete', 'completed', 'shipped', 'done')
            """), params).scalar(), 0))
        except Exception:
            return 0

    def _allocated_cavity_count(self, conn, mold_key: str, casing_type: str, line_text: str) -> dict[str, Any]:
        mold_count = self._available_mold_count(conn, mold_key)
        if mold_count <= 0:
            return {"allocated_cavity_count": 0, "reason": "Mold is not available for this item."}

        casing_required = self._casing_required(casing_type)
        if casing_required:
            casing_count = self._available_casing_count(conn, casing_type)
            if casing_count <= 0:
                return {"allocated_cavity_count": 0, "reason": "Casing is not available for this item."}
        else:
            casing_count = 10**9

        line_cavities = self._available_line_cavity_count(conn, line_text)
        if line_cavities <= 0:
            return {"allocated_cavity_count": 0, "reason": "No free line/cavity is available for this item."}

        allocated = min(mold_count, casing_count, line_cavities)
        return {"allocated_cavity_count": max(0, int(allocated)), "reason": "Resources available."}

    def _available_mold_count(self, conn, mold_key: str) -> int:
        if not mold_key or self._norm(mold_key) in {"", "-"}:
            return 0
        if not self.table_exists(conn, "mold_master"):
            return 0
        try:
            value = conn.execute(text("""
                SELECT COALESCE(SUM(mold_count), 0)
                FROM mold_master
                WHERE LOWER(TRIM(mold_key_code)) = LOWER(TRIM(:mold_key))
                  AND LOWER(COALESCE(status, 'Active')) = 'active'
            """), {"mold_key": mold_key}).scalar()
            return max(0, self._int(value, 0))
        except Exception:
            return 0

    def _available_casing_count(self, conn, casing_type: str) -> int:
        if not self._casing_required(casing_type):
            return 10**9
        if self.table_exists(conn, "casing_units"):
            try:
                value = conn.execute(text("""
                    SELECT COUNT(*)
                    FROM casing_units
                    WHERE LOWER(TRIM(casing_type)) = LOWER(TRIM(:casing_type))
                      AND LOWER(COALESCE(condition_status, 'Active')) = 'active'
                      AND LOWER(COALESCE(stock_status, 'Free')) = 'free'
                """), {"casing_type": casing_type}).scalar()
                count = self._int(value, 0)
                if count > 0:
                    return count
            except Exception:
                pass
        if self.table_exists(conn, "casing_master"):
            try:
                value = conn.execute(text("""
                    SELECT COALESCE(SUM(available_casing_count), 0)
                    FROM casing_master
                    WHERE LOWER(TRIM(casing_type)) = LOWER(TRIM(:casing_type))
                      AND LOWER(COALESCE(status, 'Active')) = 'active'
                """), {"casing_type": casing_type}).scalar()
                return max(0, self._int(value, 0))
            except Exception:
                return 0
        return 0

    def _available_line_cavity_count(self, conn, line_text: str) -> int:
        if not self.table_exists(conn, "production_line_cavities"):
            return 0
        lines = self._parse_lines(line_text)
        if not lines:
            return 0
        total = 0
        for line in lines:
            try:
                value = conn.execute(text("""
                    SELECT COUNT(*)
                    FROM production_line_cavities
                    WHERE LOWER(TRIM(line_name)) = LOWER(TRIM(:line_name))
                      AND LOWER(COALESCE(status, 'Active')) = 'active'
                      AND TRIM(COALESCE(assigned_tyre_item, '')) = ''
                """), {"line_name": line}).scalar()
                total += self._int(value, 0)
            except Exception:
                pass
        return max(0, total)

    # ----------------------------- utils -----------------------------
    def _parse_lines(self, value: Any) -> list[str]:
        text_value = str(value or "").replace(";", ",").replace("|", ",")
        parts = [p.strip() for p in text_value.split(",")]
        return [p for p in parts if p and p != "-"]

    def _casing_required(self, casing_type: str) -> bool:
        return self._norm(casing_type) not in NO_CASING_VALUES

    def _norm(self, value: str) -> str:
        return " ".join(str(value or "").strip().lower().split())

    def _int(self, value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            if isinstance(value, Decimal):
                return int(value)
            return int(float(str(value).replace(",", "").strip()))
        except Exception:
            return default

    def _date(self, value: Any) -> date | None:
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None
