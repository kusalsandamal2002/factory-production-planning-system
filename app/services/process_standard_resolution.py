from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any, Iterable

from sqlalchemy import text

from app.services.master_data_normalization import (
    identifier_key,
    normalize_casing_type,
    normalize_line_name,
    normalize_mold_key,
    normalize_sap_code,
)


# PROCESS STANDARD PLANNING INTEGRITY V6.5


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", "").strip()
            if not value:
                return default
        return float(value)
    except Exception:
        return default


def process_standard_complete(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    return (
        _to_float(row.get("normal_curing_minutes")) > 0
        and row.get("handling_time") is not None
        and _to_float(row.get("handling_time"), -1.0) >= 0
        and _to_float(row.get("day_plan")) > 0
        and _to_float(row.get("night_plan")) > 0
        and _to_float(row.get("total_plan")) > 0
    )


@dataclass(frozen=True)
class ProcessStandardResolution:
    curing_cycle: str
    normal_curing_minutes: float
    normal_curing_time_text: str
    handling_time: float
    day_plan: float
    night_plan: float
    total_plan: float
    peer_count: int
    group_count: int
    confidence: float
    source: str
    peer_sap_codes: tuple[str, ...]

    def as_smds_values(self) -> dict[str, Any]:
        return {
            "curing_cycle": self.curing_cycle,
            "normal_curing_minutes": self.normal_curing_minutes,
            "normal_curing_time_text": self.normal_curing_time_text,
            "handling_time": self.handling_time,
            "day_plan": self.day_plan,
            "night_plan": self.night_plan,
            "total_plan": self.total_plan,
            "process_standard_source": self.source,
            "process_standard_confidence": self.confidence,
            "process_standard_peer_count": self.peer_count,
        }


def _resource_group(row: dict[str, Any], tier: str) -> tuple[str, ...]:
    key_code = normalize_mold_key(row.get("key_code"), unknown_value="")
    casing_type = normalize_casing_type(
        row.get("casing_type"),
        unknown_value="",
    )
    line_name = normalize_line_name(row.get("line"))
    line_key = identifier_key(line_name)
    line_key = re.sub(
        r"^LINE[\s_-]*",
        "",
        line_key,
    )

    if tier == "exact":
        return (
            identifier_key(key_code),
            identifier_key(casing_type),
            line_key,
        )
    return (
        identifier_key(key_code),
        identifier_key(casing_type),
    )


def _numeric_standard_tuple(row: dict[str, Any]) -> tuple[float, ...]:
    return (
        round(_to_float(row.get("normal_curing_minutes")), 3),
        round(_to_float(row.get("handling_time")), 3),
        round(_to_float(row.get("day_plan")), 3),
        round(_to_float(row.get("night_plan")), 3),
        round(_to_float(row.get("total_plan")), 3),
    )


def _display_cycle(
    peers: list[dict[str, Any]],
    numeric_tuple: tuple[float, ...],
) -> str:
    values = [
        str(
            row.get("curing_cycle")
            or row.get("normal_curing_time_text")
            or ""
        ).strip()
        for row in peers
        if _numeric_standard_tuple(row) == numeric_tuple
    ]
    values = [value for value in values if value and value != "-"]
    if values:
        return Counter(values).most_common(1)[0][0]

    minutes = numeric_tuple[0]
    hours = int(minutes // 60)
    mins = int(round(minutes - hours * 60))
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{int(round(minutes))}m"


def _candidate_resolution(
    peers: list[dict[str, Any]],
    *,
    source: str,
    minimum_mode_peers: int,
    minimum_confidence: float,
) -> ProcessStandardResolution | None:
    if not peers:
        return None

    counts = Counter(
        _numeric_standard_tuple(row)
        for row in peers
    )
    numeric_tuple, mode_count = counts.most_common(1)[0]
    group_count = len(peers)
    confidence = mode_count / group_count

    if (
        mode_count < minimum_mode_peers
        or confidence < minimum_confidence
    ):
        return None

    cycle = _display_cycle(peers, numeric_tuple)
    matching_saps = tuple(
        sorted(
            normalize_sap_code(row.get("sap_code"))
            for row in peers
            if _numeric_standard_tuple(row) == numeric_tuple
        )
    )
    return ProcessStandardResolution(
        curing_cycle=cycle,
        normal_curing_minutes=numeric_tuple[0],
        normal_curing_time_text=cycle,
        handling_time=numeric_tuple[1],
        day_plan=numeric_tuple[2],
        night_plan=numeric_tuple[3],
        total_plan=numeric_tuple[4],
        peer_count=mode_count,
        group_count=group_count,
        confidence=round(confidence, 4),
        source=source,
        peer_sap_codes=matching_saps,
    )


class ProcessStandardIndex:
    """Precomputed peer groups for fast repeated resolution."""

    def __init__(
        self,
        rows: Iterable[dict[str, Any]],
    ) -> None:
        self.rows = [dict(row) for row in rows]
        self.exact_groups: dict[
            tuple[str, ...],
            list[dict[str, Any]],
        ] = {}
        self.key_casing_groups: dict[
            tuple[str, ...],
            list[dict[str, Any]],
        ] = {}

        for row in self.rows:
            if not process_standard_complete(row):
                continue
            self.exact_groups.setdefault(
                _resource_group(row, "exact"),
                [],
            ).append(row)
            self.key_casing_groups.setdefault(
                _resource_group(row, "key_casing"),
                [],
            ).append(row)

    @staticmethod
    def _without_target(
        peers: list[dict[str, Any]],
        target: dict[str, Any],
    ) -> list[dict[str, Any]]:
        target_sap = normalize_sap_code(
            target.get("sap_code")
        )
        return [
            row
            for row in peers
            if normalize_sap_code(
                row.get("sap_code")
            ) != target_sap
        ]

    def resolve(
        self,
        target: dict[str, Any],
    ) -> ProcessStandardResolution | None:
        exact_key = _resource_group(
            target,
            "exact",
        )
        if exact_key[0] and exact_key[2]:
            exact = _candidate_resolution(
                self._without_target(
                    self.exact_groups.get(
                        exact_key,
                        [],
                    ),
                    target,
                ),
                source=(
                    "Exact peer consensus: "
                    "Mold/Key Code + Casing + Line"
                ),
                minimum_mode_peers=2,
                minimum_confidence=0.75,
            )
            if exact:
                return exact

        key_casing_key = _resource_group(
            target,
            "key_casing",
        )
        if key_casing_key[0]:
            return _candidate_resolution(
                self._without_target(
                    self.key_casing_groups.get(
                        key_casing_key,
                        [],
                    ),
                    target,
                ),
                source=(
                    "High-confidence peer consensus: "
                    "Mold/Key Code + Casing"
                ),
                minimum_mode_peers=3,
                minimum_confidence=0.85,
            )
        return None


def build_process_standard_index(
    rows: Iterable[dict[str, Any]],
) -> ProcessStandardIndex:
    return ProcessStandardIndex(rows)


def resolve_process_standard(
    rows: Iterable[dict[str, Any]],
    target: dict[str, Any],
) -> ProcessStandardResolution | None:
    return ProcessStandardIndex(rows).resolve(target)


def load_process_standard_rows(
    conn,
    target: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if target:
        rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    sap_code,
                    material_description,
                    key_code,
                    casing_type,
                    line,
                    curing_cycle,
                    normal_curing_minutes,
                    normal_curing_time_text,
                    handling_time,
                    day_plan,
                    night_plan,
                    total_plan,
                    planning_manager_approval_status,
                    planning_manager_approval_note,
                    planning_manager_approved_at,
                    manager_approval_updated_at
                FROM smds
                WHERE mpps_identifier_key(key_code)
                    = mpps_identifier_key(:key_code)
                  AND mpps_identifier_key(casing_type)
                    = mpps_identifier_key(:casing_type)
                """
            ),
            {
                "key_code": target.get("key_code"),
                "casing_type": target.get("casing_type"),
            },
        ).mappings().all()
    else:
        rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    sap_code,
                    material_description,
                    key_code,
                    casing_type,
                    line,
                    curing_cycle,
                    normal_curing_minutes,
                    normal_curing_time_text,
                    handling_time,
                    day_plan,
                    night_plan,
                    total_plan,
                    planning_manager_approval_status,
                    planning_manager_approval_note,
                    planning_manager_approved_at,
                    manager_approval_updated_at
                FROM smds
                """
            )
        ).mappings().all()
    return [dict(row) for row in rows]


def resolve_process_standard_from_connection(
    conn,
    target: dict[str, Any],
) -> ProcessStandardResolution | None:
    return ProcessStandardIndex(
        load_process_standard_rows(
            conn,
            target,
        )
    ).resolve(target)
