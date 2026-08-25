from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class DomainEvent:
    name: str
    payload: dict[str, Any]
    created_at: datetime


class EventBus(QObject):
    event = Signal(object)
    _instance: "EventBus | None" = None

    @classmethod
    def instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def publish(self, name: str, **payload: Any) -> DomainEvent:
        item = DomainEvent(
            name=str(name),
            payload=dict(payload),
            created_at=datetime.now(),
        )
        self.event.emit(item)
        return item
