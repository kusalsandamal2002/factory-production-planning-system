from __future__ import annotations

from app.ui.order_entry_page import ShipmentDemandPage


class ShipmentDetailsPage(ShipmentDemandPage):
    def __init__(self, current_user=None):
        super().__init__(
            current_user,
            title="Shipment Demand Management",
            subtitle=(
                "Review the current MPPS shipment-demand register used by stock, "
                "production requirement, quantity capacity, and shipment-risk pages."
            ),
        )
