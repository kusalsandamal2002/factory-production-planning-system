from __future__ import annotations

from datetime import date, datetime
from typing import Any


class FactoryCanOutService:
    """Single active MPPS API for Factory Can Out calculations.

    The deterministic FactoryPlanningEngine remains the low-level scheduler.
    Active UI/services call this facade so shipment entry, cumulative replanning,
    saved-plan follow-up and explanations share one implementation. ML forecasts
    never replace the deterministic date; they remain advisory.
    """

    ENGINE_VERSION = "R6-CANOUT-1"

    @staticmethod
    def _engine(*, start_date: date | None = None):
        from app.services.factory_planning_engine import FactoryPlanningEngine

        return FactoryPlanningEngine(start_date=start_date or date.today())

    @classmethod
    def preview_items(
        cls,
        items: list[dict[str, Any]],
        *,
        target_date: date | None = None,
        exclude_shipment_id: int | None = None,
        target_date_is_manual: bool = False,
        draft_created_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        return cls._engine().calculate_cart_items(
            items,
            target_date=target_date,
            exclude_shipment_id=exclude_shipment_id,
            target_date_is_manual=target_date_is_manual,
            draft_created_at=draft_created_at,
        )

    @classmethod
    def replan_open_shipments(
        cls,
        *,
        trigger_reason: str,
        created_by: str = "r6_canonical_can_out",
        start_date: date | None = None,
    ) -> dict[str, Any]:
        run = cls._engine(start_date=start_date).replan_all_open_shipments(
            trigger_reason=trigger_reason,
            created_by=created_by,
        )
        shipments = list(getattr(run, "shipments", []) or [])
        return {
            "engine_version": cls.ENGINE_VERSION,
            "planning_run_id": getattr(run, "planning_run_id", None),
            "planning_version": getattr(run, "planning_version", None),
            "status": getattr(run, "status", ""),
            "message": getattr(run, "message", ""),
            "shipment_count": len(shipments),
            "shipments": shipments,
        }

    @classmethod
    def replan_single_shipment(
        cls,
        shipment_id: int,
        *,
        start_date: date | None = None,
    ) -> Any:
        return cls._engine(start_date=start_date).replan_single_shipment_preview(
            int(shipment_id)
        )
