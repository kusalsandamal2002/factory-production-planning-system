from pathlib import Path


file_path = Path("app/ui/main_window.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/main_window.py not found.")

code = file_path.read_text(encoding="utf-8")


replacements = [
    (
        """from app.ui.product_master_page import ProductMasterPage
""",
        """from app.ui.product_master_page import ProductMasterPage
from app.ui.stock_master_page import StockMasterPage
""",
    ),
    (
        """    PRODUCT_MASTER_INDEX = 10
    PLACEHOLDER_INDEX = 11
""",
        """    PRODUCT_MASTER_INDEX = 10
    STOCK_MASTER_INDEX = 11
    PLACEHOLDER_INDEX = 12
""",
    ),
    (
        """        self.product_master_page = ProductMasterPage()
        self.placeholder_page = PlaceholderPage(
""",
        """        self.product_master_page = ProductMasterPage()
        self.stock_master_page = StockMasterPage()
        self.placeholder_page = PlaceholderPage(
""",
    ),
    (
        """        self.stack.addWidget(self._wrap_scroll(self.product_master_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
        """        self.stack.addWidget(self._wrap_scroll(self.product_master_page))
        self.stack.addWidget(self._wrap_scroll(self.stock_master_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
    ),
    (
        """            self.PRODUCT_MASTER_INDEX: self.product_master_page,
        }
""",
        """            self.PRODUCT_MASTER_INDEX: self.product_master_page,
            self.STOCK_MASTER_INDEX: self.stock_master_page,
        }
""",
    ),
    (
        '''            "stock_master": (
                self.PLACEHOLDER_INDEX,
                "Stock Master",
                "Manage FG, QC, scrap, blocked and available stock balances.",
            ),
''',
        '''            "stock_master": (
                self.STOCK_MASTER_INDEX,
                None,
                None,
            ),
''',
    ),
    (
        """        if index == self.PRODUCT_MASTER_INDEX:
            self.navigate(self.PRODUCT_MASTER_INDEX)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")
""",
        """        if index == self.PRODUCT_MASTER_INDEX:
            self.navigate(self.PRODUCT_MASTER_INDEX)
            return

        if index == self.STOCK_MASTER_INDEX:
            self.navigate(self.STOCK_MASTER_INDEX)
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

print("Stock Master page connected successfully.")
print("Factory Data Center -> Stock Master -> Open will now load the real Stock Master page.")