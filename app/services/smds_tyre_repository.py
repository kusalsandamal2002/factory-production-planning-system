from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.database import engine
from app.services.smds_curing_time import (
    curing_cycle_to_minutes,
    ensure_smds_curing_time_columns,
    minutes_to_display_text,
    minutes_to_duration_text,
)
from app.services.smds_schema import ensure_smds_table


def guess_tyre_size(description: str) -> str:
    desc = re.sub(r"\s+", " ", str(description or "").strip())

    if not desc:
        return ""

    parts = desc.split()

    if not parts:
        return ""

    if len(parts) >= 2 and re.match(r"^\d+(\.\d+)?X\d+(\.\d+)?$", parts[0], re.I) and re.match(r"^\d+/\d+-\d+", parts[1]):
        return f"{parts[0]} {parts[1]}"

    if len(parts) >= 2 and re.match(r".*-\d+$", parts[0]) and re.fullmatch(r"\d+/\d+", parts[1]):
        return f"{parts[0]} {parts[1]}"

    return parts[0]


def _text_value(value: Any) -> str:
    return str(value or "").strip()


class TyreItemRepository:
    """Tyre Item Master data source backed by the central SMDS table.

    Analysis uses normal_curing_minutes as a numeric value.
    UI uses normal_curing_display / normal_curing_time_text for readability.
    """

    def ensure_table(self) -> None:
        ensure_smds_table()
        ensure_smds_curing_time_columns()

    def list_items(self, search_text: str = "") -> list[dict]:
        self.ensure_table()

        query = """
            SELECT
                id,
                sap_code,
                material_description AS description,
                line,
                key_code,
                casing_type,
                curing_cycle,
                normal_curing_minutes,
                normal_curing_time_text,
                handling_time,
                day_plan,
                night_plan,
                total_plan
            FROM smds
            WHERE 1 = 1
        """
        params: dict[str, object] = {}

        if search_text:
            query += """
                AND (
                    sap_code ILIKE :search
                    OR material_description ILIKE :search
                    OR COALESCE(key_code, '') ILIKE :search
                    OR COALESCE(casing_type, '') ILIKE :search
                    OR COALESCE(curing_cycle, '') ILIKE :search
                    OR COALESCE(line, '') ILIKE :search
                )
            """
            params["search"] = f"%{search_text}%"

        query += " ORDER BY sap_code"

        with engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()

        items: list[dict] = []
        for row in rows:
            item = dict(row)
            description = _text_value(item.get("description"))
            item["tyre_size"] = guess_tyre_size(description)

            minutes = item.get("normal_curing_minutes")
            if not minutes:
                minutes = curing_cycle_to_minutes(item.get("curing_cycle"))

            item["normal_curing_minutes"] = minutes
            item["normal_curing_time_text"] = item.get("normal_curing_time_text") or minutes_to_duration_text(minutes)
            item["normal_curing_display"] = minutes_to_display_text(minutes)
            item["short_cycle_curing_minutes"] = 0
            item["handling_minutes"] = item.get("handling_time") or 0
            item["status"] = "Active"
            items.append(item)

        return items

    def create_item(self, sap_code: str, description: str) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO smds (sap_code, material_description, source_file, source_sheet)
                    VALUES (:sap_code, :description, 'APP_MANUAL', 'Tyre Item Master')
                    ON CONFLICT (sap_code) DO UPDATE SET
                        material_description = EXCLUDED.material_description,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {"sap_code": sap_code, "description": description},
            )

    def update_item(self, item_id: int, sap_code: str, description: str) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE smds
                    SET sap_code = :sap_code,
                        material_description = :description,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": item_id, "sap_code": sap_code, "description": description},
            )

    def delete_item(self, item_id: int) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(text("DELETE FROM smds WHERE id = :id"), {"id": item_id})

# MPPS V32 FAST READ PATH
def _v32_fast_list_items(self, search_text: str = "") -> list[dict]:
    """Pure SELECT read path. No DDL/schema migration is allowed here."""
    query = """
        SELECT
            id,
            sap_code,
            material_description AS description,
            line,
            key_code,
            casing_type,
            curing_cycle,
            normal_curing_minutes,
            normal_curing_time_text,
            handling_time,
            day_plan,
            night_plan,
            total_plan
        FROM smds
        WHERE 1=1
    """
    params: dict[str, object] = {}

    if search_text:
        query += """
            AND (
                sap_code ILIKE :search
                OR material_description ILIKE :search
                OR COALESCE(key_code, '') ILIKE :search
                OR COALESCE(casing_type, '') ILIKE :search
                OR COALESCE(curing_cycle, '') ILIKE :search
                OR COALESCE(line, '') ILIKE :search
            )
        """
        params["search"] = f"%{search_text}%"

    query += " ORDER BY sap_code LIMIT 3000"

    with engine.connect() as conn:
        rows = conn.execute(
            text(query),
            params,
        ).mappings().all()

    items: list[dict] = []

    for row in rows:
        item = dict(row)
        description = _text_value(
            item.get("description")
        )
        item["tyre_size"] = guess_tyre_size(
            description
        )

        minutes = item.get(
            "normal_curing_minutes"
        )
        if not minutes:
            minutes = curing_cycle_to_minutes(
                item.get("curing_cycle")
            )

        item["normal_curing_minutes"] = minutes
        item["normal_curing_time_text"] = (
            item.get("normal_curing_time_text")
            or minutes_to_duration_text(minutes)
        )
        item["normal_curing_display"] = (
            minutes_to_display_text(minutes)
        )
        item["short_cycle_curing_minutes"] = 0
        item["handling_minutes"] = (
            item.get("handling_time") or 0
        )
        item["status"] = "Active"
        items.append(item)

    return items


TyreItemRepository.list_items = _v32_fast_list_items
