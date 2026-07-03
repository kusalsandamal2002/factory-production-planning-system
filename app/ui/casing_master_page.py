from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _code_prefix(casing_type: str) -> str:
    prefix = re.sub(r"[^A-Z0-9]+", "-", _clean(casing_type).upper()).strip("-")
    return prefix or "CASING"


def _unit_code(casing_type: str, casing_no: int) -> str:
    return f"{_code_prefix(casing_type)}-{casing_no:03d}"


class CasingRepository:
    def __init__(self) -> None:
        self.ensure_table()

    def ensure_table(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS casing_master (
                    id BIGSERIAL PRIMARY KEY,
                    casing_type VARCHAR(255) NOT NULL UNIQUE,
                    available_casing_count INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS casing_units (
                    id BIGSERIAL PRIMARY KEY,
                    casing_type VARCHAR(255) NOT NULL,
                    casing_no INTEGER NOT NULL,
                    casing_code VARCHAR(255) NOT NULL,
                    condition_status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    stock_status VARCHAR(32) NOT NULL DEFAULT 'Free',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_casing_units_type_no
                ON casing_units (casing_type, casing_no)
            """))

            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_casing_units_type_code
                ON casing_units (casing_type, casing_code)
            """))

        self.ensure_units_from_counts()

    def ensure_units_from_counts(self) -> None:
        with engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT casing_type, available_casing_count
                FROM casing_master
                WHERE casing_type IS NOT NULL
                  AND TRIM(casing_type) <> ''
                  AND LOWER(TRIM(casing_type)) <> 'no casing'
                ORDER BY casing_type
            """)).mappings().all()

            for row in rows:
                casing_type = row["casing_type"]
                target_count = int(row["available_casing_count"] or 0)

                if target_count <= 0:
                    continue

                existing_numbers = {
                    int(item["casing_no"])
                    for item in conn.execute(
                        text("""
                            SELECT casing_no
                            FROM casing_units
                            WHERE casing_type = :casing_type
                        """),
                        {"casing_type": casing_type},
                    ).mappings().all()
                }

                for casing_no in range(1, target_count + 1):
                    if casing_no in existing_numbers:
                        continue

                    conn.execute(
                        text("""
                            INSERT INTO casing_units (
                                casing_type,
                                casing_no,
                                casing_code,
                                condition_status,
                                stock_status,
                                remarks,
                                updated_at
                            )
                            VALUES (
                                :casing_type,
                                :casing_no,
                                :casing_code,
                                'Active',
                                'Free',
                                '',
                                CURRENT_TIMESTAMP
                            )
                        """),
                        {
                            "casing_type": casing_type,
                            "casing_no": casing_no,
                            "casing_code": _unit_code(casing_type, casing_no),
                        },
                    )

                self._sync_count_for_type(conn, casing_type)

    def _sync_count_for_type(self, conn, casing_type: str) -> None:
        conn.execute(
            text("""
                UPDATE casing_master
                SET available_casing_count = (
                        SELECT COUNT(*)
                        FROM casing_units
                        WHERE casing_type = :casing_type
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE casing_type = :casing_type
            """),
            {"casing_type": casing_type},
        )

    def overview_stats(self) -> dict:
        with engine.connect() as conn:
            return dict(conn.execute(text("""
                SELECT
                    COALESCE((
                        SELECT COUNT(*)
                        FROM casing_master
                        WHERE LOWER(TRIM(casing_type)) <> 'no casing'
                    ), 0) AS total_types,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM casing_units
                    ), 0) AS total_units,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM casing_units
                        WHERE condition_status = 'Active'
                          AND stock_status = 'Free'
                    ), 0) AS free_units,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM casing_units
                        WHERE condition_status = 'Breakdown'
                    ), 0) AS breakdown_units,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM casing_units
                        WHERE stock_status = 'In Use'
                    ), 0) AS in_use_units
            """)).mappings().one())

    def list_types(self, search_text: str = "") -> list[dict]:
        search = (search_text or "").strip().lower()

        sql = """
            WITH unit_summary AS (
                SELECT
                    casing_type,
                    COUNT(*) AS total_units,
                    COUNT(*) FILTER (
                        WHERE condition_status = 'Active'
                          AND stock_status = 'Free'
                    ) AS free_units,
                    COUNT(*) FILTER (
                        WHERE condition_status = 'Breakdown'
                    ) AS breakdown_units,
                    COUNT(*) FILTER (
                        WHERE stock_status = 'In Use'
                    ) AS in_use_units
                FROM casing_units
                GROUP BY casing_type
            )
            SELECT
                c.id,
                c.casing_type,
                c.remarks,
                COALESCE(u.total_units, 0) AS total_units,
                COALESCE(u.free_units, 0) AS free_units,
                COALESCE(u.breakdown_units, 0) AS breakdown_units,
                COALESCE(u.in_use_units, 0) AS in_use_units
            FROM casing_master c
            LEFT JOIN unit_summary u ON u.casing_type = c.casing_type
            WHERE LOWER(TRIM(c.casing_type)) <> 'no casing'
        """

        params = {}

        if search:
            sql += """
              AND (
                    LOWER(c.casing_type) LIKE :search
                 OR LOWER(c.remarks) LIKE :search
              )
            """
            params["search"] = f"%{search}%"

        sql += " ORDER BY c.casing_type"

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    def type_stats(self, casing_type: str) -> dict:
        with engine.connect() as conn:
            return dict(conn.execute(text("""
                SELECT
                    COUNT(*) AS total_units,
                    COUNT(*) FILTER (WHERE condition_status = 'Active') AS active_units,
                    COUNT(*) FILTER (WHERE condition_status = 'Breakdown') AS breakdown_units,
                    COUNT(*) FILTER (
                        WHERE condition_status = 'Active'
                          AND stock_status = 'Free'
                    ) AS free_units,
                    COUNT(*) FILTER (WHERE stock_status = 'In Use') AS in_use_units,
                    COUNT(*) FILTER (WHERE stock_status = 'Reserved') AS reserved_units
                FROM casing_units
                WHERE casing_type = :casing_type
            """), {"casing_type": casing_type}).mappings().one())

    def get_type(self, casing_type: str) -> dict:
        with engine.connect() as conn:
            return dict(conn.execute(text("""
                SELECT id, casing_type, available_casing_count, remarks
                FROM casing_master
                WHERE casing_type = :casing_type
            """), {"casing_type": casing_type}).mappings().one())

    def add_type(self, casing_type: str, initial_count: int, remarks: str) -> None:
        casing_type = _clean(casing_type)

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO casing_master (
                        casing_type,
                        available_casing_count,
                        status,
                        remarks,
                        updated_at
                    )
                    VALUES (
                        :casing_type,
                        0,
                        'Active',
                        :remarks,
                        CURRENT_TIMESTAMP
                    )
                """),
                {
                    "casing_type": casing_type,
                    "remarks": remarks,
                },
            )

            for _ in range(max(0, int(initial_count))):
                self._add_one_unit(conn, casing_type)

            self._sync_count_for_type(conn, casing_type)

    def rename_type(self, old_type: str, new_type: str, remarks: str) -> None:
        old_type = _clean(old_type)
        new_type = _clean(new_type)

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE casing_master
                    SET casing_type = :new_type,
                        remarks = :remarks,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE casing_type = :old_type
                """),
                {
                    "old_type": old_type,
                    "new_type": new_type,
                    "remarks": remarks,
                },
            )

            unit_rows = conn.execute(
                text("""
                    SELECT id, casing_no
                    FROM casing_units
                    WHERE casing_type = :old_type
                    ORDER BY casing_no
                """),
                {"old_type": old_type},
            ).mappings().all()

            for row in unit_rows:
                conn.execute(
                    text("""
                        UPDATE casing_units
                        SET casing_type = :new_type,
                            casing_code = :casing_code,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                    """),
                    {
                        "id": row["id"],
                        "new_type": new_type,
                        "casing_code": _unit_code(new_type, int(row["casing_no"])),
                    },
                )

            conn.execute(
                text("""
                    UPDATE mold_master
                    SET casing_type = :new_type,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE casing_type = :old_type
                """),
                {
                    "old_type": old_type,
                    "new_type": new_type,
                },
            )

            self._sync_count_for_type(conn, new_type)

    def delete_type(self, casing_type: str) -> None:
        casing_type = _clean(casing_type)

        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM casing_units WHERE casing_type = :casing_type"),
                {"casing_type": casing_type},
            )
            conn.execute(
                text("DELETE FROM casing_master WHERE casing_type = :casing_type"),
                {"casing_type": casing_type},
            )

    def list_units(self, casing_type: str, search_text: str = "") -> list[dict]:
        search = (search_text or "").strip().lower()

        sql = """
            SELECT
                id,
                casing_type,
                casing_no,
                casing_code,
                condition_status,
                stock_status,
                remarks
            FROM casing_units
            WHERE casing_type = :casing_type
        """

        params = {"casing_type": casing_type}

        if search:
            sql += """
                AND (
                    LOWER(casing_code) LIKE :search
                    OR LOWER(condition_status) LIKE :search
                    OR LOWER(stock_status) LIKE :search
                    OR LOWER(remarks) LIKE :search
                )
            """
            params["search"] = f"%{search}%"

        sql += """
            ORDER BY
                CASE WHEN condition_status = 'Breakdown' THEN 0 ELSE 1 END,
                casing_no
        """

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    def get_unit(self, unit_id: int) -> dict:
        with engine.connect() as conn:
            return dict(conn.execute(text("""
                SELECT
                    id,
                    casing_type,
                    casing_no,
                    casing_code,
                    condition_status,
                    stock_status,
                    remarks
                FROM casing_units
                WHERE id = :id
            """), {"id": unit_id}).mappings().one())

    def add_units(self, casing_type: str, qty: int) -> None:
        casing_type = _clean(casing_type)
        qty = max(1, int(qty))

        with engine.begin() as conn:
            for _ in range(qty):
                self._add_one_unit(conn, casing_type)

            self._sync_count_for_type(conn, casing_type)

    def _add_one_unit(self, conn, casing_type: str) -> None:
        max_no = conn.execute(
            text("""
                SELECT COALESCE(MAX(casing_no), 0)
                FROM casing_units
                WHERE casing_type = :casing_type
            """),
            {"casing_type": casing_type},
        ).scalar_one()

        casing_no = int(max_no or 0) + 1

        conn.execute(
            text("""
                INSERT INTO casing_units (
                    casing_type,
                    casing_no,
                    casing_code,
                    condition_status,
                    stock_status,
                    remarks,
                    updated_at
                )
                VALUES (
                    :casing_type,
                    :casing_no,
                    :casing_code,
                    'Active',
                    'Free',
                    '',
                    CURRENT_TIMESTAMP
                )
            """),
            {
                "casing_type": casing_type,
                "casing_no": casing_no,
                "casing_code": _unit_code(casing_type, casing_no),
            },
        )

    def update_unit(self, unit_id: int, data: dict) -> None:
        with engine.begin() as conn:
            unit = conn.execute(
                text("""
                    SELECT casing_type
                    FROM casing_units
                    WHERE id = :id
                """),
                {"id": unit_id},
            ).mappings().one()

            conn.execute(
                text("""
                    UPDATE casing_units
                    SET casing_code = :casing_code,
                        condition_status = :condition_status,
                        stock_status = :stock_status,
                        remarks = :remarks,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": unit_id, **data},
            )

            self._sync_count_for_type(conn, unit["casing_type"])

    def update_unit_condition(self, unit_id: int, condition_status: str) -> None:
        with engine.begin() as conn:
            unit = conn.execute(
                text("""
                    SELECT casing_type
                    FROM casing_units
                    WHERE id = :id
                """),
                {"id": unit_id},
            ).mappings().one()

            conn.execute(
                text("""
                    UPDATE casing_units
                    SET condition_status = :condition_status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {
                    "id": unit_id,
                    "condition_status": condition_status,
                },
            )

            self._sync_count_for_type(conn, unit["casing_type"])

    def update_unit_stock(self, unit_id: int, stock_status: str) -> None:
        with engine.begin() as conn:
            unit = conn.execute(
                text("""
                    SELECT casing_type
                    FROM casing_units
                    WHERE id = :id
                """),
                {"id": unit_id},
            ).mappings().one()

            conn.execute(
                text("""
                    UPDATE casing_units
                    SET stock_status = :stock_status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {
                    "id": unit_id,
                    "stock_status": stock_status,
                },
            )

            self._sync_count_for_type(conn, unit["casing_type"])

    def delete_unit(self, unit_id: int) -> str:
        with engine.begin() as conn:
            unit = conn.execute(
                text("""
                    SELECT casing_type
                    FROM casing_units
                    WHERE id = :id
                """),
                {"id": unit_id},
            ).mappings().one()

            casing_type = unit["casing_type"]

            conn.execute(text("DELETE FROM casing_units WHERE id = :id"), {"id": unit_id})
            self._sync_count_for_type(conn, casing_type)

            return casing_type


class CasingTypeDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        casing_type: str = "",
        remarks: str = "",
        allow_initial_count: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.allow_initial_count = allow_initial_count

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.casing_type_input = QLineEdit(casing_type)
        self.casing_type_input.setPlaceholderText("Example: B2 / B5 / B5 Special 02")

        self.initial_count_input = QSpinBox()
        self.initial_count_input.setRange(0, 100000)
        self.initial_count_input.setValue(0)

        self.remarks_input = QTextEdit(remarks or "")
        self.remarks_input.setFixedHeight(90)

        form.addRow("Casing Type", self.casing_type_input)

        if self.allow_initial_count:
            form.addRow("Initial Unit Count", self.initial_count_input)

        form.addRow("Remarks", self.remarks_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def data(self) -> dict:
        return {
            "casing_type": self.casing_type_input.text().strip(),
            "initial_count": int(self.initial_count_input.value()) if self.allow_initial_count else 0,
            "remarks": self.remarks_input.toPlainText().strip(),
        }


class AddUnitsDialog(QDialog):
    def __init__(self, parent: QWidget, casing_type: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Add Casing Units - {casing_type}")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        form = QFormLayout()
        self.qty_input = QSpinBox()
        self.qty_input.setRange(1, 10000)
        self.qty_input.setValue(1)

        form.addRow("Number of Units to Add", self.qty_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def qty(self) -> int:
        return int(self.qty_input.value())


class CasingUnitDialog(QDialog):
    def __init__(self, parent: QWidget, unit: dict) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit {unit.get('casing_code', 'Casing Unit')}")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.code_input = QLineEdit(str(unit.get("casing_code", "") or ""))

        self.condition_input = QComboBox()
        self.condition_input.addItems(["Active", "Breakdown"])
        self.condition_input.setCurrentText(str(unit.get("condition_status", "Active") or "Active"))

        self.stock_input = QComboBox()
        self.stock_input.addItems(["Free", "In Use", "Reserved"])
        self.stock_input.setCurrentText(str(unit.get("stock_status", "Free") or "Free"))

        self.remarks_input = QTextEdit(str(unit.get("remarks", "") or ""))
        self.remarks_input.setFixedHeight(90)

        form.addRow("Casing Code", self.code_input)
        form.addRow("Condition", self.condition_input)
        form.addRow("Stock Status", self.stock_input)
        form.addRow("Remarks", self.remarks_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def data(self) -> dict:
        return {
            "casing_code": self.code_input.text().strip(),
            "condition_status": self.condition_input.currentText(),
            "stock_status": self.stock_input.currentText(),
            "remarks": self.remarks_input.toPlainText().strip(),
        }


class CasingMasterPage(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.repo = CasingRepository()
        self.current_casing_type: str | None = None

        self.setStyleSheet("""
            QFrame#HeaderCard, QFrame#MetricCard, QFrame#TableCard, QFrame#TypeCard {
                background: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 18px;
            }

            QFrame#HeaderCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ffffff,
                    stop:1 #f8fbff);
            }

            QFrame#TypeCard:hover {
                border: 1px solid #2563eb;
                background: #fbfdff;
            }

            QFrame#UnitCard {
                background: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 18px;
            }

            QFrame#UnitCard:hover {
                border: 1px solid #2563eb;
                background: #fbfdff;
            }

            QFrame#UnitCardBreakdown {
                background: #fff7f7;
                border: 1px solid #fecaca;
                border-radius: 18px;
            }

            QFrame#UnitCardBusy {
                background: #fffaf0;
                border: 1px solid #fed7aa;
                border-radius: 18px;
            }

            QLabel#UnitCode {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#UnitNo {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 900;
                letter-spacing: 0.4px;
            }

            QLabel#UnitRemark {
                color: #475569;
                font-size: 9pt;
                font-weight: 650;
            }

            QLabel#Breadcrumb {
                color: #2563eb;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 23pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle, QLabel#MetricLabel, QLabel#CardHint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#MetricValue {
                color: #0f172a;
                font-size: 19pt;
                font-weight: 950;
            }

            QLabel#TypeName {
                color: #0f172a;
                font-size: 17pt;
                font-weight: 950;
            }

            QLabel#SmallLabel {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 800;
            }

            QLabel#SmallValue {
                color: #0f172a;
                font-size: 13pt;
                font-weight: 950;
            }

            QFrame#SmallMetric {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }

            QLabel#ChipGood {
                background: #ecfdf5;
                color: #047857;
                border: 1px solid #a7f3d0;
                border-radius: 9px;
                padding: 4px 8px;
                font-weight: 850;
            }

            QLabel#ChipWarn {
                background: #fff7ed;
                color: #c2410c;
                border: 1px solid #fed7aa;
                border-radius: 9px;
                padding: 4px 8px;
                font-weight: 850;
            }

            QLabel#ChipBad {
                background: #fef2f2;
                color: #b91c1c;
                border: 1px solid #fecaca;
                border-radius: 9px;
                padding: 4px 8px;
                font-weight: 850;
            }

            QLabel#ChipNeutral {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 9px;
                padding: 4px 8px;
                font-weight: 850;
            }

            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 11px;
                padding: 9px 11px;
                color: #0f172a;
                font-weight: 650;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                padding: 9px 15px;
                font-weight: 850;
            }

            QPushButton#SecondaryButton {
                background: #f8fafc;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 11px;
                padding: 8px 13px;
                font-weight: 800;
            }

            QPushButton#DangerButton {
                background: #fee2e2;
                color: #991b1b;
                border: 1px solid #fecaca;
                border-radius: 11px;
                padding: 8px 13px;
                font-weight: 850;
            }

            QPushButton#OpenButton {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 11px;
                padding: 8px 13px;
                font-weight: 900;
            }

            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                gridline-color: #e2e8f0;
                color: #0f172a;
                font-size: 9.5pt;
            }

            QTableWidget::item {
                padding: 8px;
            }

            QTableWidget::item:selected {
                background: #dbeafe;
                color: #0f172a;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 10px;
                font-weight: 900;
            }

            QComboBox#InlineGood {
                background: #ecfdf5;
                color: #047857;
                border: 1px solid #86efac;
                border-radius: 10px;
                padding: 7px 10px;
                font-weight: 900;
            }

            QComboBox#InlineWarn {
                background: #fff7ed;
                color: #c2410c;
                border: 1px solid #fed7aa;
                border-radius: 10px;
                padding: 7px 10px;
                font-weight: 900;
            }

            QComboBox#InlineBad {
                background: #fef2f2;
                color: #b91c1c;
                border: 1px solid #fecaca;
                border-radius: 10px;
                padding: 7px 10px;
                font-weight: 900;
            }
        """)

        self._build_ui()
        self.refresh_overview()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._overview_page())
        self.stack.addWidget(self._detail_page())

        root.addWidget(self.stack)

    def _overview_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(22, 20, 22, 22)
        root.setSpacing(16)

        root.addWidget(self._overview_header())
        root.addLayout(self._overview_metrics())
        root.addWidget(self._overview_card_area(), 1)

        return page

    def _overview_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(7)

        breadcrumb = QLabel("Master Data  /  Factory Capacity  /  Casing Master")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Casing Control Center")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Track each casing type, physical unit availability, breakdown condition and stock use.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        self.overview_search_input = QLineEdit()
        self.overview_search_input.setPlaceholderText("Search casing type...")
        self.overview_search_input.setMinimumWidth(340)
        self.overview_search_input.textChanged.connect(self.refresh_overview)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh_overview)

        add_button = QPushButton("+ Add Casing Type")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self.add_type)

        layout.addLayout(text_area, 1)
        layout.addWidget(self.overview_search_input)
        layout.addWidget(refresh_button)
        layout.addWidget(add_button)

        return card

    def _overview_metrics(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        self.total_types_value = self._metric_card(layout, "Casing Types")
        self.total_units_value = self._metric_card(layout, "Total Physical Units")
        self.free_units_value = self._metric_card(layout, "Ready / Free")
        self.in_use_units_value = self._metric_card(layout, "In Use")
        self.breakdown_units_value = self._metric_card(layout, "Breakdown")

        return layout

    def _metric_card(self, parent_layout: QHBoxLayout, label_text: str) -> QLabel:
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(5)

        value = QLabel("0")
        value.setObjectName("MetricValue")

        label = QLabel(label_text)
        label.setObjectName("MetricLabel")

        layout.addWidget(value)
        layout.addWidget(label)

        parent_layout.addWidget(card)
        return value

    def _overview_card_area(self) -> QFrame:
        outer = QFrame()
        outer.setObjectName("TableCard")

        layout = QVBoxLayout(outer)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Casing Type Register")
        title.setObjectName("TypeName")
        hint = QLabel("Open a casing type to inspect individual physical casing units.")
        hint.setObjectName("CardHint")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(hint)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.cards_container = QWidget()
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setContentsMargins(2, 2, 2, 2)
        self.cards_grid.setSpacing(14)

        self.cards_scroll.setWidget(self.cards_container)

        layout.addLayout(top)
        layout.addWidget(self.cards_scroll, 1)

        return outer

    def _detail_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(22, 20, 22, 22)
        root.setSpacing(16)

        root.addWidget(self._detail_header())
        root.addLayout(self._detail_metrics())
        root.addWidget(self._detail_table_card(), 1)

        return page

    def _detail_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)

        text_area = QVBoxLayout()
        text_area.setSpacing(7)

        self.detail_breadcrumb = QLabel("Master Data  /  Factory Capacity  /  Casing Master")
        self.detail_breadcrumb.setObjectName("Breadcrumb")

        self.detail_title = QLabel("Casing Register")
        self.detail_title.setObjectName("PageTitle")

        self.detail_subtitle = QLabel("Manage individual casing condition and stock status.")
        self.detail_subtitle.setObjectName("PageSubtitle")
        self.detail_subtitle.setWordWrap(True)

        text_area.addWidget(self.detail_breadcrumb)
        text_area.addWidget(self.detail_title)
        text_area.addWidget(self.detail_subtitle)

        self.detail_search_input = QLineEdit()
        self.detail_search_input.setPlaceholderText("Search unit code, condition, stock status...")
        self.detail_search_input.setMinimumWidth(320)
        self.detail_search_input.textChanged.connect(self.refresh_detail)

        back_button = QPushButton("Back")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self.back_to_overview)

        edit_type_button = QPushButton("Edit Type")
        edit_type_button.setObjectName("SecondaryButton")
        edit_type_button.clicked.connect(self.edit_current_type)

        delete_type_button = QPushButton("Delete Type")
        delete_type_button.setObjectName("DangerButton")
        delete_type_button.clicked.connect(self.delete_current_type)

        add_unit_button = QPushButton("+ Add Unit")
        add_unit_button.setObjectName("PrimaryButton")
        add_unit_button.clicked.connect(self.add_units_to_current_type)

        layout.addLayout(text_area, 1)
        layout.addWidget(self.detail_search_input)
        layout.addWidget(back_button)
        layout.addWidget(edit_type_button)
        layout.addWidget(delete_type_button)
        layout.addWidget(add_unit_button)

        return card

    def _detail_metrics(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        self.detail_total_value = self._metric_card(layout, "Total Units")
        self.detail_active_value = self._metric_card(layout, "Active")
        self.detail_free_value = self._metric_card(layout, "Free")
        self.detail_in_use_value = self._metric_card(layout, "In Use")
        self.detail_breakdown_value = self._metric_card(layout, "Breakdown")

        return layout

    def _detail_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()

        title_area = QVBoxLayout()
        title_area.setSpacing(4)

        title = QLabel("Casing Unit Details")
        title.setObjectName("TypeName")

        subtitle = QLabel("Inline controls update condition and stock status instantly.")
        subtitle.setObjectName("CardHint")
        subtitle.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.detail_board_hint = QLabel("Inline asset controls")
        self.detail_board_hint.setObjectName("ChipNeutral")

        top.addLayout(title_area, 1)
        top.addWidget(self.detail_board_hint)

        self.detail_table = QTableWidget(0, 6)
        self.detail_table.setHorizontalHeaderLabels([
            "Casing Code",
            "Condition",
            "Stock Status",
            "Availability",
            "Remarks",
            "Action",
        ])

        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.detail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.detail_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.detail_table.setColumnWidth(0, 180)
        self.detail_table.setColumnWidth(1, 150)
        self.detail_table.setColumnWidth(2, 150)
        self.detail_table.setColumnWidth(3, 140)
        self.detail_table.setColumnWidth(5, 140)

        layout.addLayout(top)
        layout.addWidget(self.detail_table, 1)

        return card

    def refresh_overview(self) -> None:
        try:
            stats = self.repo.overview_stats()
            rows = self.repo.list_types(
                self.overview_search_input.text() if hasattr(self, "overview_search_input") else ""
            )
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load casing master. " + str(exc))
            return

        self.total_types_value.setText(str(stats.get("total_types", 0)))
        self.total_units_value.setText(str(stats.get("total_units", 0)))
        self.free_units_value.setText(str(stats.get("free_units", 0)))
        self.in_use_units_value.setText(str(stats.get("in_use_units", 0)))
        self.breakdown_units_value.setText(str(stats.get("breakdown_units", 0)))

        self._clear_layout(self.cards_grid)

        for index, row in enumerate(rows):
            card = self._type_card(row)
            self.cards_grid.addWidget(card, index // 3, index % 3)

        self.cards_grid.setRowStretch((len(rows) // 3) + 1, 1)

    def _type_card(self, row: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("TypeCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda event, casing_type=row["casing_type"]: self.open_detail(casing_type)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(10)

        top = QHBoxLayout()
        name = QLabel(str(row.get("casing_type", "")))
        name.setObjectName("TypeName")

        health = QLabel("READY" if int(row.get("breakdown_units", 0) or 0) == 0 else "ATTENTION")
        health.setObjectName("ChipGood" if health.text() == "READY" else "ChipBad")

        top.addWidget(name)
        top.addStretch()
        top.addWidget(health)

        metrics = QGridLayout()
        metrics.setSpacing(8)

        metrics.addWidget(self._small_metric("Total", row.get("total_units", 0)), 0, 0)
        metrics.addWidget(self._small_metric("Free", row.get("free_units", 0)), 0, 1)
        metrics.addWidget(self._small_metric("In Use", row.get("in_use_units", 0)), 1, 0)
        metrics.addWidget(self._small_metric("Breakdown", row.get("breakdown_units", 0)), 1, 1)

        open_button = QPushButton("Open Register")
        open_button.setObjectName("OpenButton")
        open_button.clicked.connect(lambda checked=False, casing_type=row["casing_type"]: self.open_detail(casing_type))

        layout.addLayout(top)
        layout.addLayout(metrics)
        layout.addStretch()
        layout.addWidget(open_button)

        return card

    def _small_metric(self, label_text: str, value_text) -> QFrame:
        box = QFrame()
        box.setObjectName("SmallMetric")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(2)

        value = QLabel(str(value_text))
        value.setObjectName("SmallValue")

        label = QLabel(label_text)
        label.setObjectName("SmallLabel")

        layout.addWidget(value)
        layout.addWidget(label)

        return box

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()

            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def open_detail(self, casing_type: str) -> None:
        self.current_casing_type = casing_type
        self.detail_search_input.clear()

        self.detail_breadcrumb.setText(f"Master Data  /  Factory Capacity  /  Casing Master  /  {casing_type}")
        self.detail_title.setText(f"{casing_type} Casing Board")
        self.detail_subtitle.setText(f"Add/edit/delete casing units. Active + Free = Available.")

        self.refresh_detail()
        self.stack.setCurrentIndex(1)

    def refresh_detail(self) -> None:
        if not self.current_casing_type:
            return

        try:
            stats = self.repo.type_stats(self.current_casing_type)
            rows = self.repo.list_units(
                self.current_casing_type,
                self.detail_search_input.text() if hasattr(self, "detail_search_input") else "",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load casing units. " + str(exc))
            return

        self.detail_total_value.setText(str(stats.get("total_units", 0)))
        self.detail_active_value.setText(str(stats.get("active_units", 0)))
        self.detail_free_value.setText(str(stats.get("free_units", 0)))
        self.detail_in_use_value.setText(str(stats.get("in_use_units", 0)))
        self.detail_breakdown_value.setText(str(stats.get("breakdown_units", 0)))

        self.detail_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            self.detail_table.setRowHeight(row_index, 58)

            condition = str(row.get("condition_status", "") or "Active")
            stock = str(row.get("stock_status", "") or "Free")

            if condition == "Breakdown":
                availability = "Not Usable"
            elif stock == "Free":
                availability = "Available"
            elif stock == "In Use":
                availability = "In Use"
            elif stock == "Reserved":
                availability = "Reserved"
            else:
                availability = "-"

            self._set_table_item(self.detail_table, row_index, 0, row.get("casing_code", ""))

            condition_combo = self._status_combo(
                ["Active", "Breakdown"],
                condition,
                "condition",
            )
            condition_combo.currentTextChanged.connect(
                lambda value, unit_id=row["id"]: self.update_unit_condition_inline(unit_id, value)
            )
            self.detail_table.setCellWidget(row_index, 1, condition_combo)

            stock_combo = self._status_combo(
                ["Free", "In Use", "Reserved"],
                stock,
                "stock",
            )
            stock_combo.currentTextChanged.connect(
                lambda value, unit_id=row["id"]: self.update_unit_stock_inline(unit_id, value)
            )
            self.detail_table.setCellWidget(row_index, 2, stock_combo)

            self.detail_table.setCellWidget(row_index, 3, self._chip(availability))
            self._set_table_item(self.detail_table, row_index, 4, row.get("remarks", ""))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 5, 4, 5)

            manage_button = QPushButton("Manage")
            manage_button.setObjectName("OpenButton")
            manage_button.clicked.connect(lambda checked=False, unit_id=row["id"]: self.edit_unit(unit_id))

            action_layout.addStretch()
            action_layout.addWidget(manage_button)
            action_layout.addStretch()

            self.detail_table.setCellWidget(row_index, 5, action_widget)

    def _status_combo(self, values: list[str], current_value: str, mode: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(values)
        combo.blockSignals(True)
        combo.setCurrentText(current_value)
        combo.blockSignals(False)
        combo.setMinimumHeight(38)

        if current_value == "Breakdown":
            combo.setObjectName("InlineBad")
        elif current_value in {"In Use", "Reserved"}:
            combo.setObjectName("InlineWarn")
        else:
            combo.setObjectName("InlineGood")

        return combo

    def _chip(self, value) -> QLabel:
        text_value = str(value or "-")
        chip = QLabel(text_value)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if text_value == "Active" or text_value == "Free":
            chip.setObjectName("ChipGood")
        elif text_value == "Reserved" or text_value == "In Use":
            chip.setObjectName("ChipWarn")
        elif text_value == "Breakdown":
            chip.setObjectName("ChipBad")
        else:
            chip.setObjectName("ChipNeutral")

        return chip

    def _set_table_item(self, table: QTableWidget, row: int, col: int, value, center: bool = False) -> None:
        item = QTableWidgetItem(str(value if value is not None else ""))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        table.setItem(row, col, item)

    def back_to_overview(self) -> None:
        self.current_casing_type = None
        self.refresh_overview()
        self.stack.setCurrentIndex(0)

    def add_type(self) -> None:
        dialog = CasingTypeDialog(
            self,
            "Add Casing Type",
            allow_initial_count=True,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        if not data["casing_type"]:
            QMessageBox.warning(self, "Validation", "Casing Type is required.")
            return

        try:
            self.repo.add_type(data["casing_type"], data["initial_count"], data["remarks"])
            self.refresh_overview()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not add casing type. " + str(exc))

    def edit_current_type(self) -> None:
        if not self.current_casing_type:
            return

        try:
            current = self.repo.get_type(self.current_casing_type)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load casing type. " + str(exc))
            return

        dialog = CasingTypeDialog(
            self,
            "Edit Casing Type",
            casing_type=current.get("casing_type", ""),
            remarks=current.get("remarks", ""),
            allow_initial_count=False,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        if not data["casing_type"]:
            QMessageBox.warning(self, "Validation", "Casing Type is required.")
            return

        try:
            old_type = self.current_casing_type
            new_type = data["casing_type"]
            self.repo.rename_type(old_type, new_type, data["remarks"])
            self.current_casing_type = new_type

            self.detail_breadcrumb.setText(f"Master Data  /  Factory Capacity  /  Casing Master  /  {new_type}")
            self.detail_title.setText(f"{new_type} Casing Board")
            self.detail_subtitle.setText(f"Add/edit/delete casing units. Active + Free = Available.")

            self.refresh_detail()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not update casing type. " + str(exc))

    def delete_current_type(self) -> None:
        if not self.current_casing_type:
            return

        casing_type = self.current_casing_type

        answer = QMessageBox.question(
            self,
            "Delete Casing Type",
            f"Delete {casing_type} and all its casing units?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repo.delete_type(casing_type)
            self.current_casing_type = None
            self.refresh_overview()
            self.stack.setCurrentIndex(0)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not delete casing type. " + str(exc))

    def add_units_to_current_type(self) -> None:
        if not self.current_casing_type:
            return

        dialog = AddUnitsDialog(self, self.current_casing_type)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.repo.add_units(self.current_casing_type, dialog.qty())
            self.refresh_detail()
            self.refresh_overview()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not add casing units. " + str(exc))

    def update_unit_condition_inline(self, unit_id: int, condition_status: str) -> None:
        try:
            self.repo.update_unit_condition(unit_id, condition_status)
            self.refresh_detail()
            self.refresh_overview()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not update casing condition. " + str(exc))

    def update_unit_stock_inline(self, unit_id: int, stock_status: str) -> None:
        try:
            self.repo.update_unit_stock(unit_id, stock_status)
            self.refresh_detail()
            self.refresh_overview()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not update casing stock status. " + str(exc))

    def edit_unit(self, unit_id: int) -> None:
        try:
            unit = self.repo.get_unit(unit_id)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load casing unit. " + str(exc))
            return

        dialog = CasingUnitDialog(self, unit)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        if not data["casing_code"]:
            QMessageBox.warning(self, "Validation", "Casing Code is required.")
            return

        try:
            self.repo.update_unit(unit_id, data)
            self.refresh_detail()
            self.refresh_overview()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not update casing unit. " + str(exc))

    def delete_unit(self, unit_id: int) -> None:
        answer = QMessageBox.question(
            self,
            "Delete Casing Unit",
            "Delete this individual casing unit?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repo.delete_unit(unit_id)
            self.refresh_detail()
            self.refresh_overview()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not delete casing unit. " + str(exc))
