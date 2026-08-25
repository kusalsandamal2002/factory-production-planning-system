from __future__ import annotations

from typing import Any

from app.services.planning_authority_service import PlanningAuthorityService


class DashboardSnapshotService:
    """Dashboard adapter over the single R6 canonical planning authority."""

    @classmethod
    def load(cls) -> dict[str, Any]:
        return PlanningAuthorityService.load(persist_priority=True)
