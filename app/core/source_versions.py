from __future__ import annotations

from collections import defaultdict
from threading import Lock


class SourceVersions:
    _instance: "SourceVersions | None" = None

    def __init__(self) -> None:
        self._lock = Lock()
        self._versions = defaultdict(int)

    @classmethod
    def instance(cls) -> "SourceVersions":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, key: str) -> int:
        with self._lock:
            return int(self._versions[str(key)])

    def bump(self, *keys: str) -> dict[str, int]:
        result: dict[str, int] = {}
        with self._lock:
            for raw in keys:
                key = str(raw)
                self._versions[key] += 1
                result[key] = int(self._versions[key])
        return result

    def snapshot(self, *keys: str) -> tuple[int, ...]:
        with self._lock:
            return tuple(int(self._versions[str(key)]) for key in keys)
