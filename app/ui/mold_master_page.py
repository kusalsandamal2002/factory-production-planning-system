from __future__ import annotations

from typing import Any

from PySide6.QtCore import QDateTime, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if not value:
                return default
        return int(float(value))
    except Exception:
        return default


class MoldRepository:
    """Mold master with live production-plan usage.

    Manual physical state remains in mold_master. Live plan usage is read
    from planning_resource_reservations, which is the same source used by
    the production-planning engine. Nothing is copied into the master table,
    avoiding stale values and reservation double counting.
    """

    def __init__(self) -> None:
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS mold_master (
                        id BIGSERIAL PRIMARY KEY,
                        mold_key_code VARCHAR(255) NOT NULL UNIQUE,
                        mold_count INTEGER NOT NULL DEFAULT 0,
                        production_mold_count INTEGER NOT NULL DEFAULT 0,
                        breakdown_mold_count INTEGER NOT NULL DEFAULT 0,
                        planning_reserved_mold_count INTEGER NOT NULL DEFAULT 0,
                        casing_type VARCHAR(255) NOT NULL DEFAULT '',
                        casing_count INTEGER NOT NULL DEFAULT 0,
                        status VARCHAR(32) NOT NULL DEFAULT 'Active',
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        remarks TEXT NOT NULL DEFAULT '',
                        source_file VARCHAR(255) NOT NULL DEFAULT '',
                        source_sheet VARCHAR(255) NOT NULL DEFAULT '',
                        source_rows TEXT NOT NULL DEFAULT '',
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

            statements = [
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS production_mold_count "
                    "INTEGER NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS breakdown_mold_count "
                    "INTEGER NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS planning_reserved_mold_count "
                    "INTEGER NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS casing_type "
                    "VARCHAR(255) NOT NULL DEFAULT ''"
                ),
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS casing_count "
                    "INTEGER NOT NULL DEFAULT 0"
                ),
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS status "
                    "VARCHAR(32) NOT NULL DEFAULT 'Active'"
                ),
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS is_active "
                    "BOOLEAN NOT NULL DEFAULT TRUE"
                ),
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS remarks "
                    "TEXT NOT NULL DEFAULT ''"
                ),
                (
                    "ALTER TABLE mold_master "
                    "ADD COLUMN IF NOT EXISTS updated_at "
                    "TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ),
            ]

            for statement in statements:
                conn.execute(text(statement))

            conn.execute(
                text(
                    """
                    UPDATE mold_master
                    SET
                        mold_count = COALESCE(mold_count, 0),
                        production_mold_count =
                            COALESCE(production_mold_count, 0),
                        breakdown_mold_count =
                            COALESCE(breakdown_mold_count, 0),
                        planning_reserved_mold_count =
                            COALESCE(planning_reserved_mold_count, 0),
                        status =
                            COALESCE(NULLIF(status, ''), 'Active'),
                        is_active = COALESCE(is_active, TRUE)
                    """
                )
            )

            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        ix_mold_master_key_live
                    ON mold_master (
                        LOWER(TRIM(mold_key_code))
                    )
                    """
                )
            )

            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        ix_plan_reservations_mold_live
                    ON planning_resource_reservations (
                        resource_type,
                        reservation_date,
                        LOWER(TRIM(resource_key))
                    )
                    """
                )
            )

    @staticmethod
    def _live_cte() -> str:
        return """
            WITH reservation_daily AS (
                SELECT
                    LOWER(TRIM(resource_key)) AS resource_identity,
                    reservation_date,
                    COALESCE(SUM(reserved_qty), 0)::INTEGER
                        AS reserved_qty,
                    STRING_AGG(
                        DISTINCT COALESCE(
                            NULLIF(shipment.shipment_name, ''),
                            shipment.shipment_no,
                            'Unknown Shipment'
                        ),
                        ', '
                        ORDER BY COALESCE(
                            NULLIF(shipment.shipment_name, ''),
                            shipment.shipment_no,
                            'Unknown Shipment'
                        )
                    ) AS shipment_names
                FROM planning_resource_reservations reservation
                LEFT JOIN mpps_shipments shipment
                  ON shipment.id = reservation.shipment_id
                WHERE reservation.resource_type = 'mold'
                  AND reservation.reservation_date >= CURRENT_DATE
                GROUP BY
                    LOWER(TRIM(resource_key)),
                    reservation_date
            ),
            today_reservations AS (
                SELECT
                    resource_identity,
                    reserved_qty AS reserved_today,
                    shipment_names AS shipments_today
                FROM reservation_daily
                WHERE reservation_date = CURRENT_DATE
            ),
            future_peak AS (
                SELECT DISTINCT ON (resource_identity)
                    resource_identity,
                    reservation_date AS peak_date,
                    reserved_qty AS future_peak_reserved,
                    shipment_names AS peak_shipments
                FROM reservation_daily
                ORDER BY
                    resource_identity,
                    reserved_qty DESC,
                    reservation_date ASC
            )
        """

    def _base_select(self) -> str:
        return (
            self._live_cte()
            + """
            SELECT
                mold.id,
                mold.mold_key_code,
                COALESCE(mold.mold_count, 0)::INTEGER
                    AS mold_count,
                COALESCE(mold.production_mold_count, 0)::INTEGER
                    AS manual_production_mold_count,
                COALESCE(mold.breakdown_mold_count, 0)::INTEGER
                    AS breakdown_mold_count,
                COALESCE(
                    mold.planning_reserved_mold_count,
                    0
                )::INTEGER AS manual_reserved_mold_count,
                COALESCE(today.reserved_today, 0)::INTEGER
                    AS plan_reserved_today,
                (
                    COALESCE(mold.production_mold_count, 0)
                    + COALESCE(today.reserved_today, 0)
                )::INTEGER AS live_production_mold_count,
                COALESCE(peak.future_peak_reserved, 0)::INTEGER
                    AS future_peak_reserved,
                peak.peak_date,
                COALESCE(today.shipments_today, '') AS shipments_today,
                COALESCE(peak.peak_shipments, '') AS peak_shipments,
                CASE
                    WHEN
                        COALESCE(mold.is_active, TRUE) = FALSE
                        OR LOWER(
                            COALESCE(mold.status, 'Active')
                        ) <> 'active'
                    THEN 0
                    ELSE GREATEST(
                        COALESCE(mold.mold_count, 0)
                        - COALESCE(
                            mold.production_mold_count,
                            0
                        )
                        - COALESCE(
                            mold.breakdown_mold_count,
                            0
                        )
                        - COALESCE(
                            mold.planning_reserved_mold_count,
                            0
                        )
                        - COALESCE(today.reserved_today, 0),
                        0
                    )
                END::INTEGER AS available_mold_count,
                COALESCE(mold.remarks, '') AS remarks,
                COALESCE(mold.status, 'Active') AS status,
                COALESCE(mold.is_active, TRUE) AS is_active,
                mold.updated_at
            FROM mold_master mold
            LEFT JOIN today_reservations today
              ON today.resource_identity =
                 LOWER(TRIM(mold.mold_key_code))
            LEFT JOIN future_peak peak
              ON peak.resource_identity =
                 LOWER(TRIM(mold.mold_key_code))
            """
        )

    def stats(self) -> dict[str, Any]:
        sql = (
            "SELECT "
            "COUNT(*) AS total_keys, "
            "COALESCE(SUM(mold_count), 0) AS total_molds, "
            "COALESCE(SUM(live_production_mold_count), 0) "
            "AS live_production_molds, "
            "COALESCE(SUM(plan_reserved_today), 0) "
            "AS plan_reserved_today, "
            "COALESCE(SUM(breakdown_mold_count), 0) "
            "AS breakdown_molds, "
            "COALESCE(SUM(available_mold_count), 0) "
            "AS available_molds, "
            "COALESCE(SUM(future_peak_reserved), 0) "
            "AS future_peak_reserved "
            "FROM ("
            + self._base_select()
            + ") live_molds"
        )

        with engine.connect() as conn:
            row = conn.execute(
                text(sql)
            ).mappings().one()
            return dict(row)

    def list_molds(
        self,
        search_text: str = "",
    ) -> list[dict[str, Any]]:
        search = (search_text or "").strip().lower()
        sql = self._base_select()
        params: dict[str, Any] = {}

        if search:
            sql += (
                " WHERE LOWER(mold.mold_key_code) "
                "LIKE :search "
            )
            params["search"] = f"%{search}%"

        sql += " ORDER BY mold.mold_key_code ASC "

        with engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    text(sql),
                    params,
                ).mappings().all()
            ]

    def get_mold(
        self,
        mold_id: int,
    ) -> dict[str, Any]:
        sql = (
            self._base_select()
            + " WHERE mold.id = :mold_id LIMIT 1"
        )

        with engine.connect() as conn:
            row = conn.execute(
                text(sql),
                {"mold_id": int(mold_id)},
            ).mappings().first()

        if not row:
            raise RuntimeError(
                "The selected mold record was not found."
            )

        return dict(row)

    def add_mold(self, data: dict[str, Any]) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO mold_master (
                        mold_key_code,
                        mold_count,
                        production_mold_count,
                        breakdown_mold_count,
                        planning_reserved_mold_count,
                        status,
                        is_active,
                        remarks,
                        source_file,
                        source_sheet,
                        source_rows,
                        updated_at
                    )
                    VALUES (
                        :mold_key_code,
                        :mold_count,
                        :production_mold_count,
                        :breakdown_mold_count,
                        :planning_reserved_mold_count,
                        'Active',
                        TRUE,
                        :remarks,
                        'Manual',
                        '',
                        '',
                        CURRENT_TIMESTAMP
                    )
                    """
                ),
                data,
            )

    def update_mold(
        self,
        mold_id: int,
        data: dict[str, Any],
    ) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE mold_master
                    SET
                        mold_key_code = :mold_key_code,
                        mold_count = :mold_count,
                        production_mold_count =
                            :production_mold_count,
                        breakdown_mold_count =
                            :breakdown_mold_count,
                        planning_reserved_mold_count =
                            :planning_reserved_mold_count,
                        status = 'Active',
                        is_active = TRUE,
                        remarks = :remarks,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {
                    "id": int(mold_id),
                    **data,
                },
            )


class MoldDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        mold: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setMinimumWidth(620)
        self.mold = mold or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        explanation = QLabel(
            "Manual In Production is a physical shop-floor override. "
            "Live production-plan usage is calculated automatically from "
            "planning reservations and cannot be edited here."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet(
            "background:#eff6ff; color:#1e40af; "
            "border:1px solid #bfdbfe; border-radius:9px; "
            "padding:10px; font-weight:750;"
        )
        layout.addWidget(explanation)

        form = QFormLayout()
        form.setSpacing(12)

        self.key_input = QLineEdit(
            str(
                self.mold.get(
                    "mold_key_code",
                    "",
                )
            )
        )
        self.key_input.setPlaceholderText(
            "Example: 10.00-20 SM"
        )

        self.total_input = QSpinBox()
        self.total_input.setRange(0, 100000)
        self.total_input.setValue(
            _to_int(
                self.mold.get("mold_count")
            )
        )

        self.add_qty_input = QSpinBox()
        self.add_qty_input.setRange(0, 100000)
        self.add_qty_input.setValue(0)

        self.manual_production_input = QSpinBox()
        self.manual_production_input.setRange(
            0,
            100000,
        )
        self.manual_production_input.setValue(
            _to_int(
                self.mold.get(
                    "manual_production_mold_count"
                )
            )
        )

        self.live_plan_value = QLabel(
            str(
                _to_int(
                    self.mold.get(
                        "plan_reserved_today"
                    )
                )
            )
        )
        self.live_plan_value.setStyleSheet(
            "font-size:12pt; font-weight:950; "
            "color:#1d4ed8;"
        )

        self.manual_reserved_input = QSpinBox()
        self.manual_reserved_input.setRange(
            0,
            100000,
        )
        self.manual_reserved_input.setValue(
            _to_int(
                self.mold.get(
                    "manual_reserved_mold_count"
                )
            )
        )

        self.breakdown_input = QSpinBox()
        self.breakdown_input.setRange(
            0,
            100000,
        )
        self.breakdown_input.setValue(
            _to_int(
                self.mold.get(
                    "breakdown_mold_count"
                )
            )
        )

        self.available_label = QLabel()
        self.available_label.setStyleSheet(
            "font-size:12pt; font-weight:950; "
            "color:#047857;"
        )

        self.remarks_input = QTextEdit(
            str(
                self.mold.get("remarks")
                or ""
            )
        )
        self.remarks_input.setFixedHeight(88)

        for widget in (
            self.total_input,
            self.add_qty_input,
            self.manual_production_input,
            self.manual_reserved_input,
            self.breakdown_input,
        ):
            widget.valueChanged.connect(
                self.update_available_preview
            )

        form.addRow(
            "Mold Key Code",
            self.key_input,
        )
        form.addRow(
            "Current / Total Mold Count",
            self.total_input,
        )
        form.addRow(
            "Add New Mold Quantity",
            self.add_qty_input,
        )
        form.addRow(
            "Manual In-Production Count",
            self.manual_production_input,
        )
        form.addRow(
            "Live Plan Reserved Today",
            self.live_plan_value,
        )
        form.addRow(
            "Manual Planning Reserved",
            self.manual_reserved_input,
        )
        form.addRow(
            "Breakdown Mold Count",
            self.breakdown_input,
        )
        form.addRow(
            "Available Now",
            self.available_label,
        )
        form.addRow(
            "Remarks",
            self.remarks_input,
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

        self.update_available_preview()

    def update_available_preview(self) -> None:
        total = (
            self.total_input.value()
            + self.add_qty_input.value()
        )
        manual_production = (
            self.manual_production_input.value()
        )
        live_plan = _to_int(
            self.mold.get(
                "plan_reserved_today"
            )
        )
        manual_reserved = (
            self.manual_reserved_input.value()
        )
        breakdown = self.breakdown_input.value()

        available = max(
            0,
            total
            - manual_production
            - live_plan
            - manual_reserved
            - breakdown,
        )

        self.available_label.setText(
            (
                f"{available}  =  {total} total"
                f" − {manual_production} manual production"
                f" − {live_plan} live plan"
                f" − {manual_reserved} manual reserved"
                f" − {breakdown} breakdown"
            )
        )

    def data(self) -> dict[str, Any]:
        total = (
            int(self.total_input.value())
            + int(self.add_qty_input.value())
        )

        return {
            "mold_key_code": (
                self.key_input.text().strip()
            ),
            "mold_count": total,
            "production_mold_count": int(
                self.manual_production_input.value()
            ),
            "breakdown_mold_count": int(
                self.breakdown_input.value()
            ),
            "planning_reserved_mold_count": int(
                self.manual_reserved_input.value()
            ),
            "remarks": (
                self.remarks_input
                .toPlainText()
                .strip()
            ),
        }


class MoldMasterPage(QWidget):
    AUTO_REFRESH_MS = 5000

    def __init__(self) -> None:
        super().__init__()

        self.repo = MoldRepository()
        self._last_error = ""

        self._build_ui()
        self._apply_styles()
        self._setup_auto_refresh()

        self.refresh(show_error=True)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#HeaderCard,
            QFrame#MetricCard,
            QFrame#TableCard,
            QFrame#LiveBar {
                background:#ffffff;
                border:1px solid #e2e8f0;
                border-radius:16px;
            }

            QLabel#Breadcrumb {
                color:#2563eb;
                font-size:9pt;
                font-weight:850;
            }

            QLabel#PageTitle {
                color:#0f172a;
                font-size:22pt;
                font-weight:950;
            }

            QLabel#PageSubtitle,
            QLabel#MetricLabel,
            QLabel#TableHint {
                color:#64748b;
                font-size:9pt;
                font-weight:650;
            }

            QLabel#MetricValue {
                color:#0f172a;
                font-size:18pt;
                font-weight:950;
            }

            QLabel#LiveBadge {
                background:#dcfce7;
                color:#047857;
                border:1px solid #bbf7d0;
                border-radius:9px;
                padding:7px 11px;
                font-weight:950;
            }

            QLabel#LastRefresh {
                color:#475569;
                font-weight:750;
            }

            QLineEdit {
                background:#ffffff;
                border:1px solid #cbd5e1;
                border-radius:10px;
                padding:8px 10px;
                color:#0f172a;
                font-weight:650;
            }

            QPushButton#PrimaryButton {
                background:#2563eb;
                color:#ffffff;
                border:none;
                border-radius:10px;
                padding:9px 14px;
                font-weight:850;
            }

            QPushButton#SecondaryButton {
                background:#f8fafc;
                color:#0f172a;
                border:1px solid #cbd5e1;
                border-radius:10px;
                padding:8px 12px;
                font-weight:800;
            }

            QTableWidget {
                background:#ffffff;
                border:1px solid #e2e8f0;
                border-radius:10px;
                gridline-color:#e2e8f0;
                color:#0f172a;
                font-size:9pt;
                alternate-background-color:#f8fafc;
                selection-background-color:#dbeafe;
                selection-color:#0f172a;
            }

            QTableWidget::item {
                padding:7px 7px;
            }

            QHeaderView::section {
                background:#f1f5f9;
                color:#334155;
                border:none;
                border-right:1px solid #e2e8f0;
                border-bottom:1px solid #e2e8f0;
                padding:8px 7px;
                font-weight:900;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(
            22,
            20,
            22,
            22,
        )
        root.setSpacing(14)

        root.addWidget(self._header())
        root.addLayout(self._metrics())
        root.addWidget(self._live_bar())
        root.addWidget(self._table_card(), 1)

    def _header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(
            22,
            18,
            22,
            18,
        )
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(7)

        breadcrumb = QLabel(
            "Master Data  /  Factory Capacity  /  Mold Master"
        )
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Mold Master")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Physical mold master with live production-plan usage. "
            "Production and available counts auto-refresh from the "
            "same reservations used by the planning engine."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search mold key code..."
        )
        self.search_input.setMinimumWidth(320)
        self.search_input.textChanged.connect(
            lambda: self.refresh(
                show_error=False
            )
        )

        self.live_badge = QLabel(
            "LIVE • AUTO 5 SEC"
        )
        self.live_badge.setObjectName(
            "LiveBadge"
        )

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName(
            "SecondaryButton"
        )
        refresh_button.clicked.connect(
            lambda: self.refresh(
                show_error=True
            )
        )

        add_button = QPushButton("+ Add Mold")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(
            self.add_mold
        )

        layout.addLayout(text_area, 1)
        layout.addWidget(self.search_input)
        layout.addWidget(self.live_badge)
        layout.addWidget(refresh_button)
        layout.addWidget(add_button)

        return card

    def _metrics(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)

        self.total_keys_value = (
            self._metric_card(
                layout,
                "Mold Key Codes",
            )
        )
        self.total_molds_value = (
            self._metric_card(
                layout,
                "Total Molds",
            )
        )
        self.live_production_value = (
            self._metric_card(
                layout,
                "Live Production Molds",
            )
        )
        self.plan_reserved_today_value = (
            self._metric_card(
                layout,
                "Plan Reserved Today",
            )
        )
        self.breakdown_molds_value = (
            self._metric_card(
                layout,
                "Breakdown Molds",
            )
        )
        self.available_molds_value = (
            self._metric_card(
                layout,
                "Available Now",
            )
        )

        return layout

    def _metric_card(
        self,
        parent_layout: QHBoxLayout,
        label_text: str,
    ) -> QLabel:
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            16,
            12,
            16,
            12,
        )
        layout.setSpacing(4)

        value = QLabel("0")
        value.setObjectName("MetricValue")

        label = QLabel(label_text)
        label.setObjectName("MetricLabel")
        label.setWordWrap(True)

        layout.addWidget(value)
        layout.addWidget(label)

        parent_layout.addWidget(card)
        return value

    def _live_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("LiveBar")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(
            15,
            9,
            15,
            9,
        )
        layout.setSpacing(12)

        formula = QLabel(
            "Available Now = Total − Manual In Production "
            "− Live Plan Reserved Today − Manual Reserved "
            "− Breakdown"
        )
        formula.setObjectName("TableHint")

        self.last_refresh_label = QLabel(
            "Last live refresh: -"
        )
        self.last_refresh_label.setObjectName(
            "LastRefresh"
        )

        layout.addWidget(formula, 1)
        layout.addWidget(
            self.last_refresh_label
        )
        return bar

    def _table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            16,
            14,
            16,
            16,
        )
        layout.setSpacing(9)

        self.loaded_rows_label = QLabel(
            "Loaded Mold Key Codes: 0"
        )
        self.loaded_rows_label.setObjectName(
            "PageSubtitle"
        )

        explanation = QLabel(
            "Live Production includes manual shop-floor usage plus "
            "today's planning reservations. Double-click a row to edit "
            "physical totals, manual usage, reserved quantity or breakdown."
        )
        explanation.setObjectName("TableHint")
        explanation.setWordWrap(True)

        layout.addWidget(
            self.loaded_rows_label
        )
        layout.addWidget(explanation)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Mold Key Code",
            "Total Mold",
            "Live Production",
            "Manual In Use",
            "Plan Reserved Today",
            "Manual Reserved",
            "Breakdown",
            "Future Peak",
            "Available Now",
            "Active Shipments Today",
        ])

        layout.addWidget(self.table, 1)
        return card

    def _setup_auto_refresh(self) -> None:
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(
            self.AUTO_REFRESH_MS
        )
        self.refresh_timer.timeout.connect(
            lambda: self.refresh(
                show_error=False
            )
        )
        self.refresh_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)

        if hasattr(self, "refresh_timer"):
            self.refresh_timer.start()

        QTimer.singleShot(
            0,
            lambda: self.refresh(
                show_error=False
            ),
        )

    def hideEvent(self, event) -> None:
        if hasattr(self, "refresh_timer"):
            self.refresh_timer.stop()

        super().hideEvent(event)

    def refresh(
        self,
        show_error: bool = False,
    ) -> None:
        try:
            stats = self.repo.stats()
            rows = self.repo.list_molds(
                self.search_input.text()
                if hasattr(
                    self,
                    "search_input",
                )
                else ""
            )
            self._last_error = ""
        except Exception as exc:
            message = str(exc)

            if (
                show_error
                or message != self._last_error
            ):
                QMessageBox.critical(
                    self,
                    "Database Error",
                    (
                        "Could not load live mold capacity."
                        f"\n\nReason: {message}"
                    ),
                )

            self._last_error = message
            return

        self.total_keys_value.setText(
            str(
                _to_int(
                    stats.get("total_keys")
                )
            )
        )
        self.total_molds_value.setText(
            str(
                _to_int(
                    stats.get("total_molds")
                )
            )
        )
        self.live_production_value.setText(
            str(
                _to_int(
                    stats.get(
                        "live_production_molds"
                    )
                )
            )
        )
        self.plan_reserved_today_value.setText(
            str(
                _to_int(
                    stats.get(
                        "plan_reserved_today"
                    )
                )
            )
        )
        self.breakdown_molds_value.setText(
            str(
                _to_int(
                    stats.get(
                        "breakdown_molds"
                    )
                )
            )
        )
        self.available_molds_value.setText(
            str(
                _to_int(
                    stats.get(
                        "available_molds"
                    )
                )
            )
        )

        self.loaded_rows_label.setText(
            (
                f"Loaded Mold Key Codes: "
                f"{len(rows)} / "
                f"{_to_int(stats.get('total_keys'))}"
            )
        )
        self.last_refresh_label.setText(
            (
                "Last live refresh: "
                + QDateTime.currentDateTime()
                .toString("yyyy-MM-dd HH:mm:ss")
            )
        )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for row_index, mold in enumerate(
            rows
        ):
            self.table.setRowHeight(
                row_index,
                38,
            )

            live_production = _to_int(
                mold.get(
                    "live_production_mold_count"
                )
            )
            available = _to_int(
                mold.get(
                    "available_mold_count"
                )
            )
            total = _to_int(
                mold.get("mold_count")
            )

            values = [
                mold.get("mold_key_code") or "",
                total,
                live_production,
                _to_int(
                    mold.get(
                        "manual_production_mold_count"
                    )
                ),
                _to_int(
                    mold.get(
                        "plan_reserved_today"
                    )
                ),
                _to_int(
                    mold.get(
                        "manual_reserved_mold_count"
                    )
                ),
                _to_int(
                    mold.get(
                        "breakdown_mold_count"
                    )
                ),
                _to_int(
                    mold.get(
                        "future_peak_reserved"
                    )
                ),
                available,
                mold.get("shipments_today") or "-",
            ]

            for column, value in enumerate(
                values
            ):
                item = QTableWidgetItem(
                    str(value)
                )
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEditable
                )

                if column > 0 and column < 9:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                if column == 0:
                    item.setData(
                        Qt.ItemDataRole.UserRole,
                        int(mold.get("id")),
                    )

                item.setToolTip(str(value))
                self.table.setItem(
                    row_index,
                    column,
                    item,
                )

            if live_production > 0:
                for column in range(
                    self.table.columnCount()
                ):
                    item = self.table.item(
                        row_index,
                        column,
                    )
                    if item is not None:
                        item.setBackground(
                            QColor("#eff6ff")
                        )

            available_item = self.table.item(
                row_index,
                8,
            )
            if available_item is not None:
                if available <= 0 and total > 0:
                    available_item.setForeground(
                        QColor("#b91c1c")
                    )
                    available_item.setBackground(
                        QColor("#fee2e2")
                    )
                elif available > 0:
                    available_item.setForeground(
                        QColor("#047857")
                    )
                    available_item.setBackground(
                        QColor("#dcfce7")
                    )

        self.table.setSortingEnabled(True)

    def _configure_table(self) -> None:
        self.table.verticalHeader().setVisible(
            False
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setAlternatingRowColors(
            True
        )
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(True)
        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.table.cellDoubleClicked.connect(
            lambda row, column:
            self.edit_mold_for_row(row)
        )

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)

        widths = {
            0: 235,
            1: 92,
            2: 115,
            3: 105,
            4: 135,
            5: 115,
            6: 95,
            7: 100,
            8: 110,
            9: 300,
        }

        for column in range(
            self.table.columnCount()
        ):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Fixed,
            )
            self.table.setColumnWidth(
                column,
                widths[column],
            )

    def _validate_counts(
        self,
        data: dict[str, Any],
        live_plan_reserved: int = 0,
    ) -> bool:
        if not data["mold_key_code"]:
            QMessageBox.warning(
                self,
                "Validation",
                "Mold Key Code is required.",
            )
            return False

        total = _to_int(data["mold_count"])
        used = (
            _to_int(
                data["production_mold_count"]
            )
            + _to_int(
                data[
                    "breakdown_mold_count"
                ]
            )
            + _to_int(
                data[
                    "planning_reserved_mold_count"
                ]
            )
            + _to_int(live_plan_reserved)
        )

        if used > total:
            QMessageBox.warning(
                self,
                "Validation",
                (
                    "The total mold count is lower than the "
                    "current physical and planning usage.\n\n"
                    f"Total: {total}\n"
                    f"Manual in production: "
                    f"{_to_int(data['production_mold_count'])}\n"
                    f"Live plan reserved today: "
                    f"{_to_int(live_plan_reserved)}\n"
                    f"Manual reserved: "
                    f"{_to_int(data['planning_reserved_mold_count'])}\n"
                    f"Breakdown: "
                    f"{_to_int(data['breakdown_mold_count'])}"
                ),
            )
            return False

        return True

    def add_mold(self) -> None:
        dialog = MoldDialog(
            self,
            "Add Mold",
        )

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        data = dialog.data()

        if not self._validate_counts(data):
            return

        try:
            self.repo.add_mold(data)
            self.refresh(show_error=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Database Error",
                (
                    "Could not add mold."
                    f"\n\nReason: {exc}"
                ),
            )

    def edit_mold_for_row(
        self,
        row: int,
    ) -> None:
        if row < 0:
            return

        item = self.table.item(
            row,
            0,
        )
        if item is None:
            return

        mold_id = item.data(
            Qt.ItemDataRole.UserRole
        )
        if mold_id is None:
            return

        self.edit_mold(int(mold_id))

    def edit_mold(
        self,
        mold_id: int,
    ) -> None:
        try:
            mold = self.repo.get_mold(
                mold_id
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Database Error",
                (
                    "Could not load selected mold."
                    f"\n\nReason: {exc}"
                ),
            )
            return

        dialog = MoldDialog(
            self,
            "Edit Mold / Add Mold Quantity",
            mold,
        )

        if (
            dialog.exec()
            != QDialog.DialogCode.Accepted
        ):
            return

        data = dialog.data()
        live_plan_reserved = _to_int(
            mold.get(
                "plan_reserved_today"
            )
        )

        if not self._validate_counts(
            data,
            live_plan_reserved,
        ):
            return

        try:
            self.repo.update_mold(
                mold_id,
                data,
            )
            self.refresh(show_error=True)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Database Error",
                (
                    "Could not update mold."
                    f"\n\nReason: {exc}"
                ),
            )

    def _setup_auto_refresh(self) -> None:
        self._configure_table()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(
            self.AUTO_REFRESH_MS
        )
        self.refresh_timer.timeout.connect(
            lambda: self.refresh(
                show_error=False
            )
        )
        self.refresh_timer.start()
