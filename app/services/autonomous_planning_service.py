from __future__ import annotations

from typing import Any

from app.services.planning_authority_service import PlanningAuthorityService


class AutonomousPlanningService:
    """Stable R6 facade for deterministic planning + advisory intelligence.

    Operational facts are read from PlanningAuthorityService. ML readiness is
    exposed separately so unvalidated predictions can never silently replace
    stock, demand, capacity or saved-plan facts.
    """

    @classmethod
    def operational_snapshot(cls, *, persist: bool = False) -> dict[str, Any]:
        payload = PlanningAuthorityService.load(persist_priority=True)
        if persist:
            snapshot_id = PlanningAuthorityService.persist_snapshot(payload)
            payload = dict(payload)
            payload["snapshot_id"] = snapshot_id
        return payload

    @classmethod
    def model_snapshot(cls) -> dict[str, Any]:
        from app.services.ml_platform_service import MLPlatformService

        return MLPlatformService.snapshot()

    @classmethod
    def shipment_explanation(cls, shipment_id: int) -> dict[str, Any]:
        payload = cls.operational_snapshot(persist=False)
        shipment_id = int(shipment_id)
        shipment = next(
            (
                row
                for row in payload.get("shipments") or []
                if int(row.get("shipment_id") or 0) == shipment_id
            ),
            None,
        )
        if shipment is None:
            return {
                "shipment_id": shipment_id,
                "found": False,
                "explanation": "Shipment is not in the active planning queue.",
            }

        priority = shipment.get("priority_no")
        gap = int(shipment.get("production_gap_qty") or 0)
        target = shipment.get("target_date")
        can_out = shipment.get("factory_can_out_date")
        stock = int(shipment.get("stock_covered_qty") or 0)
        demand = int(shipment.get("quantity") or 0)

        reasons = [
            f"Priority #{priority}" if priority is not None else "No active priority",
            f"Demand {demand:,}",
            f"Stock covered {stock:,}",
            f"Production gap {gap:,}",
        ]
        if target:
            reasons.append(f"Target {target}")
        if can_out:
            reasons.append(f"Factory Can Out {can_out}")

        return {
            "shipment_id": shipment_id,
            "found": True,
            "priority_no": priority,
            "demand_qty": demand,
            "stock_covered_qty": stock,
            "production_gap_qty": gap,
            "target_date": target,
            "factory_can_out_date": can_out,
            "explanation": " • ".join(reasons),
        }
