from pathlib import Path


file_path = Path("app/ui/main_window.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/main_window.py not found.")

code = file_path.read_text(encoding="utf-8")


replacements = [
    (
        """from app.ui.compound_master_page import CompoundMasterPage
""",
        """from app.ui.compound_master_page import CompoundMasterPage
from app.ui.bead_master_page import BeadMasterPage
""",
    ),
    (
        """    PRODUCT_MASTER_INDEX = 10
    STOCK_MASTER_INDEX = 11
    BOM_MASTER_INDEX = 12
    COMPOUND_MASTER_INDEX = 13
    PLACEHOLDER_INDEX = 14
""",
        """    PRODUCT_MASTER_INDEX = 10
    STOCK_MASTER_INDEX = 11
    BOM_MASTER_INDEX = 12
    COMPOUND_MASTER_INDEX = 13
    BEAD_MASTER_INDEX = 14
    PLACEHOLDER_INDEX = 15
""",
    ),
    (
        """        self.product_master_page = ProductMasterPage()
        self.stock_master_page = StockMasterPage()
        self.bom_master_page = BomMasterPage()
        self.compound_master_page = CompoundMasterPage()
        self.placeholder_page = PlaceholderPage(
""",
        """        self.product_master_page = ProductMasterPage()
        self.stock_master_page = StockMasterPage()
        self.bom_master_page = BomMasterPage()
        self.compound_master_page = CompoundMasterPage()
        self.bead_master_page = BeadMasterPage()
        self.placeholder_page = PlaceholderPage(
""",
    ),
    (
        """        self.stack.addWidget(self._wrap_scroll(self.product_master_page))
        self.stack.addWidget(self._wrap_scroll(self.stock_master_page))
        self.stack.addWidget(self._wrap_scroll(self.bom_master_page))
        self.stack.addWidget(self._wrap_scroll(self.compound_master_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
        """        self.stack.addWidget(self._wrap_scroll(self.product_master_page))
        self.stack.addWidget(self._wrap_scroll(self.stock_master_page))
        self.stack.addWidget(self._wrap_scroll(self.bom_master_page))
        self.stack.addWidget(self._wrap_scroll(self.compound_master_page))
        self.stack.addWidget(self._wrap_scroll(self.bead_master_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
    ),
    (
        """            self.PRODUCT_MASTER_INDEX: self.product_master_page,
            self.STOCK_MASTER_INDEX: self.stock_master_page,
            self.BOM_MASTER_INDEX: self.bom_master_page,
            self.COMPOUND_MASTER_INDEX: self.compound_master_page,
        }
""",
        """            self.PRODUCT_MASTER_INDEX: self.product_master_page,
            self.STOCK_MASTER_INDEX: self.stock_master_page,
            self.BOM_MASTER_INDEX: self.bom_master_page,
            self.COMPOUND_MASTER_INDEX: self.compound_master_page,
            self.BEAD_MASTER_INDEX: self.bead_master_page,
        }
""",
    ),
    (
        '''            "bead_master": (
                self.PLACEHOLDER_INDEX,
                "Bead Master",
                "Manage bead type and bead consumption per tyre or size.",
            ),
''',
        '''            "bead_master": (
                self.BEAD_MASTER_INDEX,
                None,
                None,
            ),
''',
    ),
    (
        """        if index == self.COMPOUND_MASTER_INDEX:
            self.navigate(self.COMPOUND_MASTER_INDEX)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")
""",
        """        if index == self.COMPOUND_MASTER_INDEX:
            self.navigate(self.COMPOUND_MASTER_INDEX)
            return

        if index == self.BEAD_MASTER_INDEX:
            self.navigate(self.BEAD_MASTER_INDEX)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")
""",
    ),
]


for old, new in replacements:
    if old not in code:
        print("Warning: expected block not found. Maybe already patched:")
        print(old[:120])
    else:
        code = code.replace(old, new)

file_path.write_text(code, encoding="utf-8")

print("Bead Master page connected successfully.")
print("Factory Data Center -> Bead Master -> Open will now load the real Bead Master page.")