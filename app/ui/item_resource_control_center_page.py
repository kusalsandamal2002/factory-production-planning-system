from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
import re
from typing import Any, Callable

from PySide6.QtCore import QDateTime, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QInputDialog,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine


NO_CASING_VALUES = {
    "",
    "-",
    "n/a",
    "na",
    "none",
    "no",
    "no casing",
    "no casing required",
    "casing not required",
    "not required",
    "not applicable",
    "without casing",
    "without any casing",
}


# NO-CASING NORMALIZATION FIX V5.1
# PRODUCTION LINE CAPACITY CARD REMOVED V5.2
# PROCESS STANDARD PLANNING INTEGRITY V6.5
def _casing_required(value: Any) -> bool:
    """Return False for all supported no-casing descriptions.

    Casing is a hard planning constraint only when the SMDS item
    genuinely requires one. No-casing items must never receive a zero
    capacity, waiting-for-casing status or casing bottleneck.
    """
    normalized = _norm(value)

    # Check the normalized source before removing punctuation.
    # This correctly handles values such as "N/A".
    if normalized in NO_CASING_VALUES:
        return False

    compact = re.sub(
        r"[^a-z0-9]+",
        " ",
        normalized,
    ).strip()

    compact_no_casing_values = {
        re.sub(
            r"[^a-z0-9]+",
            " ",
            item,
        ).strip()
        for item in NO_CASING_VALUES
    }

    if compact in compact_no_casing_values:
        return False

    no_casing_phrases = (
        "no casing",
        "without casing",
        "without any casing",
        "casing not required",
        "casing is not required",
        "does not require casing",
        "not applicable casing",
    )
    return not any(
        phrase in compact
        for phrase in no_casing_phrases
    )


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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if not value:
                return default
        return float(value)
    except Exception:
        return default


def _fmt_int(value: Any) -> str:
    return f"{_to_int(value):,}"


def _fmt_number(value: Any) -> str:
    number = _to_float(value)
    return f"{int(number):,}" if number.is_integer() else f"{number:,.2f}"


def _fmt_date(value: Any) -> str:
    if value is None:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _is_active(status: Any, is_active: Any = True) -> bool:
    if is_active is False:
        return False
    return _norm(status) not in {
        "inactive", "breakdown", "broken", "disabled",
        "maintenance", "out of service", "blocked",
    }


def _split_lines(raw: Any) -> list[str]:
    parts = re.split(r"[,;|/\n]+", str(raw or "").strip())
    return [
        re.sub(r"\s+", " ", part.strip())
        for part in parts
        if _norm(part) not in {"", "-", "n/a", "na", "none", "no", "0"}
    ]


def _line_match(line_name: str, candidates: list[str]) -> bool:
    line = _norm(line_name)
    for candidate in candidates:
        item = _norm(candidate)
        if not item:
            continue
        if line == item or line in item or item in line:
            return True
        line_digits = re.findall(r"\d+", line)
        item_digits = re.findall(r"\d+", item)
        if line_digits and item_digits and line_digits[-1] == item_digits[-1]:
            return True
    return False


class ItemResourceControlCenterPage(QWidget):
    """Item lifecycle, stock, shipment demand and resource control center."""

    def __init__(
        self,
        *,
        current_user=None,
        on_back: Callable[[], None] | None = None,
        on_open_master: Callable[[str], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self.on_back = on_back
        self.on_open_master = on_open_master
        self.sap_code = ""
        self.shipment_item_id: int | None = None
        self.smds: dict[str, Any] = {}
        self.data: dict[str, Any] = {}
        self.lifecycle: dict[str, Any] = {}
        self.events: list[dict[str, Any]] = []
        self._ensure_operational_schema()
        self._build_ui()
        self._apply_styles()
        self._setup_tables()
        self._setup_auto_refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        header = QFrame()
        header.setObjectName("HeaderCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(12)

        top = QHBoxLayout()
        self.back_button = QPushButton("← Back to Shipment Details")
        self.back_button.setObjectName("SecondaryButton")
        self.back_button.clicked.connect(self._go_back)

        title_box = QVBoxLayout()
        self.title_label = QLabel("Item Resource Control Center")
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel(
            "SAP-linked mold, casing, production-line, cavity, oven, "
            "capacity, plan and reservation information."
        )
        self.subtitle_label.setObjectName("Hint")
        self.subtitle_label.setWordWrap(True)
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)

        self.approval_badge = QLabel("NOT LOADED")
        self.approval_badge.setObjectName("NeutralBadge")
        self.approval_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        refresh = QPushButton("Refresh")
        refresh.setObjectName("SecondaryButton")
        refresh.clicked.connect(self.refresh_data)

        top.addWidget(self.back_button)
        top.addLayout(title_box, 1)
        top.addWidget(self.approval_badge)
        top.addWidget(refresh)
        header_layout.addLayout(top)

        identity = QGridLayout()
        identity.setHorizontalSpacing(12)
        identity.setVerticalSpacing(8)
        self.sap_value = QLabel("-")
        self.description_value = QLabel("-")
        self.key_code_value = QLabel("-")
        self.casing_type_value = QLabel("-")
        self.line_value = QLabel("-")
        self.plan_value = QLabel("-")
        self.curing_value = QLabel("-")
        self.handling_value = QLabel("-")
        self.weight_value = QLabel("-")
        self.stock_position_value = QLabel("-")
        identity.addWidget(self._identity("SAP CODE", self.sap_value), 0, 0)
        identity.addWidget(self._identity("MATERIAL DESCRIPTION", self.description_value), 0, 1, 1, 3)
        identity.addWidget(self._identity("MOLD / KEY CODE", self.key_code_value), 1, 0)
        identity.addWidget(self._identity("CASING TYPE", self.casing_type_value), 1, 1)
        identity.addWidget(self._identity("COMPATIBLE LINE", self.line_value), 1, 2)
        identity.addWidget(self._identity("DAY / NIGHT / TOTAL PLAN", self.plan_value), 1, 3)
        identity.addWidget(self._identity("CURING CYCLE", self.curing_value), 2, 0)
        identity.addWidget(self._identity("HANDLING TIME", self.handling_value), 2, 1)
        identity.addWidget(self._identity("WEIGHT / TYRE", self.weight_value), 2, 2)
        identity.addWidget(
            self._identity(
                "CURRENT STOCK POSITION",
                self.stock_position_value,
            ),
            2,
            3,
        )
        header_layout.addLayout(identity)
        root.addWidget(header)

        actions = QFrame()
        actions.setObjectName("ActionBar")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(14, 10, 14, 10)
        caption = QLabel("RESOURCE MANAGEMENT")
        caption.setObjectName("ActionCaption")
        action_layout.addWidget(caption)
        action_layout.addStretch(1)
        self.hold_button = QPushButton("Place Production Hold")
        self.hold_button.setObjectName("WarningButton")
        self.hold_button.clicked.connect(self._place_hold)
        self.release_hold_button = QPushButton("Release Hold")
        self.release_hold_button.setObjectName("SuccessButton")
        self.release_hold_button.clicked.connect(self._release_hold)
        self.note_button = QPushButton("Add Operational Note")
        self.note_button.setObjectName("SecondaryButton")
        self.note_button.clicked.connect(self._add_note)
        action_layout.addWidget(self.hold_button)
        action_layout.addWidget(self.release_hold_button)
        action_layout.addWidget(self.note_button)
        for label, target in (
            ("Manage Molds", "molds"),
            ("Manage Casings", "casings"),
            ("Manage Cavities", "cavities"),
            ("Manage Lines / Ovens", "lines"),
        ):
            action_layout.addWidget(self._manage_button(label, target))
        root.addWidget(actions)

        status_card = QFrame()
        status_card.setObjectName("StatusCard")
        status_root = QVBoxLayout(status_card)
        status_root.setContentsMargins(18, 14, 18, 14)
        status_root.setSpacing(10)

        status_top = QHBoxLayout()
        status_top.setSpacing(12)

        status_left = QVBoxLayout()
        status_left.setSpacing(3)
        status_caption = QLabel(
            "CURRENT ITEM PRODUCTION & DEMAND STATUS"
        )
        status_caption.setObjectName("StatusCaption")
        self.lifecycle_status = QLabel("NOT LOADED")
        self.lifecycle_status.setObjectName("LifecycleNeutral")
        self.lifecycle_summary = QLabel(
            "Load a SAP item to calculate its stock, shipment demand "
            "and production position."
        )
        self.lifecycle_summary.setObjectName("StatusSummary")
        self.lifecycle_summary.setWordWrap(True)
        status_left.addWidget(status_caption)
        status_left.addWidget(self.lifecycle_status)
        status_left.addWidget(self.lifecycle_summary)

        next_action_box = QFrame()
        next_action_box.setObjectName("NextActionCard")
        next_action_layout = QVBoxLayout(next_action_box)
        next_action_layout.setContentsMargins(14, 10, 14, 10)
        next_action_layout.setSpacing(3)
        next_action_caption = QLabel("NEXT BEST ACTION")
        next_action_caption.setObjectName("StatusMiniCaption")
        self.status_values: dict[str, QLabel] = {}
        next_action_value = QLabel("-")
        next_action_value.setObjectName("NextActionValue")
        next_action_value.setWordWrap(True)
        self.status_values["next_action"] = next_action_value
        next_action_layout.addWidget(next_action_caption)
        next_action_layout.addWidget(next_action_value)

        status_top.addLayout(status_left, 2)
        status_top.addWidget(next_action_box, 1)
        status_root.addLayout(status_top)

        status_metrics = QGridLayout()
        status_metrics.setHorizontalSpacing(9)
        status_metrics.setVerticalSpacing(8)

        for index, (key, title) in enumerate((
            ("current_stock", "Current Physical Stock"),
            ("unallocated_stock", "Unallocated Stock"),
            ("total_qty", "Total Shipment Quantity"),
            ("stock_allocated", "Stock Allocated"),
            ("production_required", "Production Required"),
            ("progress", "Fulfilment Progress"),
        )):
            label = QLabel("-")
            label.setObjectName("StatusMetricValue")
            label.setWordWrap(True)
            self.status_values[key] = label

            box = QFrame()
            box.setObjectName("StatusMiniCard")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(12, 8, 12, 8)
            box_layout.setSpacing(2)
            cap = QLabel(title)
            cap.setObjectName("StatusMiniCaption")
            box_layout.addWidget(cap)
            box_layout.addWidget(label)
            status_metrics.addWidget(
                box,
                index // 3,
                index % 3,
            )

        status_root.addLayout(status_metrics)

        schedule_row = QHBoxLayout()
        schedule_row.setSpacing(9)
        for key, title in (
            ("next_start", "Next Production Start"),
            ("finish", "Expected Completion"),
        ):
            label = QLabel("-")
            label.setObjectName("ScheduleValue")
            label.setWordWrap(True)
            self.status_values[key] = label

            box = QFrame()
            box.setObjectName("ScheduleCard")
            box_layout = QHBoxLayout(box)
            box_layout.setContentsMargins(12, 7, 12, 7)
            box_layout.setSpacing(8)
            cap = QLabel(title)
            cap.setObjectName("ScheduleCaption")
            box_layout.addWidget(cap)
            box_layout.addStretch(1)
            box_layout.addWidget(label)
            schedule_row.addWidget(box, 1)

        self.priority_rule_value = QLabel(
            "Priority rule: earliest Target Date first; stock is allocated "
            "before production; remaining demand is planned cumulatively "
            "without overlapping higher-priority shipments."
        )
        self.priority_rule_value.setObjectName("PriorityRuleBanner")
        self.priority_rule_value.setWordWrap(True)
        schedule_row.addWidget(self.priority_rule_value, 2)

        status_root.addLayout(schedule_row)
        root.addWidget(status_card)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(10)

        self.resource_capacity_values: dict[
            str,
            dict[str, QLabel],
        ] = {}
        self.resource_capacity_cards: dict[
            str,
            QFrame,
        ] = {}
        self.resource_capacity_titles: dict[
            str,
            QLabel,
        ] = {}
        self.resource_capacity_hints: dict[
            str,
            QLabel,
        ] = {}
        self.resource_capacity_captions: dict[
            str,
            dict[str, QLabel],
        ] = {}

        resource_definitions = (
            (
                "mold",
                "Mold Capacity",
                "All matching physical molds, free units and units assigned "
                "to this SAP item.",
            ),
            (
                "casing",
                "Casing Capacity",
                "All matching casing units, free units and units assigned "
                "to this SAP item.",
            ),
            (
                "cavity",
                "Cavity Capacity",
                "All compatible cavities, currently free cavities and "
                "cavities assigned to this SAP item.",
            ),
        )

        # Three operational resource cards fill the full row.
        # Production-line details remain available in Lines & Cavities,
        # but the separate Production Line Capacity card is intentionally
        # removed to avoid duplicating the cavity-capacity information.
        for column, (
            key,
            title,
            hint,
        ) in enumerate(resource_definitions):
            metrics.addWidget(
                self._resource_capacity_card(
                    key,
                    title,
                    hint,
                ),
                0,
                column * 4,
                1,
                4,
            )

        self.metric_labels: dict[str, QLabel] = {}
        summary_definitions = (
            (
                "physical",
                "Maximum Physical Capacity",
                "Maximum simultaneous capacity before current live "
                "commitments.",
            ),
            (
                "committed",
                "Assigned Capacity — This Item",
                "Simultaneous capacity already reserved or planned for "
                "this SAP item.",
            ),
            (
                "free_additional",
                "Additional Free Capacity",
                "Extra simultaneous capacity still available after all "
                "current assignments.",
            ),
            (
                "daily_output",
                "Daily Output Capacity",
                "Maximum output and additional free output using the SMDS "
                "total plan.",
            ),
        )

        for column, (
            key,
            title,
            hint,
        ) in enumerate(summary_definitions):
            value = QLabel("0")
            self.metric_labels[key] = value
            metrics.addWidget(
                self._metric(
                    value,
                    title,
                    hint,
                ),
                1,
                column * 3,
                1,
                3,
            )

        for grid_column in range(12):
            metrics.setColumnStretch(
                grid_column,
                1,
            )

        root.addLayout(metrics)

        bottleneck = QFrame()
        bottleneck.setObjectName("BottleneckCard")
        bottle_layout = QHBoxLayout(bottleneck)
        bottle_layout.setContentsMargins(18, 13, 18, 13)
        left = QVBoxLayout()
        cap = QLabel("CURRENT CAPACITY BOTTLENECK")
        cap.setObjectName("BottleneckCaption")
        self.bottleneck_value = QLabel("Load a SAP item to calculate.")
        self.bottleneck_value.setObjectName("BottleneckValue")
        left.addWidget(cap)
        left.addWidget(self.bottleneck_value)
        self.capacity_formula = QLabel("-")
        self.capacity_formula.setObjectName("FormulaLabel")
        self.capacity_formula.setWordWrap(True)
        self.capacity_formula.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottle_layout.addLayout(left, 1)
        bottle_layout.addWidget(self.capacity_formula, 2)
        root.addWidget(bottleneck)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("ResourceTabs")
        self.lifecycle_tab = QWidget()
        self.overview_tab = QWidget()
        self.mold_tab = QWidget()
        self.casing_tab = QWidget()
        self.cavity_tab = QWidget()
        self.oven_tab = QWidget()
        self.plan_tab = QWidget()
        self.history_tab = QWidget()
        for widget, title in (
            (self.lifecycle_tab, "Lifecycle & Shipments"),
            (self.overview_tab, "Resource Overview"),
            (self.mold_tab, "Molds"),
            (self.casing_tab, "Casings"),
            (self.cavity_tab, "Lines & Cavities"),
            (self.oven_tab, "Ovens"),
            (self.plan_tab, "Plans & Reservations"),
            (self.history_tab, "Operational History"),
        ):
            self.tabs.addTab(widget, title)

        self._build_lifecycle_tab()
        self._build_overview_tab()
        self.mold_table = self._make_tab(
            self.mold_tab,
            "Matching Mold Capacity",
            "Double-click a row to open Mold Master.",
            ["Key Code", "Description", "Status", "Total", "In Production", "Breakdown", "Master Reserved", "Reserved Today", "Available Now", "Remarks"],
            "Add / Edit Molds", "molds",
        )
        self.casing_table = self._make_tab(
            self.casing_tab,
            "Matching Casing Capacity",
            "Double-click a row to open Casing Master.",
            ["Casing Type", "Code", "Status", "Total", "In Production", "Breakdown", "Master Reserved", "Reserved Today", "Available Now", "Remarks"],
            "Add / Edit Casings", "casings",
        )
        self.cavity_table = self._make_tab(
            self.cavity_tab,
            "Compatible Production Lines and Cavities",
            "Only cavities mapped to compatible SMDS production lines are counted.",
            ["Line", "Cavity", "Cavity Code", "Status", "Active", "Assigned Tyre", "Reserved Today", "Latest Oven", "Current SAP Plan", "Availability"],
            "Add / Edit Cavities", "cavities",
        )
        self.oven_table = self._make_tab(
            self.oven_tab,
            "Oven Register and Current Item Usage",
            "Oven use is derived from saved cavity plans for this SAP code.",
            ["Oven Code", "Oven Name", "Active", "Used by This SAP", "Latest Plan Date", "Current Lines / Cavities"],
            "Manage Lines / Ovens", "lines",
        )
        self._build_plan_tab()
        self._build_history_tab()
        root.addWidget(self.tabs, 1)

    def _identity(self, caption: str, value: QLabel) -> QFrame:
        frame = QFrame()
        frame.setObjectName("IdentityField")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        c = QLabel(caption)
        c.setObjectName("IdentityCaption")
        value.setObjectName("IdentityValue")
        value.setWordWrap(True)
        layout.addWidget(c)
        layout.addWidget(value)
        return frame

    def _resource_capacity_card(
        self,
        key: str,
        title: str,
        hint: str,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("ResourceCapacityCard")
        card.setMinimumHeight(142)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            15,
            12,
            15,
            12,
        )
        layout.setSpacing(7)

        title_label = QLabel(title)
        title_label.setObjectName(
            "ResourceCardTitle"
        )

        hint_label = QLabel(hint)
        hint_label.setObjectName(
            "ResourceCardHint"
        )
        hint_label.setWordWrap(True)

        values_row = QHBoxLayout()
        values_row.setSpacing(6)

        values: dict[str, QLabel] = {}
        captions: dict[str, QLabel] = {}

        for value_key, caption in (
            ("total", "Total Compatible"),
            ("available", "Available Free"),
            ("assigned", "Assigned This Item"),
        ):
            box = QFrame()
            box.setObjectName(
                "ResourceValueBox"
            )

            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(
                8,
                7,
                8,
                7,
            )
            box_layout.setSpacing(1)

            value = QLabel("0")
            value.setObjectName(
                "ResourceValue"
            )
            value.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            caption_label = QLabel(caption)
            caption_label.setObjectName(
                "ResourceValueCaption"
            )
            caption_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            caption_label.setWordWrap(True)

            box_layout.addWidget(value)
            box_layout.addWidget(
                caption_label
            )
            values_row.addWidget(box, 1)
            values[value_key] = value
            captions[value_key] = caption_label

        self.resource_capacity_values[
            key
        ] = values
        self.resource_capacity_cards[
            key
        ] = card
        self.resource_capacity_titles[
            key
        ] = title_label
        self.resource_capacity_hints[
            key
        ] = hint_label
        self.resource_capacity_captions[
            key
        ] = captions

        layout.addWidget(title_label)
        layout.addWidget(hint_label)
        layout.addLayout(values_row)

        return card

    def _metric(self, value: QLabel, title: str, hint: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setMinimumHeight(112)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)
        value.setObjectName("MetricValue")
        value.setWordWrap(True)
        title_label = QLabel(title)
        title_label.setObjectName("MetricTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("MetricHint")
        hint_label.setWordWrap(True)
        layout.addWidget(value)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)
        layout.addStretch(1)
        return card

    def _manage_button(self, title: str, target: str) -> QPushButton:
        button = QPushButton(title)
        button.setObjectName("ManageButton")
        button.clicked.connect(lambda checked=False, key=target: self._open_master(key))
        return button

    def _section_header(self, title: str, description: str, action: tuple[str, str] | None = None) -> QHBoxLayout:
        row = QHBoxLayout()
        box = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        hint = QLabel(description)
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        box.addWidget(title_label)
        box.addWidget(hint)
        row.addLayout(box, 1)
        if action:
            row.addWidget(self._manage_button(*action))
        return row

    def _make_tab(self, tab: QWidget, title: str, description: str, headers: list[str], action_title: str, action_target: str) -> QTableWidget:
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addLayout(self._section_header(title, description, (action_title, action_target)))
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        layout.addWidget(table, 1)
        return table

    def _build_lifecycle_tab(self) -> None:
        layout = QVBoxLayout(self.lifecycle_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addLayout(self._section_header(
            "Shipment-wise Demand and Main-Rule Production Plan",
            "Every shipment requiring this SAP item is ranked by the main "
            "planning rule and shown with stock allocation, production "
            "requirement, progress and planned start/finish times.",
        ))

        demand_card = QFrame()
        demand_card.setObjectName("ShipmentDemandCard")
        demand_layout = QVBoxLayout(demand_card)
        demand_layout.setContentsMargins(14, 12, 14, 12)
        demand_layout.setSpacing(9)

        demand_summary = QHBoxLayout()
        demand_summary.setSpacing(8)
        self.demand_summary_values: dict[str, QLabel] = {}

        for key, title in (
            ("shipments", "Active Shipments"),
            ("total_qty", "Total Shipment Qty"),
            ("stock_allocated", "Stock Allocated"),
            ("production_required", "Production Required"),
            ("progress", "Fulfilment Progress"),
        ):
            box = QFrame()
            box.setObjectName("DemandSummaryCard")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(12, 8, 12, 8)
            box_layout.setSpacing(2)

            value = QLabel("0")
            value.setObjectName("DemandSummaryValue")
            caption = QLabel(title)
            caption.setObjectName("DemandSummaryCaption")

            self.demand_summary_values[key] = value
            box_layout.addWidget(value)
            box_layout.addWidget(caption)
            demand_summary.addWidget(box, 1)

        demand_layout.addLayout(demand_summary)

        self.lifecycle_notice = QLabel(
            "MAIN RULE: earliest Target Date receives priority first. "
            "Available unallocated stock is assigned first; the remaining "
            "quantity is then planned cumulatively using mold, casing, "
            "compatible cavity and oven capacity. Planned Start and Finish "
            "come only from saved cavity-plan rows."
        )
        self.lifecycle_notice.setObjectName("PriorityRuleBanner")
        self.lifecycle_notice.setWordWrap(True)
        demand_layout.addWidget(self.lifecycle_notice)

        self.lifecycle_shipment_table = QTableWidget(0, 15)
        self.lifecycle_shipment_table.setHorizontalHeaderLabels([
            "Priority",
            "Shipment Name",
            "Shipment ID",
            "Target Date",
            "Required Qty",
            "Stock Allocated",
            "Production Required",
            "Produced",
            "Completed",
            "Remaining",
            "Fulfilment %",
            "Planned Start",
            "Planned Finish",
            "Receive Date",
            "Plan Status",
        ])
        demand_layout.addWidget(self.lifecycle_shipment_table, 1)
        layout.addWidget(demand_card, 2)

        current_label = QLabel("Current / Next Production Position")
        current_label.setObjectName("SubsectionTitle")
        layout.addWidget(current_label)

        self.current_production_table = QTableWidget(0, 12)
        self.current_production_table.setHorizontalHeaderLabels([
            "Position",
            "Plan Date",
            "Start",
            "Finish",
            "Shift",
            "Line",
            "Cavity",
            "Oven",
            "Shipment Name",
            "Qty",
            "Status",
            "Risk / Note",
        ])
        layout.addWidget(self.current_production_table, 1)

    def _build_history_tab(self) -> None:
        layout = QVBoxLayout(self.history_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addLayout(self._section_header(
            "Operational Hold and Audit History",
            "Production holds, releases and operational notes are stored as auditable item events. Resource master changes continue through the existing master-data modules.",
        ))
        self.event_table = QTableWidget(0, 8)
        self.event_table.setHorizontalHeaderLabels([
            "Started At", "Ended At", "Event", "Status", "Reason / Note", "Shipment Item", "Created By", "Closed By",
        ])
        layout.addWidget(self.event_table, 1)

    def _build_overview_tab(self) -> None:
        layout = QVBoxLayout(self.overview_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        layout.addLayout(self._section_header(
            "Operational Capacity Summary",
            "The page shows full physical capacity and current available capacity separately, with the exact limiting resource.",
        ))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.overview_values: dict[str, QLabel] = {}
        for index, (key, title) in enumerate((
            ("mold", "Mold Position"),
            ("casing", "Casing Position"),
            ("cavity", "Cavity Position"),
            ("oven", "Oven Position"),
            ("plan", "Current Production Plan"),
            ("reservation", "Active Reservations"),
        )):
            label = QLabel("-")
            self.overview_values[key] = label
            card = QFrame()
            card.setObjectName("SummaryCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 13, 16, 13)
            t = QLabel(title)
            t.setObjectName("SummaryTitle")
            label.setObjectName("SummaryValue")
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            card_layout.addWidget(t)
            card_layout.addWidget(label)
            card_layout.addStretch(1)
            grid.addWidget(card, index // 3, index % 3)
        layout.addLayout(grid)
        layout.addStretch(1)

    def _build_plan_tab(self) -> None:
        layout = QVBoxLayout(self.plan_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addLayout(self._section_header(
            "Shipment Demand and Current Reservations",
            "Live demand, cavity/oven plan rows and resource reservations connected to this SAP item.",
        ))
        self.shipment_table = QTableWidget(0, 10)
        self.shipment_table.setHorizontalHeaderLabels([
            "Shipment Name",
            "Shipment ID",
            "Order Qty",
            "Stock Allocated",
            "Production Required",
            "Produced",
            "Completed",
            "Remaining",
            "Fulfilment %",
            "Status",
        ])
        self.plan_table = QTableWidget(0, 10)
        self.plan_table.setHorizontalHeaderLabels([
            "Plan Date", "Shift", "Line", "Cavity", "Oven", "Qty", "Mold", "Casing", "Status", "Risk / Note",
        ])
        self.reservation_table = QTableWidget(0, 8)
        self.reservation_table.setHorizontalHeaderLabels([
            "Date", "Resource Type", "Resource Key", "Reserved Qty", "Capacity Qty", "Shipment Name", "Shipment ID", "Note",
        ])
        for title, table in (
            ("Shipment Demand", self.shipment_table),
            ("Cavity / Oven Plans", self.plan_table),
            ("Resource Reservations", self.reservation_table),
        ):
            label = QLabel(title)
            label.setObjectName("SubsectionTitle")
            layout.addWidget(label)
            layout.addWidget(table, 1)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget { font-family: "Segoe UI"; }
            QFrame#HeaderCard, QFrame#MetricCard, QFrame#ResourceCapacityCard,
            QFrame#SummaryCard, QFrame#ActionBar,
            QFrame#StatusCard, QFrame#StatusMiniCard, QFrame#ScheduleCard,
            QFrame#ShipmentDemandCard, QFrame#DemandSummaryCard,
            QFrame#NextActionCard {
                background:#ffffff; border:1px solid #dbe4f0; border-radius:14px;
            }
            QFrame#ResourceCapacityCard {
                background:#ffffff;
                border-color:#cbd5e1;
            }
            QFrame#NoCasingResourceCard {
                background:#ecfdf5;
                border:1px solid #86efac;
                border-radius:14px;
            }
            QFrame#ResourceValueBox {
                background:#f8fafc;
                border:1px solid #e2e8f0;
                border-radius:9px;
            }
            QFrame#ShipmentDemandCard {
                background:#f8fafc;
            }
            QFrame#DemandSummaryCard {
                background:#ffffff;
                border-radius:10px;
            }
            QFrame#NextActionCard {
                background:#eff6ff;
                border-color:#bfdbfe;
            }
            QFrame#IdentityField { background:#f8fafc; border:1px solid #e2e8f0; border-radius:9px; }
            QFrame#BottleneckCard { background:#0f172a; border:1px solid #1e293b; border-radius:13px; }
            QLabel#PageTitle { color:#0f172a; font-size:22pt; font-weight:950; }
            QLabel#SectionTitle { color:#0f172a; font-size:15pt; font-weight:950; }
            QLabel#SubsectionTitle { color:#1e293b; font-size:10.5pt; font-weight:950; }
            QLabel#Hint { color:#64748b; font-size:9.5pt; font-weight:650; }
            QLabel#IdentityCaption { color:#64748b; font-size:8pt; font-weight:900; }
            QLabel#IdentityValue { color:#0f172a; font-size:10.5pt; font-weight:900; }
            QLabel#MetricValue { color:#0f172a; font-size:20pt; font-weight:950; }
            QLabel#MetricTitle { color:#334155; font-size:9pt; font-weight:900; }
            QLabel#MetricHint { color:#64748b; font-size:8pt; font-weight:650; }
            QLabel#ResourceCardTitle {
                color:#0f172a;
                font-size:11pt;
                font-weight:950;
            }
            QLabel#ResourceCardHint {
                color:#64748b;
                font-size:7.8pt;
                font-weight:650;
            }
            QLabel#ResourceValue {
                color:#0f172a;
                font-size:16pt;
                font-weight:950;
            }
            QLabel#NoCasingValue {
                color:#047857;
                font-size:11.5pt;
                font-weight:950;
            }
            QLabel#ResourceValueCaption {
                color:#64748b;
                font-size:7pt;
                font-weight:850;
            }
            QLabel#SummaryTitle { color:#475569; font-size:8.5pt; font-weight:900; }
            QLabel#SummaryValue { color:#0f172a; font-size:10pt; font-weight:750; }
            QLabel#ActionCaption { color:#64748b; font-size:8.5pt; font-weight:950; }
            QLabel#StatusCaption, QLabel#StatusMiniCaption { color:#64748b; font-size:8pt; font-weight:950; }
            QLabel#StatusSummary { color:#475569; font-size:9pt; font-weight:700; }
            QLabel#StatusValue { color:#0f172a; font-size:10pt; font-weight:900; }
            QLabel#LifecycleNeutral, QLabel#LifecycleQueued, QLabel#LifecycleRunning,
            QLabel#LifecycleHold, QLabel#LifecycleComplete, QLabel#LifecycleBlocked {
                border-radius:9px; padding:7px 11px; font-size:13pt; font-weight:950;
            }
            QLabel#LifecycleNeutral { background:#e2e8f0; color:#334155; border:1px solid #cbd5e1; }
            QLabel#LifecycleQueued { background:#dbeafe; color:#1d4ed8; border:1px solid #bfdbfe; }
            QLabel#LifecycleRunning { background:#dcfce7; color:#047857; border:1px solid #bbf7d0; }
            QLabel#LifecycleHold, QLabel#LifecycleBlocked { background:#fee2e2; color:#b91c1c; border:1px solid #fecaca; }
            QLabel#LifecycleComplete { background:#ccfbf1; color:#0f766e; border:1px solid #99f6e4; }
            QLabel#InfoBanner { background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe; border-radius:9px; padding:9px 11px; font-weight:750; }
            QLabel#StatusMetricValue {
                color:#0f172a; font-size:14pt; font-weight:950;
            }
            QLabel#NextActionValue {
                color:#1e3a8a; font-size:10pt; font-weight:850;
            }
            QLabel#ScheduleCaption {
                color:#64748b; font-size:8.5pt; font-weight:900;
            }
            QLabel#ScheduleValue {
                color:#0f172a; font-size:9.5pt; font-weight:900;
            }
            QLabel#PriorityRuleBanner {
                background:#eff6ff; color:#1e40af;
                border:1px solid #bfdbfe; border-radius:9px;
                padding:8px 10px; font-weight:750;
            }
            QLabel#DemandSummaryValue {
                color:#0f172a; font-size:16pt; font-weight:950;
            }
            QLabel#DemandSummaryCaption {
                color:#64748b; font-size:8pt; font-weight:900;
            }
            QLabel#BottleneckCaption { color:#94a3b8; font-size:8pt; font-weight:950; }
            QLabel#BottleneckValue { color:#ffffff; font-size:13pt; font-weight:950; }
            QLabel#FormulaLabel { color:#cbd5e1; font-size:9.5pt; font-weight:750; }
            QLabel#NeutralBadge { background:#e2e8f0; color:#334155; border:1px solid #cbd5e1; border-radius:10px; padding:8px 13px; font-weight:950; }
            QLabel#ApprovedBadge { background:#dcfce7; color:#047857; border:1px solid #bbf7d0; border-radius:10px; padding:8px 13px; font-weight:950; }
            QLabel#PendingBadge { background:#fef3c7; color:#92400e; border:1px solid #fde68a; border-radius:10px; padding:8px 13px; font-weight:950; }
            QPushButton#SecondaryButton { background:#e2e8f0; color:#0f172a; border:none; border-radius:10px; padding:10px 16px; font-weight:900; min-height:25px; }
            QPushButton#ManageButton { background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe; border-radius:9px; padding:8px 13px; font-weight:900; }
            QPushButton#ManageButton:hover { background:#dbeafe; }
            QPushButton#WarningButton { background:#fff7ed; color:#c2410c; border:1px solid #fed7aa; border-radius:9px; padding:8px 13px; font-weight:900; }
            QPushButton#SuccessButton { background:#ecfdf5; color:#047857; border:1px solid #a7f3d0; border-radius:9px; padding:8px 13px; font-weight:900; }
            QTabWidget::pane { background:#ffffff; border:1px solid #dbe4f0; border-radius:12px; top:-1px; }
            QTabBar::tab { background:#e2e8f0; color:#334155; border:1px solid #cbd5e1; padding:9px 16px; font-weight:850; }
            QTabBar::tab:selected { background:#2563eb; color:#ffffff; border-color:#2563eb; }
            QTableWidget { background:#ffffff; color:#0f172a; border:1px solid #dbe4f0; border-radius:9px; gridline-color:#e2e8f0; alternate-background-color:#f8fafc; selection-background-color:#dbeafe; selection-color:#0f172a; }
            QTableWidget::item { padding:7px 8px; }
            QHeaderView::section { background:#eef2f7; color:#1e293b; border:none; border-right:1px solid #dbe4f0; border-bottom:1px solid #dbe4f0; padding:8px 7px; font-weight:950; }
        """)

    def _setup_tables(self) -> None:
        tables = [
            self.current_production_table, self.lifecycle_shipment_table,
            self.mold_table, self.casing_table, self.cavity_table,
            self.oven_table, self.shipment_table, self.plan_table,
            self.reservation_table, self.event_table,
        ]
        for table in tables:
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setAlternatingRowColors(True)
            table.setWordWrap(False)
            table.setSortingEnabled(True)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(38)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            header = table.horizontalHeader()
            header.setStretchLastSection(False)
            for column in range(table.columnCount()):
                header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
            if table.columnCount() > 1:
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.mold_table.cellDoubleClicked.connect(lambda *_: self._open_master("molds"))
        self.casing_table.cellDoubleClicked.connect(lambda *_: self._open_master("casings"))
        self.cavity_table.cellDoubleClicked.connect(lambda *_: self._open_master("cavities"))
        self.oven_table.cellDoubleClicked.connect(lambda *_: self._open_master("lines"))

    def load_item(self, sap_code: str, shipment_item_id: int | None = None) -> None:
        self.sap_code = str(sap_code or "").strip()
        self.shipment_item_id = int(shipment_item_id) if shipment_item_id else None
        if not self.sap_code:
            QMessageBox.warning(self, "SAP Code Required", "The selected row has no valid SAP code.")
            return
        self.refresh_data()

    def refresh_data(self) -> None:
        if not self.sap_code:
            return
        try:
            self._load_data()
            self._calculate_capacity()
            self._render()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Item Resource Control Center",
                f"The resource data could not be loaded.\n\nReason: {exc}",
            )

    def _line_candidates(self) -> list[str]:
        candidates = _split_lines(self.smds.get("line"))
        aliases = {
            "line_400": "400", "line_800": "800", "press_line": "Press",
            "nancy_press": "Nancy", "press_400_t": "400 T",
            "t_600_01_press": "600 01", "t_600_02_press": "600 02",
            "l_press_1250": "1250", "l_press_1500": "1500",
            "l_press_1800": "1800", "oring_press": "O Ring",
            "new_press": "New Press",
        }
        for field, label in aliases.items():
            raw = self.smds.get(field)
            if _norm(raw) not in {"", "-", "0", "no", "n/a", "na", "none"}:
                candidates.extend(_split_lines(raw))
                candidates.append(label)
        result: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = _norm(candidate)
            if key and key not in seen:
                result.append(candidate)
                seen.add(key)
        return result

    def _load_data(self) -> None:
        today = date.today()
        with engine.begin() as connection:
            smds_row = connection.execute(text("""
                SELECT * FROM smds
                WHERE TRIM(sap_code) = TRIM(:sap_code)
                ORDER BY id DESC LIMIT 1
            """), {"sap_code": self.sap_code}).mappings().first()
            self.smds = dict(smds_row) if smds_row else {}
            key_code = str(self.smds.get("key_code") or "").strip()
            casing_type = str(self.smds.get("casing_type") or "").strip()
            casing_required = _casing_required(casing_type)

            molds = connection.execute(text("""
                SELECT * FROM mold_master
                WHERE LOWER(TRIM(COALESCE(NULLIF(key_code, ''), mold_key_code)))
                    = LOWER(TRIM(:key_code))
                ORDER BY id
            """), {"key_code": key_code}).mappings().all() if key_code else []

            casings = connection.execute(text("""
                SELECT * FROM casing_master
                WHERE LOWER(TRIM(casing_type)) = LOWER(TRIM(:casing_type))
                ORDER BY id
            """), {"casing_type": casing_type}).mappings().all() if casing_required else []

            all_cavities = [dict(row) for row in connection.execute(text("""
                SELECT * FROM production_line_cavities
                ORDER BY line_name, display_order, cavity_no, id
            """)).mappings().all()]
            line_candidates = self._line_candidates()
            cavities = [row for row in all_cavities if _line_match(str(row.get("line_name") or ""), line_candidates)]

            latest_plan = {
                _to_int(row.get("cavity_id")): dict(row)
                for row in connection.execute(text("""
                    SELECT DISTINCT ON (cavity_id)
                        cavity_id, line_name, cavity_no, oven_no,
                        plan_date, tyre_code, allocation_status
                    FROM mpps_cavity_plan_rows
                    ORDER BY cavity_id, plan_date DESC, end_minute DESC,
                             sequence_no DESC, id DESC
                """)).mappings().all()
            }
            sap_cavity_ids = {
                _to_int(row.get("cavity_id"))
                for row in connection.execute(text("""
                    SELECT DISTINCT cavity_id
                    FROM mpps_cavity_plan_rows
                    WHERE TRIM(tyre_code) = TRIM(:sap_code)
                      AND plan_date >= :today
                      AND UPPER(COALESCE(allocation_status, ''))
                          NOT IN ('BREAKDOWN', 'BLOCKED')
                """), {"sap_code": self.sap_code, "today": today}).mappings().all()
            }
            line_reservations = {
                _norm(row.get("resource_key")): _to_int(row.get("reserved_qty"))
                for row in connection.execute(text("""
                    SELECT resource_key, COALESCE(SUM(reserved_qty), 0) reserved_qty
                    FROM planning_resource_reservations
                    WHERE reservation_date = :today
                      AND resource_type = 'line_cavity'
                    GROUP BY resource_key
                """), {"today": today}).mappings().all()
            }
            for cavity in cavities:
                latest = latest_plan.get(_to_int(cavity.get("id")), {})
                cavity["_latest_oven"] = str(latest.get("oven_no") or "-")
                cavity["_current_sap_plan"] = _to_int(cavity.get("id")) in sap_cavity_ids

            ovens = [dict(row) for row in connection.execute(text("SELECT * FROM ovens ORDER BY oven_code, id")).mappings().all()]
            plans = [dict(row) for row in connection.execute(text("""
                SELECT id, plan_date, shift_name, line_name, cavity_id,
                       cavity_no, oven_no, start_minute, end_minute,
                       shipment_id, shipment_item_id, today_qty,
                       total_to_be_produced, balance, mold_type, casing_type,
                       allocation_status, risk_reason, created_at, updated_at
                FROM mpps_cavity_plan_rows
                WHERE TRIM(tyre_code) = TRIM(:sap_code)
                ORDER BY plan_date DESC, start_minute DESC, cavity_no
                LIMIT 300
            """), {"sap_code": self.sap_code}).mappings().all()]
            reservations = [dict(row) for row in connection.execute(text("""
                SELECT r.id, r.reservation_date, r.resource_type,
                       r.resource_key, r.reserved_qty, r.capacity_qty,
                       r.shipment_id, r.shipment_item_id, s.shipment_name,
                       s.shipment_no, r.note, r.created_at
                FROM planning_resource_reservations r
                LEFT JOIN mpps_shipments s ON s.id = r.shipment_id
                WHERE TRIM(r.sap_code) = TRIM(:sap_code)
                ORDER BY r.reservation_date, r.resource_type, r.id
                LIMIT 500
            """), {"sap_code": self.sap_code}).mappings().all()]
            shipments = [dict(row) for row in connection.execute(text("""
                SELECT i.id AS shipment_item_id, i.shipment_id,
                       s.shipment_name, s.shipment_no, s.target_date,
                       s.factory_can_receive_date, s.status AS shipment_status,
                       s.planning_status, i.quantity, i.stock_allocated_qty,
                       i.production_required_qty, i.produced_qty,
                       i.completed_qty, i.remaining_qty, i.progress_pct,
                       i.start_date, i.end_date, i.item_receive_date,
                       i.item_status, i.planning_note, i.schedule_reason,
                       i.allocated_cavity_count, i.daily_capacity
                FROM mpps_shipment_items i
                JOIN mpps_shipments s ON s.id = i.shipment_id
                WHERE TRIM(i.sap_code) = TRIM(:sap_code)
                ORDER BY s.target_date NULLS LAST,
                         s.created_at, s.id, i.id
            """), {"sap_code": self.sap_code}).mappings().all()]

            stock_table_exists = bool(connection.execute(text(
                "SELECT to_regclass('public.mpps_sap_stock_items') IS NOT NULL"
            )).scalar())

            stock_item = {}
            if stock_table_exists:
                stock_row = connection.execute(text("""
                    SELECT
                        COALESCE(fg_stock, 0)::INTEGER AS fg_stock,
                        COALESCE(qc_stock, 0)::INTEGER AS qc_stock,
                        COALESCE(scrap_stock, 0)::INTEGER AS scrap_stock,
                        COALESCE(blocked_stock, 0)::INTEGER AS blocked_stock,
                        GREATEST(
                            COALESCE(fg_stock, 0)
                            + COALESCE(qc_stock, 0)
                            - COALESCE(scrap_stock, 0)
                            - COALESCE(blocked_stock, 0),
                            0
                        )::INTEGER AS physical_available_stock,
                        updated_at
                    FROM mpps_sap_stock_items
                    WHERE TRIM(sap_code) = TRIM(:sap_code)
                    ORDER BY updated_at DESC NULLS LAST, id DESC
                    LIMIT 1
                """), {"sap_code": self.sap_code}).mappings().first()
                stock_item = dict(stock_row) if stock_row else {}

            events = [dict(row) for row in connection.execute(text("""
                SELECT id, sap_code, shipment_item_id, event_type,
                       event_status, reason, started_at, ended_at,
                       created_by, closed_by, created_at, updated_at
                FROM item_operational_events
                WHERE TRIM(sap_code) = TRIM(:sap_code)
                ORDER BY started_at DESC, id DESC
                LIMIT 500
            """), {"sap_code": self.sap_code}).mappings().all()]

            mold_reserved = connection.execute(text("""
                SELECT COALESCE(SUM(reserved_qty), 0)
                FROM planning_resource_reservations
                WHERE reservation_date = :today AND resource_type = 'mold'
                  AND LOWER(TRIM(resource_key)) = LOWER(TRIM(:key_code))
            """), {"today": today, "key_code": key_code}).scalar_one() if key_code else 0
            casing_reserved = connection.execute(text("""
                SELECT COALESCE(SUM(reserved_qty), 0)
                FROM planning_resource_reservations
                WHERE reservation_date = :today AND resource_type = 'casing'
                  AND LOWER(TRIM(resource_key)) = LOWER(TRIM(:casing_type))
            """), {"today": today, "casing_type": casing_type}).scalar_one() if casing_required else 0

        self.data = {
            "today": today,
            "key_code": key_code,
            "casing_type": casing_type,
            "casing_required": casing_required,
            "molds": [dict(row) for row in molds],
            "casings": [dict(row) for row in casings],
            "cavities": cavities,
            "ovens": ovens,
            "plans": plans,
            "reservations": reservations,
            "shipments": shipments,
            "stock_item": stock_item,
            "events": events,
            "line_reservations": line_reservations,
            "mold_reserved_today": _to_int(mold_reserved),
            "casing_reserved_today": _to_int(casing_reserved),
        }

    def _calculate_capacity(self) -> None:
        d = self.data
        mold_total = mold_prod = mold_break = mold_master_reserved = 0
        for row in d["molds"]:
            if not _is_active(row.get("status"), row.get("is_active")):
                continue
            total = max(
                _to_int(row.get("mold_count")),
                _to_int(row.get("production_mold_count"))
                + _to_int(row.get("breakdown_mold_count"))
                + _to_int(row.get("planning_reserved_mold_count")),
            )
            mold_total += total
            mold_prod += _to_int(row.get("production_mold_count"))
            mold_break += _to_int(row.get("breakdown_mold_count"))
            mold_master_reserved += _to_int(row.get("planning_reserved_mold_count"))
        mold_before = max(0, mold_total - mold_prod - mold_break - mold_master_reserved)
        mold_now = max(0, mold_before - d["mold_reserved_today"])

        casing_total = casing_prod = casing_break = casing_master_reserved = casing_master_available = 0
        for row in d["casings"]:
            if not _is_active(row.get("status"), row.get("is_active")):
                continue
            total = max(
                _to_int(row.get("total_casing_count")),
                _to_int(row.get("casing_count")),
                _to_int(row.get("production_casing_count"))
                + _to_int(row.get("breakdown_casing_count"))
                + _to_int(row.get("planning_reserved_casing_count")),
            )
            casing_total += total
            casing_prod += _to_int(row.get("production_casing_count"))
            casing_break += _to_int(row.get("breakdown_casing_count"))
            casing_master_reserved += _to_int(row.get("planning_reserved_casing_count"))
            casing_master_available += _to_int(row.get("available_casing_count"))
        if d["casing_required"]:
            casing_before = casing_master_available or max(0, casing_total - casing_prod - casing_break - casing_master_reserved)
            casing_now = max(0, casing_before - d["casing_reserved_today"])
        else:
            casing_before = casing_now = None

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in d["cavities"]:
            groups[str(row.get("line_name") or "-")].append(row)

        cavity_registered_total = len(
            d["cavities"]
        )
        cavity_total = cavity_free = cavity_now = cavity_break = 0
        compatible_line_total = 0
        available_line_total = 0

        for line_name, rows in groups.items():
            active = [
                row
                for row in rows
                if _is_active(
                    row.get("status"),
                    row.get("is_active"),
                )
            ]
            free = [
                row
                for row in active
                if not str(
                    row.get(
                        "assigned_tyre_item"
                    )
                    or ""
                ).strip()
            ]

            if active:
                compatible_line_total += 1

            reservation_qty = d[
                "line_reservations"
            ].get(
                _norm(line_name),
                0,
            )
            free_after_reservations = max(
                0,
                len(free) - reservation_qty,
            )

            if free_after_reservations > 0:
                available_line_total += 1

            cavity_total += len(active)
            cavity_free += len(free)
            cavity_break += (
                len(rows) - len(active)
            )
            cavity_now += (
                free_after_reservations
            )

        candidates = {
            "MOLD": mold_now,
            "CAVITY": cavity_now,
        }
        # NO-CASING PLANNING INVARIANT:
        # Casing is added to MIN(...) only when the SMDS item
        # genuinely requires a casing.
        if d["casing_required"]:
            candidates["CASING"] = _to_int(
                casing_now
            )
        simultaneous = min(candidates.values()) if candidates else 0
        total_plan = max(0.0, _to_float(self.smds.get("total_plan")))
        normal_curing_minutes = max(
            0.0,
            _to_float(
                self.smds.get("normal_curing_minutes")
            ),
        )
        handling_present = (
            self.smds.get("handling_time") is not None
        )
        process_standard_missing = (
            total_plan <= 0
            or normal_curing_minutes <= 0
            or not handling_present
        )
        daily = int(simultaneous * total_plan)
        bottlenecks = (
            ["PROCESS STANDARD"]
            if process_standard_missing
            else [
                name
                for name, value in candidates.items()
                if value == simultaneous
            ]
        )
        physical_candidates = {
            "MOLD": mold_before,
            "CAVITY": cavity_free,
        }
        if d["casing_required"]:
            physical_candidates["CASING"] = _to_int(
                casing_before
            )
        # For no-casing items, physical capacity is therefore
        # MIN(MOLD, CAVITY); casing can never reduce it to zero.
        physical_capacity = min(physical_candidates.values()) if physical_candidates else 0

        item_reservations_today: dict[str, int] = defaultdict(int)
        for reservation in d["reservations"]:
            if reservation.get("reservation_date") != d["today"]:
                continue
            item_reservations_today[_norm(reservation.get("resource_type"))] += _to_int(reservation.get("reserved_qty"))

        active_plan_rows = [
            row
            for row in d["plans"]
            if row.get("plan_date") == d["today"]
            and _norm(
                row.get("allocation_status")
            ) not in {
                "blocked",
                "breakdown",
            }
        ]

        active_plan_cavities = {
            _to_int(row.get("cavity_id"))
            for row in active_plan_rows
            if _to_int(
                row.get("cavity_id")
            ) > 0
        }
        active_plan_lines = {
            _norm(row.get("line_name"))
            for row in active_plan_rows
            if _norm(row.get("line_name"))
        }

        item_line_reservation_keys = {
            _norm(
                reservation.get(
                    "resource_key"
                )
            )
            for reservation in d["reservations"]
            if reservation.get(
                "reservation_date"
            ) == d["today"]
            and _norm(
                reservation.get(
                    "resource_type"
                )
            ) == "line_cavity"
            and _to_int(
                reservation.get(
                    "reserved_qty"
                )
            ) > 0
            and _norm(
                reservation.get(
                    "resource_key"
                )
            )
        }

        assigned_line_count = min(
            compatible_line_total,
            len(
                active_plan_lines
                | item_line_reservation_keys
            ),
        )

        assigned_cavity_count = min(
            cavity_total,
            max(
                len(active_plan_cavities),
                item_reservations_today.get(
                    "line_cavity",
                    0,
                ),
            ),
        )
        assigned_mold_count = min(
            mold_total,
            max(
                item_reservations_today.get(
                    "mold",
                    0,
                ),
                len(active_plan_cavities),
            ),
        )
        assigned_casing_count = (
            min(
                casing_total,
                max(
                    item_reservations_today.get(
                        "casing",
                        0,
                    ),
                    len(active_plan_cavities),
                ),
            )
            if d["casing_required"]
            else 0
        )

        committed_candidates = [
            value
            for key, value
            in item_reservations_today.items()
            if key in {
                "mold",
                "casing",
                "line_cavity",
            }
            and value > 0
        ]
        committed_capacity = len(
            active_plan_cavities
        )
        if committed_candidates:
            committed_capacity = max(
                committed_capacity,
                min(committed_candidates),
            )
        committed_capacity = min(
            physical_capacity,
            committed_capacity,
        )
        maximum_item_capacity_now = min(
            physical_capacity,
            committed_capacity + simultaneous,
        )
        daily_max = int(physical_capacity * total_plan)
        daily_free = int(simultaneous * total_plan)

        d.update({
            "mold_total": mold_total,
            "mold_prod": mold_prod,
            "mold_break": mold_break,
            "mold_master_reserved": mold_master_reserved,
            "mold_before": mold_before,
            "mold_now": mold_now,
            "mold_assigned_item": assigned_mold_count,
            "casing_total": casing_total,
            "casing_prod": casing_prod,
            "casing_break": casing_break,
            "casing_master_reserved": casing_master_reserved,
            "casing_before": casing_before,
            "casing_now": casing_now,
            "casing_assigned_item": assigned_casing_count,
            "cavity_registered_total": cavity_registered_total,
            "cavity_total": cavity_total,
            "cavity_free": cavity_free,
            "cavity_now": cavity_now,
            "cavity_break": cavity_break,
            "cavity_assigned_item": assigned_cavity_count,
            "compatible_line_total": compatible_line_total,
            "available_line_total": available_line_total,
            "assigned_line_count": assigned_line_count,
            "simultaneous": simultaneous,
            "physical_capacity": physical_capacity,
            "committed_capacity": committed_capacity,
            "maximum_item_capacity_now": maximum_item_capacity_now,
            "daily_max": daily_max,
            "daily_free": daily_free,
            "total_plan": total_plan,
            "daily": daily,
            "process_standard_missing": process_standard_missing,
            "bottlenecks": bottlenecks,
            "item_reservations_today": dict(item_reservations_today),
        })
        self._calculate_lifecycle()

    @staticmethod
    def _plan_datetime(plan_date: Any, minutes: Any) -> datetime | None:
        if plan_date is None:
            return None
        try:
            # Cavity-plan minute 0 is the factory day start at 07:00.
            return datetime.combine(plan_date, time(hour=7)) + timedelta(minutes=_to_int(minutes))
        except Exception:
            return None

    @staticmethod
    def _fmt_datetime(value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value else "-"

    def _calculate_lifecycle(self) -> None:
        d = self.data
        now = datetime.now()
        shipments = d.get("shipments", [])
        plans = d.get("plans", [])
        events = d.get("events", [])
        self.events = events

        active_hold = next((
            event
            for event in events
            if _norm(event.get("event_type")) == "hold"
            and _norm(event.get("event_status")) == "active"
            and event.get("ended_at") is None
        ), None)

        closed_statuses = {
            "completed",
            "delivered",
            "cancelled",
            "canceled",
            "closed",
            "deleted",
        }
        active_shipments = [
            row
            for row in shipments
            if _norm(row.get("shipment_status"))
            not in closed_statuses
        ]

        total_qty = sum(
            _to_int(row.get("quantity"))
            for row in active_shipments
        )
        stock_allocated = sum(
            _to_int(row.get("stock_allocated_qty"))
            for row in active_shipments
        )
        production_required = sum(
            _to_int(row.get("production_required_qty"))
            for row in active_shipments
        )
        produced = sum(
            _to_int(row.get("produced_qty"))
            for row in active_shipments
        )
        completed = sum(
            _to_int(row.get("completed_qty"))
            for row in active_shipments
        )
        remaining = sum(
            max(0, _to_int(row.get("remaining_qty")))
            for row in active_shipments
        )

        stock_item = d.get("stock_item") or {}
        physical_stock = max(
            0,
            _to_int(
                stock_item.get(
                    "physical_available_stock"
                )
            ),
        )
        unallocated_stock = max(
            0,
            physical_stock - stock_allocated,
        )
        fulfilled_qty = min(
            total_qty,
            stock_allocated + completed,
        )
        progress = (
            fulfilled_qty / total_qty * 100.0
            if total_qty > 0
            else 0.0
        )

        plan_windows: list[tuple[datetime, datetime, dict[str, Any]]] = []
        for row in plans:
            start = self._plan_datetime(row.get("plan_date"), row.get("start_minute"))
            finish = self._plan_datetime(row.get("plan_date"), row.get("end_minute"))
            if start and finish:
                plan_windows.append((start, finish, row))
        plan_windows.sort(key=lambda item: (item[0], item[1]))

        active_windows = [item for item in plan_windows if item[0] <= now < item[1] and _norm(item[2].get("allocation_status")) not in {"blocked", "breakdown"}]
        future_windows = [item for item in plan_windows if item[0] > now and _norm(item[2].get("allocation_status")) not in {"blocked", "breakdown"}]
        blocked_windows = [item for item in plan_windows if _norm(item[2].get("allocation_status")) in {"blocked", "breakdown", "hold"}]

        next_start = future_windows[0][0] if future_windows else (active_windows[0][0] if active_windows else None)
        expected_finish = max((item[1] for item in plan_windows), default=None)

        if active_hold:
            status = "PRODUCTION HOLD"
            style = "LifecycleHold"
            summary = str(active_hold.get("reason") or "An active operational hold blocks this SAP item.")
            next_action = "Resolve the hold reason, then use Release Hold."
        elif active_windows:
            status = "IN PRODUCTION"
            style = "LifecycleRunning"
            row = active_windows[0][2]
            summary = f"Currently planned on {row.get('line_name') or '-'} / cavity {row.get('cavity_no') or '-'} / oven {row.get('oven_no') or '-'} during {row.get('shift_name') or '-'} shift."
            next_action = "Monitor production progress and resource condition."
        elif total_qty > 0 and fulfilled_qty >= total_qty:
            if production_required <= 0 and stock_allocated >= total_qty:
                status = "STOCK ALLOCATED / READY"
                summary = (
                    "All active shipment demand is covered by allocated "
                    "stock; no production is required."
                )
            else:
                status = "SHIPMENT DEMAND FULFILLED"
                summary = (
                    "All active shipment demand is covered by allocated "
                    "stock and completed production."
                )
            style = "LifecycleComplete"
            next_action = (
                "Confirm receive dates and shipment factory-out readiness."
            )
        elif produced > 0 or completed > 0:
            status = "PARTIALLY COMPLETED"
            style = "LifecycleRunning"
            summary = f"Recorded output is {produced:,} produced and {completed:,} completed; {remaining:,} remains open."
            next_action = "Continue the saved production schedule and monitor delays."
        elif future_windows:
            status = "SCHEDULED"
            style = "LifecycleQueued"
            summary = f"The next saved production slot starts at {self._fmt_datetime(next_start)}."
            next_action = (
                "Confirm mold, casing, cavity and oven readiness "
                "before the start."
                if d.get("casing_required")
                else
                "Confirm mold, cavity and oven readiness before "
                "the start. No casing is required for this item."
            )
        elif (
            production_required > 0
            and _norm(
                self.smds.get(
                    "planning_manager_approval_status"
                )
            ) != "approved"
        ):
            status = "MASTER APPROVAL REQUIRED"
            style = "LifecycleBlocked"
            summary = (
                "The item has production demand, but its SMDS planning "
                "approval is not Approved."
            )
            next_action = (
                "Review the process standard in SMDS Master and approve "
                "the item before replanning."
            )
        elif (
            production_required > 0
            and d.get("process_standard_missing")
        ):
            status = "PROCESS STANDARD REQUIRED"
            style = "LifecycleBlocked"
            summary = (
                "Mold, casing and cavity resources may be available, but "
                "curing cycle, handling time or total plan is missing. "
                "Daily output and completion date cannot be calculated."
            )
            next_action = (
                "Repair or approve the SMDS process standard, then run "
                "the cumulative production planner."
            )
        elif blocked_windows or (production_required > 0 and d.get("physical_capacity", 0) <= 0):
            status = "WAITING FOR RESOURCES"
            style = "LifecycleBlocked"
            summary = "Open production demand exists, but no usable physical capacity is currently available."
            bottleneck = " + ".join(d.get("bottlenecks") or ["RESOURCE MAPPING"])
            next_action = f"Release, repair or add the limiting resource: {bottleneck}."
        elif production_required > 0:
            status = "NOT PLANNED"
            style = "LifecycleNeutral"
            summary = "Production demand exists but no future cavity-plan row is saved for this SAP item."
            next_action = "Run the production planner and verify the generated schedule."
        elif stock_allocated > 0:
            status = "AVAILABLE / ALLOCATED STOCK"
            style = "LifecycleComplete"
            summary = (
                f"{stock_allocated:,} units are allocated from stock "
                "and no production is currently required."
            )
            next_action = (
                "Monitor shipment receive and factory-out readiness."
            )
        else:
            status = "NO OPEN DEMAND"
            style = "LifecycleNeutral"
            summary = "No shipment demand is currently recorded for this SAP item."
            next_action = "No production action is required."

        demand_context = (
            f" Active shipment demand: {total_qty:,} pcs; "
            f"current physical stock: {physical_stock:,}; "
            f"stock allocated: {stock_allocated:,}; "
            f"production required: {production_required:,}; "
            f"fulfilled: {fulfilled_qty:,} ({progress:.1f}%)."
        )
        summary = (
            str(summary).rstrip()
            + demand_context
        )

        shipment_schedules: dict[int, dict[str, Any]] = {}
        active_priority = 0
        for shipment in shipments:
            item_id = _to_int(
                shipment.get("shipment_item_id")
            )
            is_active_shipment = (
                _norm(shipment.get("shipment_status"))
                not in closed_statuses
            )
            if is_active_shipment:
                active_priority += 1
                priority = active_priority
            else:
                priority = 0

            item_windows = [
                item
                for item in plan_windows
                if _to_int(
                    item[2].get("shipment_item_id")
                ) == item_id
            ]
            start = min(
                (item[0] for item in item_windows),
                default=None,
            )
            finish = max(
                (item[1] for item in item_windows),
                default=None,
            )
            item_remaining = max(
                0,
                _to_int(
                    shipment.get("remaining_qty")
                ),
            )
            item_qty = _to_int(
                shipment.get("quantity")
            )
            item_stock = _to_int(
                shipment.get("stock_allocated_qty")
            )
            item_completed = _to_int(
                shipment.get("completed_qty")
            )
            item_fulfilled = min(
                item_qty,
                item_stock + item_completed,
            )
            item_progress = (
                item_fulfilled / item_qty * 100.0
                if item_qty > 0
                else 0.0
            )

            if not is_active_shipment:
                item_status = str(
                    shipment.get("shipment_status")
                    or shipment.get("item_status")
                    or "Closed"
                )
            elif item_remaining <= 0 and item_qty > 0:
                item_status = "Completed"
            elif any(
                item[0] <= now < item[1]
                for item in item_windows
            ):
                item_status = "In Production"
            elif start and start > now:
                item_status = "Scheduled"
            elif (
                _to_int(
                    shipment.get("produced_qty")
                ) > 0
                or item_completed > 0
            ):
                item_status = "Partially Completed"
            elif (
                _to_int(
                    shipment.get(
                        "production_required_qty"
                    )
                ) > 0
            ):
                item_status = (
                    "Waiting / Not Planned"
                    if not item_windows
                    else "Queued"
                )
            elif item_stock >= item_qty and item_qty > 0:
                item_status = "Stock Covered"
            else:
                item_status = str(
                    shipment.get("item_status")
                    or "Pending"
                )

            shipment_schedules[item_id] = {
                "priority": priority,
                "start": start,
                "finish": finish,
                "status": item_status,
                "progress": item_progress,
                "fulfilled_qty": item_fulfilled,
            }

        self.lifecycle = {
            "status": status,
            "style": style,
            "summary": summary,
            "next_action": next_action,
            "next_start": next_start,
            "expected_finish": expected_finish,
            "shipment_count": len(active_shipments),
            "total_qty": total_qty,
            "physical_stock": physical_stock,
            "unallocated_stock": unallocated_stock,
            "stock_allocated": stock_allocated,
            "fulfilled_qty": fulfilled_qty,
            "production_required": production_required,
            "produced": produced,
            "completed": completed,
            "remaining": remaining,
            "progress": progress,
            "active_hold": active_hold,
            "active_windows": active_windows,
            "future_windows": future_windows,
            "plan_windows": plan_windows,
            "shipment_schedules": shipment_schedules,
        }

    def _render_lifecycle_status(self) -> None:
        lifecycle = self.lifecycle
        self.lifecycle_status.setText(
            str(lifecycle.get("status") or "UNKNOWN")
        )
        self.lifecycle_status.setObjectName(
            str(
                lifecycle.get("style")
                or "LifecycleNeutral"
            )
        )
        self.lifecycle_status.style().unpolish(
            self.lifecycle_status
        )
        self.lifecycle_status.style().polish(
            self.lifecycle_status
        )
        self.lifecycle_summary.setText(
            str(lifecycle.get("summary") or "-")
        )

        self.status_values["current_stock"].setText(
            f"{_fmt_int(lifecycle.get('physical_stock'))} pcs"
        )
        self.status_values["unallocated_stock"].setText(
            f"{_fmt_int(lifecycle.get('unallocated_stock'))} pcs"
        )
        self.status_values["total_qty"].setText(
            f"{_fmt_int(lifecycle.get('total_qty'))} pcs"
        )
        self.status_values["stock_allocated"].setText(
            f"{_fmt_int(lifecycle.get('stock_allocated'))} pcs"
        )
        self.status_values["production_required"].setText(
            f"{_fmt_int(lifecycle.get('production_required'))} pcs"
        )
        self.status_values["progress"].setText(
            f"{_to_float(lifecycle.get('progress')):.1f}%"
        )
        self.status_values["next_start"].setText(
            self._fmt_datetime(
                lifecycle.get("next_start")
            )
        )
        self.status_values["finish"].setText(
            self._fmt_datetime(
                lifecycle.get("expected_finish")
            )
        )
        self.status_values["next_action"].setText(
            str(lifecycle.get("next_action") or "-")
        )

        self.demand_summary_values["shipments"].setText(
            _fmt_int(
                lifecycle.get("shipment_count")
            )
        )
        self.demand_summary_values["total_qty"].setText(
            _fmt_int(
                lifecycle.get("total_qty")
            )
        )
        self.demand_summary_values["stock_allocated"].setText(
            _fmt_int(
                lifecycle.get("stock_allocated")
            )
        )
        self.demand_summary_values["production_required"].setText(
            _fmt_int(
                lifecycle.get("production_required")
            )
        )
        self.demand_summary_values["progress"].setText(
            f"{_to_float(lifecycle.get('progress')):.1f}%"
        )

        has_hold = (
            lifecycle.get("active_hold")
            is not None
        )
        self.hold_button.setEnabled(
            not has_hold and bool(self.sap_code)
        )
        self.release_hold_button.setEnabled(
            has_hold
        )

    def _render_lifecycle_tables(self) -> None:
        lifecycle = self.lifecycle
        now = datetime.now()
        current_rows: list[list[Any]] = []
        positions = list(lifecycle.get("active_windows") or [])
        positions.extend((lifecycle.get("future_windows") or [])[: max(0, 12 - len(positions))])
        for start, finish, row in positions:
            position = "CURRENT" if start <= now < finish else "NEXT"
            shipment_name = "-"
            shipment_item_id = _to_int(row.get("shipment_item_id"))
            for shipment in self.data.get("shipments", []):
                if _to_int(shipment.get("shipment_item_id")) == shipment_item_id:
                    shipment_name = shipment.get("shipment_name") or shipment.get("shipment_no") or "-"
                    break
            current_rows.append([
                position, _fmt_date(row.get("plan_date")), start.strftime("%H:%M"), finish.strftime("%Y-%m-%d %H:%M"), row.get("shift_name") or "-", row.get("line_name") or "-", _fmt_int(row.get("cavity_no")), row.get("oven_no") or "-", shipment_name, _fmt_int(row.get("today_qty")), row.get("allocation_status") or "-", row.get("risk_reason") or "-",
            ])
        self._set_rows(self.current_production_table, current_rows, {0,1,2,3,4,6,7,9,10}, 10)

        shipment_rows: list[list[Any]] = []
        schedules = lifecycle.get("shipment_schedules") or {}
        for shipment in self.data.get("shipments", []):
            item_id = _to_int(shipment.get("shipment_item_id"))
            schedule = schedules.get(item_id, {})
            priority_value = _to_int(
                schedule.get("priority")
            )
            shipment_rows.append([
                (
                    _fmt_int(priority_value)
                    if priority_value > 0
                    else "-"
                ),
                shipment.get("shipment_name")
                or shipment.get("shipment_no")
                or "-",
                shipment.get("shipment_no") or "-",
                _fmt_date(
                    shipment.get("target_date")
                ),
                _fmt_int(
                    shipment.get("quantity")
                ),
                _fmt_int(
                    shipment.get(
                        "stock_allocated_qty"
                    )
                ),
                _fmt_int(
                    shipment.get(
                        "production_required_qty"
                    )
                ),
                _fmt_int(
                    shipment.get("produced_qty")
                ),
                _fmt_int(
                    shipment.get("completed_qty")
                ),
                _fmt_int(
                    shipment.get("remaining_qty")
                ),
                f"{_to_float(schedule.get('progress')):.1f}%",
                self._fmt_datetime(
                    schedule.get("start")
                ),
                self._fmt_datetime(
                    schedule.get("finish")
                ),
                _fmt_date(
                    shipment.get(
                        "item_receive_date"
                    )
                ),
                schedule.get("status")
                or shipment.get("item_status")
                or "-",
            ])
        self._set_rows(
            self.lifecycle_shipment_table,
            shipment_rows,
            {
                0, 2, 3, 4, 5, 6, 7, 8,
                9, 10, 11, 12, 13, 14,
            },
            14,
        )

    def _render_event_table(self) -> None:
        rows = [[
            str(event.get("started_at") or "-"), str(event.get("ended_at") or "-"), event.get("event_type") or "-", event.get("event_status") or "-", event.get("reason") or "-", _fmt_int(event.get("shipment_item_id")) if event.get("shipment_item_id") else "-", event.get("created_by") or "-", event.get("closed_by") or "-",
        ] for event in self.events]
        self._set_rows(self.event_table, rows, {0,1,2,3,5,6,7}, 3)

    def _render(self) -> None:
        d = self.data
        description = str(self.smds.get("material_description") or "SMDS item not found")
        approval = str(self.smds.get("planning_manager_approval_status") or "Unknown")
        lines = self._line_candidates()
        self.title_label.setText(description)
        self.sap_value.setText(self.sap_code)
        self.description_value.setText(description)
        self.key_code_value.setText(str(self.smds.get("key_code") or "-"))
        raw_casing_type = str(
            self.smds.get("casing_type")
            or ""
        ).strip()
        self.casing_type_value.setText(
            raw_casing_type
            if d["casing_required"]
            else "No Casing Required"
        )
        self.line_value.setText(", ".join(lines) if lines else "Not Mapped")
        self.plan_value.setText(
            f"{_fmt_number(self.smds.get('day_plan'))} / "
            f"{_fmt_number(self.smds.get('night_plan'))} / "
            f"{_fmt_number(self.smds.get('total_plan'))}"
        )
        self.curing_value.setText(str(self.smds.get("curing_cycle") or self.smds.get("normal_curing_time_text") or "-"))
        handling = self.smds.get("handling_time")
        self.handling_value.setText(f"{_fmt_number(handling)} min" if handling is not None else "-")
        weight = self.smds.get("weight_per_tyre_kg")
        self.weight_value.setText(f"{_fmt_number(weight)} kg" if weight is not None else "-")
        lifecycle = self.lifecycle
        self.stock_position_value.setText(
            f"Physical {_fmt_int(lifecycle.get('physical_stock'))}  |  "
            f"Unallocated {_fmt_int(lifecycle.get('unallocated_stock'))}"
        )
        badge = "ApprovedBadge" if _norm(approval) == "approved" else "PendingBadge" if _norm(approval) == "pending" else "NeutralBadge"
        self.approval_badge.setObjectName(badge)
        self.approval_badge.setText(approval.upper())
        self.approval_badge.style().unpolish(self.approval_badge)
        self.approval_badge.style().polish(self.approval_badge)

        resource_values = self.resource_capacity_values

        resource_values["mold"]["total"].setText(
            _fmt_int(d["mold_total"])
        )
        resource_values["mold"]["available"].setText(
            _fmt_int(d["mold_now"])
        )
        resource_values["mold"]["assigned"].setText(
            _fmt_int(
                d["mold_assigned_item"]
            )
        )

        casing_card = self.resource_capacity_cards[
            "casing"
        ]
        casing_title = self.resource_capacity_titles[
            "casing"
        ]
        casing_hint = self.resource_capacity_hints[
            "casing"
        ]
        casing_captions = self.resource_capacity_captions[
            "casing"
        ]

        if d["casing_required"]:
            casing_card.setObjectName(
                "ResourceCapacityCard"
            )
            casing_title.setText(
                "Casing Capacity"
            )
            casing_hint.setText(
                "All matching casing units, free units and units "
                "assigned to this SAP item."
            )
            casing_captions["total"].setText(
                "Total Compatible"
            )
            casing_captions["available"].setText(
                "Available Free"
            )
            casing_captions["assigned"].setText(
                "Assigned This Item"
            )
            resource_values["casing"]["total"].setText(
                _fmt_int(d["casing_total"])
            )
            resource_values["casing"]["available"].setText(
                _fmt_int(d["casing_now"])
            )
            resource_values["casing"]["assigned"].setText(
                _fmt_int(
                    d["casing_assigned_item"]
                )
            )
            self.tabs.setTabText(
                self.tabs.indexOf(
                    self.casing_tab
                ),
                "Casings",
            )
        else:
            casing_card.setObjectName(
                "NoCasingResourceCard"
            )
            casing_title.setText(
                "Casing Requirement"
            )
            casing_hint.setText(
                "This item is manufactured without a casing. "
                "Casing is excluded from capacity, bottleneck "
                "and scheduling calculations."
            )
            casing_captions["total"].setText(
                "Casing Required"
            )
            casing_captions["available"].setText(
                "Capacity Rule"
            )
            casing_captions["assigned"].setText(
                "Planning Impact"
            )
            resource_values["casing"]["total"].setText(
                "NO"
            )
            resource_values["casing"]["available"].setText(
                "EXCLUDED"
            )
            resource_values["casing"]["assigned"].setText(
                "NONE"
            )
            self.tabs.setTabText(
                self.tabs.indexOf(
                    self.casing_tab
                ),
                "Casing — Not Required",
            )

        for label in resource_values[
            "casing"
        ].values():
            label.setObjectName(
                "ResourceValue"
                if d["casing_required"]
                else "NoCasingValue"
            )
            label.style().unpolish(label)
            label.style().polish(label)

        casing_card.style().unpolish(
            casing_card
        )
        casing_card.style().polish(
            casing_card
        )

        resource_values["cavity"]["total"].setText(
            _fmt_int(
                d["cavity_registered_total"]
            )
        )
        resource_values["cavity"]["available"].setText(
            _fmt_int(d["cavity_now"])
        )
        resource_values["cavity"]["assigned"].setText(
            _fmt_int(
                d["cavity_assigned_item"]
            )
        )

        self.metric_labels["physical"].setText(
            _fmt_int(d["physical_capacity"])
        )
        self.metric_labels["committed"].setText(
            _fmt_int(d["committed_capacity"])
        )
        self.metric_labels["free_additional"].setText(
            _fmt_int(d["simultaneous"])
        )
        self.metric_labels["daily_output"].setText(
            f"{_fmt_int(d['daily_max'])} max\n"
            f"{_fmt_int(d['daily_free'])} additional"
        )

        bottleneck_text = " + ".join(
            d["bottlenecks"]
        )
        if d.get("process_standard_missing"):
            self.bottleneck_value.setText(
                "PRODUCTION RATE UNAVAILABLE — PROCESS STANDARD "
                "MISSING (CURING / HANDLING / TOTAL PLAN)"
            )
        else:
            self.bottleneck_value.setText(
                (
                    "NO ADDITIONAL FREE CAPACITY — "
                    if d["simultaneous"] <= 0
                    else "ADDITIONAL CAPACITY LIMITED BY "
                )
                + bottleneck_text
            )

        casing_total_text = (
            _fmt_int(d["casing_total"])
            if d["casing_required"]
            else "NO CASING REQUIRED"
        )
        casing_available_text = (
            _fmt_int(d["casing_now"])
            if d["casing_required"]
            else "EXCLUDED"
        )
        casing_assigned_text = (
            _fmt_int(
                d["casing_assigned_item"]
            )
            if d["casing_required"]
            else "NO IMPACT"
        )

        self.capacity_formula.setText(
            "Resource position — "
            f"Mold: total {_fmt_int(d['mold_total'])}, "
            f"free {_fmt_int(d['mold_now'])}, "
            f"assigned to this item "
            f"{_fmt_int(d['mold_assigned_item'])}; "
            f"Casing: {casing_total_text}, "
            f"capacity rule {casing_available_text}, "
            f"planning impact {casing_assigned_text}; "
            f"Cavities: total "
            f"{_fmt_int(d['cavity_registered_total'])}, "
            f"free {_fmt_int(d['cavity_now'])}, "
            f"assigned "
            f"{_fmt_int(d['cavity_assigned_item'])}. "
            f"Additional capacity = "
            f"{_fmt_int(d['simultaneous'])}; "
            f"maximum daily output = "
            f"{_fmt_int(d['daily_max'])} pcs."
        )
        self._render_lifecycle_status()

        self.overview_values["mold"].setText(
            f"Total: {_fmt_int(d['mold_total'])}\nIn production: {_fmt_int(d['mold_prod'])}\n"
            f"Breakdown: {_fmt_int(d['mold_break'])}\nReserved today: {_fmt_int(d['mold_reserved_today'])}\n"
            f"Available now: {_fmt_int(d['mold_now'])}"
        )
        self.overview_values["casing"].setText(
            f"Total: {_fmt_int(d['casing_total'])}\nIn production: {_fmt_int(d['casing_prod'])}\n"
            f"Breakdown: {_fmt_int(d['casing_break'])}\nReserved today: {_fmt_int(d['casing_reserved_today'])}\n"
            f"Available now: {_fmt_int(d['casing_now'])}"
            if d["casing_required"] else
            "This SAP item does not require casing. Casing is excluded from the capacity formula."
        )
        self.overview_values["cavity"].setText(
            f"Compatible active cavities: {_fmt_int(d['cavity_total'])}\n"
            f"Free before reservations: {_fmt_int(d['cavity_free'])}\n"
            f"Breakdown / inactive: {_fmt_int(d['cavity_break'])}\nAvailable now: {_fmt_int(d['cavity_now'])}"
        )
        active_ovens = sum(1 for row in d["ovens"] if bool(row.get("is_active")))
        used_ovens = {str(row.get("oven_no") or "") for row in d["plans"] if str(row.get("oven_no") or "").strip()}
        self.overview_values["oven"].setText(
            f"Registered ovens: {_fmt_int(len(d['ovens']))}\nActive ovens: {_fmt_int(active_ovens)}\n"
            f"Ovens used by this SAP: {_fmt_int(len(used_ovens))}"
        )
        future_plans = [row for row in d["plans"] if row.get("plan_date") and row.get("plan_date") >= date.today()]
        self.overview_values["plan"].setText(
            f"Future plan rows: {_fmt_int(len(future_plans))}\n"
            f"Planned quantity: {_fmt_int(sum(_to_int(row.get('today_qty')) for row in future_plans))}\n"
            f"Maximum daily output: {_fmt_int(d['daily_max'])}\nAdditional daily output available: {_fmt_int(d['daily_free'])}"
        )
        future_res = [row for row in d["reservations"] if row.get("reservation_date") and row.get("reservation_date") >= date.today()]
        self.overview_values["reservation"].setText(
            f"Future reservation rows: {_fmt_int(len(future_res))}\n"
            f"Reserved resource units: {_fmt_int(sum(_to_int(row.get('reserved_qty')) for row in future_res))}\n"
            "Reservations are controlled by shipment priority and date."
        )
        self._render_tables()
        self._render_lifecycle_tables()
        self._render_event_table()

    def _set_rows(self, table: QTableWidget, rows: list[list[Any]], center: set[int] | None = None, status_column: int | None = None) -> None:
        center = center or set()
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for row_index, values in enumerate(rows):
            table.insertRow(row_index)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip(str(value))
                if column in center:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if status_column == column:
                    normalized = _norm(value)
                    if normalized in {"active", "planned", "available", "free", "yes"}:
                        item.setForeground(QColor("#047857")); item.setBackground(QColor("#dcfce7"))
                    elif normalized in {"breakdown", "blocked", "inactive", "unavailable", "no"}:
                        item.setForeground(QColor("#b91c1c")); item.setBackground(QColor("#fee2e2"))
                table.setItem(row_index, column, item)
        table.setSortingEnabled(True)
        table.resizeRowsToContents()

    def _render_tables(self) -> None:
        d = self.data
        mold_rows = []
        for row in d["molds"]:
            total = max(_to_int(row.get("mold_count")), _to_int(row.get("production_mold_count")) + _to_int(row.get("breakdown_mold_count")) + _to_int(row.get("planning_reserved_mold_count")))
            available = max(0, total - _to_int(row.get("production_mold_count")) - _to_int(row.get("breakdown_mold_count")) - _to_int(row.get("planning_reserved_mold_count")) - d["mold_reserved_today"])
            mold_rows.append([
                row.get("key_code") or row.get("mold_key_code") or "-", row.get("description") or "-", row.get("status") or "-",
                _fmt_int(total), _fmt_int(row.get("production_mold_count")), _fmt_int(row.get("breakdown_mold_count")),
                _fmt_int(row.get("planning_reserved_mold_count")), _fmt_int(d["mold_reserved_today"]), _fmt_int(available), row.get("remarks") or "-",
            ])
        self._set_rows(self.mold_table, mold_rows, {0,2,3,4,5,6,7,8}, 2)

        if not d["casing_required"]:
            casing_rows = [[
                "NO CASING REQUIRED",
                "-",
                "EXCLUDED",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "N/A",
                "NO CAPACITY LIMIT",
                (
                    "This SAP item is manufactured without a casing. "
                    "Casing is excluded from all capacity, bottleneck "
                    "and production-scheduling calculations."
                ),
            ]]
        else:
            casing_rows = []
            for row in d["casings"]:
                total = max(_to_int(row.get("total_casing_count")), _to_int(row.get("casing_count")), _to_int(row.get("production_casing_count")) + _to_int(row.get("breakdown_casing_count")) + _to_int(row.get("planning_reserved_casing_count")))
                base = _to_int(row.get("available_casing_count")) or max(0, total - _to_int(row.get("production_casing_count")) - _to_int(row.get("breakdown_casing_count")) - _to_int(row.get("planning_reserved_casing_count")))
                casing_rows.append([
                    row.get("casing_type") or "-", row.get("casing_code") or "-", row.get("status") or "-", _fmt_int(total),
                    _fmt_int(row.get("production_casing_count")), _fmt_int(row.get("breakdown_casing_count")), _fmt_int(row.get("planning_reserved_casing_count")),
                    _fmt_int(d["casing_reserved_today"]), _fmt_int(max(0, base - d["casing_reserved_today"])), row.get("remarks") or "-",
                ])
        self._set_rows(self.casing_table, casing_rows, {0,1,2,3,4,5,6,7,8}, 2)

        remaining = dict(d["line_reservations"])
        cavity_rows = []
        for row in d["cavities"]:
            line = str(row.get("line_name") or "-")
            key = _norm(line)
            active = _is_active(row.get("status"), row.get("is_active"))
            assigned = str(row.get("assigned_tyre_item") or "").strip()
            free = active and not assigned
            reserved = 1 if free and remaining.get(key, 0) > 0 else 0
            if reserved:
                remaining[key] -= 1
            availability = "Breakdown / Inactive" if not active else "Assigned" if assigned else "Reserved" if reserved else "Available"
            cavity_rows.append([
                line, _fmt_int(row.get("cavity_no")), row.get("cavity_code") or "-", row.get("status") or "-", "Yes" if active else "No",
                assigned or "-", _fmt_int(reserved), row.get("_latest_oven") or "-", "Yes" if row.get("_current_sap_plan") else "No", availability,
            ])
        self._set_rows(self.cavity_table, cavity_rows, {1,2,3,4,6,7,8,9}, 9)

        usage: dict[str, dict[str, Any]] = {}
        for row in d["plans"]:
            oven = str(row.get("oven_no") or "").strip()
            if not oven:
                continue
            entry = usage.setdefault(_norm(oven), {"count": 0, "latest": None, "locations": set()})
            entry["count"] += 1
            plan_date = row.get("plan_date")
            if plan_date and (entry["latest"] is None or plan_date > entry["latest"]):
                entry["latest"] = plan_date
            entry["locations"].add(f"{row.get('line_name') or '-'} / Cavity {row.get('cavity_no') or '-'}")
        oven_rows = []
        for row in d["ovens"]:
            code = str(row.get("oven_code") or "-")
            item = usage.get(_norm(code), {})
            oven_rows.append([
                code, row.get("oven_name") or "-", "Yes" if bool(row.get("is_active")) else "No", _fmt_int(item.get("count")),
                _fmt_date(item.get("latest")), ", ".join(sorted(item.get("locations") or [])) or "-",
            ])
        self._set_rows(self.oven_table, oven_rows, {0,2,3,4}, 2)

        shipment_rows = []
        schedules = self.lifecycle.get(
            "shipment_schedules"
        ) or {}
        for row in d["shipments"]:
            schedule = schedules.get(
                _to_int(
                    row.get("shipment_item_id")
                ),
                {},
            )
            shipment_rows.append([
                row.get("shipment_name")
                or row.get("shipment_no")
                or "-",
                row.get("shipment_no") or "-",
                _fmt_int(row.get("quantity")),
                _fmt_int(
                    row.get("stock_allocated_qty")
                ),
                _fmt_int(
                    row.get(
                        "production_required_qty"
                    )
                ),
                _fmt_int(row.get("produced_qty")),
                _fmt_int(row.get("completed_qty")),
                _fmt_int(row.get("remaining_qty")),
                f"{_to_float(schedule.get('progress')):.1f}%",
                schedule.get("status")
                or row.get("item_status")
                or "-",
            ])
        self._set_rows(
            self.shipment_table,
            shipment_rows,
            {1, 2, 3, 4, 5, 6, 7, 8, 9},
            9,
        )

        plan_rows = [[
            _fmt_date(row.get("plan_date")), row.get("shift_name") or "-", row.get("line_name") or "-", _fmt_int(row.get("cavity_no")),
            row.get("oven_no") or "-", _fmt_int(row.get("today_qty")), row.get("mold_type") or "-", row.get("casing_type") or "-",
            row.get("allocation_status") or "-", row.get("risk_reason") or "-",
        ] for row in d["plans"]]
        self._set_rows(self.plan_table, plan_rows, {0,1,3,4,5,8}, 8)

        reservation_rows = [[
            _fmt_date(row.get("reservation_date")), row.get("resource_type") or "-", row.get("resource_key") or "-", _fmt_int(row.get("reserved_qty")),
            _fmt_int(row.get("capacity_qty")), row.get("shipment_name") or row.get("shipment_no") or "-", row.get("shipment_no") or "-", row.get("note") or "-",
        ] for row in d["reservations"]]
        self._set_rows(self.reservation_table, reservation_rows, {0,1,3,4,6})

    def _ensure_operational_schema(self) -> None:
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS item_operational_events (
                    id BIGSERIAL PRIMARY KEY,
                    sap_code VARCHAR(128) NOT NULL,
                    shipment_item_id INTEGER NULL,
                    event_type VARCHAR(40) NOT NULL,
                    event_status VARCHAR(30) NOT NULL DEFAULT 'Active',
                    reason TEXT NOT NULL DEFAULT '',
                    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP NULL,
                    created_by TEXT NOT NULL DEFAULT 'system',
                    closed_by TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            connection.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_item_operational_events_sap_status
                ON item_operational_events (sap_code, event_status, started_at DESC)
            """))

    def _current_user_name(self) -> str:
        return str(getattr(self.current_user, "username", None) or "anonymous")

    def _place_hold(self) -> None:
        if not self.sap_code:
            return
        reason, accepted = QInputDialog.getMultiLineText(self, "Place Production Hold", "Enter the exact hold reason and required action:")
        reason = reason.strip()
        if not accepted:
            return
        if not reason:
            QMessageBox.warning(self, "Hold Reason Required", "A clear hold reason is required for the audit history.")
            return
        with engine.begin() as connection:
            active = connection.execute(text("""
                SELECT id FROM item_operational_events
                WHERE TRIM(sap_code) = TRIM(:sap_code)
                  AND event_type = 'HOLD'
                  AND event_status = 'Active'
                  AND ended_at IS NULL
                LIMIT 1
            """), {"sap_code": self.sap_code}).scalar()
            if active:
                QMessageBox.information(self, "Hold Already Active", "This item already has an active production hold.")
                return
            connection.execute(text("""
                INSERT INTO item_operational_events (
                    sap_code, shipment_item_id, event_type, event_status,
                    reason, created_by
                ) VALUES (
                    :sap_code, :shipment_item_id, 'HOLD', 'Active',
                    :reason, :created_by
                )
            """), {"sap_code": self.sap_code, "shipment_item_id": self.shipment_item_id, "reason": reason, "created_by": self._current_user_name()})
        self.refresh_data()

    def _release_hold(self) -> None:
        active_hold = self.lifecycle.get("active_hold")
        if not active_hold:
            return
        note, accepted = QInputDialog.getMultiLineText(self, "Release Production Hold", "Resolution / release note:")
        note = note.strip()
        if not accepted:
            return
        with engine.begin() as connection:
            connection.execute(text("""
                UPDATE item_operational_events
                SET event_status = 'Released', ended_at = CURRENT_TIMESTAMP,
                    closed_by = :closed_by,
                    reason = CASE WHEN TRIM(:note) = '' THEN reason
                                  ELSE reason || E'\\nRelease: ' || :note END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :event_id
            """), {"event_id": int(active_hold["id"]), "closed_by": self._current_user_name(), "note": note})
        self.refresh_data()

    def _add_note(self) -> None:
        if not self.sap_code:
            return
        note, accepted = QInputDialog.getMultiLineText(self, "Add Operational Note", "Operational note:")
        note = note.strip()
        if not accepted or not note:
            return
        with engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO item_operational_events (
                    sap_code, shipment_item_id, event_type, event_status,
                    reason, started_at, ended_at, created_by, closed_by
                ) VALUES (
                    :sap_code, :shipment_item_id, 'NOTE', 'Closed',
                    :reason, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    :created_by, :created_by
                )
            """), {"sap_code": self.sap_code, "shipment_item_id": self.shipment_item_id, "reason": note, "created_by": self._current_user_name()})
        self.refresh_data()

    def _setup_auto_refresh(self) -> None:
        self.live_refresh_timer = QTimer(self)
        self.live_refresh_timer.setInterval(10000)
        self.live_refresh_timer.timeout.connect(self._safe_auto_refresh)
        self.live_refresh_timer.start()

    def _safe_auto_refresh(self) -> None:
        if self.isVisible() and self.sap_code:
            self.refresh_data()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "live_refresh_timer"):
            self.live_refresh_timer.start()
        if self.sap_code:
            QTimer.singleShot(0, self.refresh_data)

    def hideEvent(self, event) -> None:
        if hasattr(self, "live_refresh_timer"):
            self.live_refresh_timer.stop()
        super().hideEvent(event)

    def _go_back(self) -> None:
        if callable(self.on_back):
            self.on_back()

    def _open_master(self, target: str) -> None:
        if callable(self.on_open_master):
            self.on_open_master(target)
        else:
            QMessageBox.information(self, "Resource Management", "The requested master-data module is unavailable.")
