from pathlib import Path


file_path = Path("app/ui/main_window.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/main_window.py not found.")

code = file_path.read_text(encoding="utf-8")


replacements = [
    (
        """from app.ui.bom_master_page import BomMasterPage
""",
        """from app.ui.bom_master_page import BomMasterPage
from app.ui.compound_master_page import CompoundMasterPage
""",
    ),
    (
        """    PRODUCT_MASTER_INDEX = 10
    STOCK_MASTER_INDEX = 11
    BOM_MASTER_INDEX = 12
    PLACEHOLDER_INDEX = 13
""",
        """    PRODUCT_MASTER_INDEX = 10
    STOCK_MASTER_INDEX = 11
    BOM_MASTER_INDEX = 12
    COMPOUND_MASTER_INDEX = 13
    PLACEHOLDER_INDEX = 14
""",
    ),
    (
        """        self.product_master_page = ProductMasterPage()
        self.stock_master_page = StockMasterPage()
        self.bom_master_page = BomMasterPage()
        self.placeholder_page = PlaceholderPage(
""",
        """        self.product_master_page = ProductMasterPage()
        self.stock_master_page = StockMasterPage()
        self.bom_master_page = BomMasterPage()
        self.compound_master_page = CompoundMasterPage()
        self.placeholder_page = PlaceholderPage(
""",
    ),
    (
        """        self.stack.addWidget(self._wrap_scroll(self.product_master_page))
        self.stack.addWidget(self._wrap_scroll(self.stock_master_page))
        self.stack.addWidget(self._wrap_scroll(self.bom_master_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
        """        self.stack.addWidget(self._wrap_scroll(self.product_master_page))
        self.stack.addWidget(self._wrap_scroll(self.stock_master_page))
        self.stack.addWidget(self._wrap_scroll(self.bom_master_page))
        self.stack.addWidget(self._wrap_scroll(self.compound_master_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
    ),
    (
        """            self.PRODUCT_MASTER_INDEX: self.product_master_page,
            self.STOCK_MASTER_INDEX: self.stock_master_page,
            self.BOM_MASTER_INDEX: self.bom_master_page,
        }
""",
        """            self.PRODUCT_MASTER_INDEX: self.product_master_page,
            self.STOCK_MASTER_INDEX: self.stock_master_page,
            self.BOM_MASTER_INDEX: self.bom_master_page,
            self.COMPOUND_MASTER_INDEX: self.compound_master_page,
        }
""",
    ),
    (
        '''            "compound_master": (
                self.PLACEHOLDER_INDEX,
                "Compound Master",
                "Manage compound codes, compound stages and compound requirement rules.",
            ),
''',
        '''            "compound_master": (
                self.COMPOUND_MASTER_INDEX,
                None,
                None,
            ),
''',
    ),
    (
        """        if index == self.BOM_MASTER_INDEX:
            self.navigate(self.BOM_MASTER_INDEX)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")
""",
        """        if index == self.BOM_MASTER_INDEX:
            self.navigate(self.BOM_MASTER_INDEX)
            return

        if index == self.COMPOUND_MASTER_INDEX:
            self.navigate(self.COMPOUND_MASTER_INDEX)
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

print("Compound Master page connected successfully.")
print("Factory Data Center -> Compound Master -> Open will now load the real Compound Master page.")