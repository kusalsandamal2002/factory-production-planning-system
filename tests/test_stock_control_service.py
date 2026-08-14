import unittest

from app.services.stock_control_service import (
    StockMetrics,
    calculate_available_stock,
    stock_status_from_available,
)


class StockControlServiceTest(unittest.TestCase):
    def test_available_stock_rule(self):
        self.assertEqual(calculate_available_stock(100, 20, 5, 10), 120)
        self.assertEqual(calculate_available_stock(0, 0, 0, 0), 0)
        self.assertEqual(calculate_available_stock(2, 0, 5, 0), 2)

    def test_stock_status(self):
        self.assertEqual(stock_status_from_available(10), "AVAILABLE")
        self.assertEqual(stock_status_from_available(0), "OUT OF STOCK")
        self.assertEqual(stock_status_from_available(-1), "OUT OF STOCK")

    def test_metrics_defaults(self):
        metrics = StockMetrics()
        self.assertEqual(metrics.total_items, 0)
        self.assertEqual(metrics.available_qty, 0)


if __name__ == "__main__":
    unittest.main()
