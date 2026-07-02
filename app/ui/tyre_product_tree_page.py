from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TyreProductTreePage(QWidget):
    def __init__(self):
        super().__init__()

        self.setStyleSheet(
            """
            QFrame#HeaderCard, QFrame#PanelCard, QFrame#RuleCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 24pt;
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
                font-weight: 900;
            }

            QLabel#CardValue {
                color: #020617;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#CardHint, QLabel#RuleText {
                color: #64748b;
                font-size: 9pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QTreeWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
                padding: 10px;
                color: #0f172a;
                font-size: 10pt;
                font-weight: 650;
            }

            QTreeWidget::item {
                padding: 7px 4px;
            }

            QTreeWidget::item:selected {
                background: #dbeafe;
                color: #1e3a8a;
                border-radius: 8px;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 9px;
                font-size: 9pt;
                font-weight: 900;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addLayout(self._build_summary_cards())

        content = QHBoxLayout()
        content.setSpacing(16)
        content.addWidget(self._build_tree_panel(), 3)
        content.addWidget(self._build_rules_panel(), 2)

        root.addLayout(content, 1)

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(8)

        title = QLabel("Tyre Product Tree Master")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Master structure for industrial tyre categories, allowed production lines, grades, layers and colour variants."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return card

    def _build_summary_cards(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        cards = [
            ("3", "Tyre Types", "Resilient, Press-On and Cured-On"),
            ("4", "Production Lines", "200T, 400T, 800T and SuperSolid"),
            ("3", "Colour Variants", "NM, Grey and Black"),
            ("2", "Layer Types", "2L and 3L where applicable"),
        ]

        for index, (value, title, hint) in enumerate(cards):
            grid.addWidget(self._summary_card(value, title, hint), 0, index)

        return grid

    def _summary_card(self, value: str, title: str, hint: str) -> QFrame:
        card = QFrame()
        card.setObjectName("PanelCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")

        value_label = QLabel(value)
        value_label.setObjectName("CardValue")

        hint_label = QLabel(hint)
        hint_label.setObjectName("CardHint")
        hint_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(hint_label)
        return card

    def _build_tree_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PanelCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Product Category Tree")
        title.setObjectName("SectionTitle")

        tree = QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderLabels(["Product structure", "Allowed production lines / rule"])
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self._populate_tree(tree)
        tree.expandAll()

        layout.addWidget(title)
        layout.addWidget(tree, 1)
        return panel

    def _populate_tree(self, tree: QTreeWidget) -> None:
        resilient = QTreeWidgetItem(tree, ["Resilient Tyre", "400T / 800T"])

        standard = QTreeWidgetItem(resilient, ["Standard", "Quick / Normal"])
        self._add_quick_normal_2l_3l(standard)

        optima = QTreeWidgetItem(resilient, ["Optima", "2L only"])
        self._add_quick_normal_colour_only(optima)

        ultima = QTreeWidgetItem(resilient, ["Ultima", "3L only"])
        self._add_quick_normal_colour_only(ultima)

        press_on = QTreeWidgetItem(tree, ["Press-On Tyre", "200T / 400T / 800T"])
        for grade in ("Standard", "Ultima"):
            grade_item = QTreeWidgetItem(press_on, [grade, "NM / Grey / Black"])
            self._add_colours(grade_item)

        cured_on = QTreeWidgetItem(tree, ["Cured-On Tyre", "200T / 400T / 800T"])
        self._add_colours(cured_on)

    def _add_quick_normal_2l_3l(self, parent: QTreeWidgetItem) -> None:
        for speed in ("Quick", "Normal"):
            speed_item = QTreeWidgetItem(parent, [speed, "2L / 3L"])
            for layer in ("2L", "3L"):
                layer_item = QTreeWidgetItem(speed_item, [layer, "NM / Grey / Black"])
                self._add_colours(layer_item)

    def _add_quick_normal_colour_only(self, parent: QTreeWidgetItem) -> None:
        for speed in ("Quick", "Normal"):
            speed_item = QTreeWidgetItem(parent, [speed, "NM / Grey / Black"])
            self._add_colours(speed_item)

    def _add_colours(self, parent: QTreeWidgetItem) -> None:
        for colour in ("NM", "Grey", "Black"):
            QTreeWidgetItem(parent, [colour, "Colour / compound variant"])

    def _build_rules_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PanelCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Validation Rules")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        rules = [
            ("Resilient Tyre", "Can be planned only on 400T and 800T lines."),
            ("Standard", "Quick and Normal are allowed. Both 2L and 3L are allowed."),
            ("Optima", "2L only. Quick and Normal are allowed."),
            ("Ultima", "3L only. Quick and Normal are allowed."),
            ("Press-On Tyre", "Can be planned on 200T, 400T and 800T lines."),
            ("Cured-On Tyre", "Can be planned on 200T, 400T and 800T lines."),
            ("Colours", "NM, Grey and Black are valid colour / compound variants."),
        ]

        for heading, body in rules:
            layout.addWidget(self._rule_card(heading, body))

        layout.addStretch()
        return panel

    def _rule_card(self, heading: str, body: str) -> QFrame:
        card = QFrame()
        card.setObjectName("RuleCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        heading_label = QLabel(heading)
        heading_label.setObjectName("CardTitle")

        body_label = QLabel(body)
        body_label.setObjectName("RuleText")
        body_label.setWordWrap(True)

        layout.addWidget(heading_label)
        layout.addWidget(body_label)

        return card
