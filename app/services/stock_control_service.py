from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def calculate_available_stock(fg: Any, qc: Any, scrap: Any, blocked: Any) -> int:
    """Return usable finished stock without double-subtracting separate buckets.

    FG and QC are usable/current stock buckets. Scrap and Blocked are separate
    physical classifications and are shown independently; they are not deducted
    again from FG/QC because that creates artificial negative stock.
    """
    return max(0, int(fg or 0)) + max(0, int(qc or 0))


def stock_status_from_available(available: int) -> str:
    if available <= 0:
        return "OUT OF STOCK"
    return "AVAILABLE"


@dataclass(frozen=True)
class StockMetrics:
    total_items: int = 0
    fg_qty: int = 0
    qc_qty: int = 0
    available_qty: int = 0
    out_of_stock_items: int = 0
    blocked_qty: int = 0
