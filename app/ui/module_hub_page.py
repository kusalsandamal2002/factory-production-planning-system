from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class ModuleCard:
    title: str
    description: str
    button_text: str = "Open"
    action_key: str | None = None


class ModuleHubPage(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str,
        cards: list[ModuleCard],
        open_callback=None,
    ):
        super().__init__()

        self.title_text = title
        self.subtitle_text = subtitle
        self.cards = cards
        self.open_callback = open_callback

        self._apply_styles()
        self._build_ui()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#HeaderCard,
            QFrame#ModuleCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle {
                color: #64748b;
                font-size: 10pt;
                font-weight: 650;
            }

            QLabel#CardTitle {
                color: #0f172a;
                font-size: 13pt;
                font-weight: 950;
            }

            QLabel#CardDescription {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 600;
                line-height: 140%;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-size: 9.5pt;
                font-weight: 950;
                min-height: 26px;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-size: 9.5pt;
                font-weight: 950;
                min-height: 26px;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        root.addWidget(self._build_header())
        root.addLayout(self._build_cards_grid())
        root.addStretch()

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(6)

        title = QLabel(self.title_text)
        title.setObjectName("PageTitle")

        subtitle = QLabel(self.subtitle_text)
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        return card

    def _build_cards_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        for index, card_data in enumerate(self.cards):
            grid.addWidget(
                self._build_module_card(card_data),
                index // 3,
                index % 3,
            )

        return grid

    def _build_module_card(self, card_data: ModuleCard) -> QFrame:
        card = QFrame()
        card.setObjectName("ModuleCard")
        card.setMinimumHeight(170)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel(card_data.title)
        title.setObjectName("CardTitle")
        title.setWordWrap(True)

        description = QLabel(card_data.description)
        description.setObjectName("CardDescription")
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignTop)

        button_row = QHBoxLayout()
        button_row.addStretch()

        button = QPushButton(card_data.button_text)
        button.setObjectName("PrimaryButton")

        if not card_data.action_key:
            button.setObjectName("SecondaryButton")
            button.setText("Coming Soon")
            button.setEnabled(False)
        else:
            button.clicked.connect(
                lambda checked=False, key=card_data.action_key: self._open_action(key)
            )

        button_row.addWidget(button)

        layout.addWidget(title)
        layout.addWidget(description, 1)
        layout.addLayout(button_row)

        return card

    def _open_action(self, action_key: str) -> None:
        if self.open_callback:
            self.open_callback(action_key)


def create_factory_data_center_page(open_callback=None) -> ModuleHubPage:
    return ModuleHubPage(
        title="Factory Data Center",
        subtitle=(
            "Admin and manager control area for maintaining the factory master data "
            "that replaces Excel input sheets."
        ),
        cards=[
            ModuleCard(
                title="Product Master",
                description="Manage material codes, descriptions, product groups, weights, bead and band links.",
                action_key="product_master",
            ),
            ModuleCard(
                title="Stock Master",
                description="Manage FG, QC, scrap, blocked and available stock balances.",
                action_key="stock_master",
            ),
            ModuleCard(
                title="BOM Master",
                description="Manage finished item to raw material usage and wastage percentages.",
                action_key="bom_master",
            ),
            ModuleCard(
                title="Compound Master",
                description="Manage compound codes, compound stages and weight per unit.",
                action_key="compound_master",
            ),
            ModuleCard(
                title="Bead Master",
                description="Manage bead type and bead consumption per tyre or size.",
                action_key="bead_master",
            ),
            ModuleCard(
                title="Band Master",
                description="Manage band code, band type and band usage per tyre.",
                action_key="band_master",
            ),
            ModuleCard(
                title="Capacity Master",
                description="Manage running moulds, per mould capacity and available daily capacity.",
                action_key="capacity_master",
            ),
            ModuleCard(
                title="Oven Master",
                description="Manage oven codes, oven names and active/inactive machine status.",
                action_key="oven_master",
            ),
        ],
        open_callback=open_callback,
    )


def create_manager_output_page(open_callback=None) -> ModuleHubPage:
    return ModuleHubPage(
        title="Manager Output Center",
        subtitle=(
            "Decision pages for production, shipment, material, capacity and risk analysis."
        ),
        cards=[
            ModuleCard(
                title="Stock Planning Result",
                description="View ready items, shortage items, production required quantity and total tons.",
                action_key="stock_planning",
            ),
            ModuleCard(
                title="Material Requirement",
                description="View BOM, compound, bead and band requirement from production demand.",
                action_key="material_requirement",
            ),
            ModuleCard(
                title="Capacity Analysis",
                description="Compare production requirement with mould and oven capacity.",
                action_key="capacity_analysis",
            ),
            ModuleCard(
                title="Shipment Risk",
                description="View cannot-complete items, delay risk and shortage reasons.",
                action_key="shipment_risk",
            ),
            ModuleCard(
                title="Data Quality Warnings",
                description="Review missing weight, BOM, compound and capacity data issues.",
                action_key="data_quality",
            ),
        ],
        open_callback=open_callback,
    )


def create_admin_control_page(open_callback=None) -> ModuleHubPage:
    return ModuleHubPage(
        title="Admin Control Center",
        subtitle=(
            "System administration area for data audit, raw Excel traceability, users, backup and restore."
        ),
        cards=[
            ModuleCard(
                title="Data Quality Issues",
                description="Review and resolve data warnings found during Excel-to-database mapping.",
                action_key="data_quality",
            ),
            ModuleCard(
                title="Raw Excel Data Viewer",
                description="Trace any app value back to workbook, sheet, row and cell.",
                action_key="raw_excel_viewer",
            ),
            ModuleCard(
                title="Users & Roles",
                description="Manage admin, manager, operator and viewer access levels.",
                action_key="users_roles",
            ),
            ModuleCard(
                title="Backup / Restore",
                description="Backup PostgreSQL data and restore previous safe snapshots.",
                action_key="backup_restore",
            ),
            ModuleCard(
                title="Audit Log",
                description="Track who changed master data, stock, demand and schedule records.",
                action_key="audit_log",
            ),
        ],
        open_callback=open_callback,
    )