from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher
import json
import math
import re
from statistics import mean, median
from typing import Any, Iterable

from sqlalchemy import text

from app.services.master_data_normalization import clean_text, normalize_sap_code
from app.services.operational_source_service import OperationalSourceService


# MPPS FACTORY INTELLIGENCE V10
# -----------------------------------------------------------------------------
# Design principles
# 1. The newest committed OVEN workbook is the live operational authority.
# 2. Older workbooks are never ignored: they remain immutable historical/ML data.
# 3. PROD column D ("TOTAL STOCK" / "STOCK") is monthly opening-stock evidence.
# 4. Data mismatches are resolved with deterministic rules + history + confidence;
#    low-confidence matches are reviewed, never silently invented.
# 5. Capacity is learned from verified actual production, not from theoretical
#    constants alone.
# -----------------------------------------------------------------------------


def _code(value: Any) -> str:
    value = normalize_sap_code(value)
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    return value.upper().strip()


def _int(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except Exception:
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _description_key(value: Any) -> str:
    value = clean_text(value).upper()
    value = value.replace('×', 'X')
    value = re.sub(r'(?<=\d)\s*[Xx]\s*(?=\d)', 'X', value)
    value = re.sub(r'[^A-Z0-9]+', ' ', value)
    return ' '.join(value.split())


def _token_similarity(left: str, right: str) -> float:
    a = set(left.split())
    b = set(right.split())
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _description_similarity(left: Any, right: Any) -> float:
    a = _description_key(left)
    b = _description_key(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    token = _token_similarity(a, b)
    return _clamp(0.68 * seq + 0.32 * token, 0.0, 1.0)


def _quantile(values: Iterable[float], q: float, default: float = 0.0) -> float:
    cleaned = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not cleaned:
        return default
    q = _clamp(q, 0.0, 1.0)
    pos = (len(cleaned) - 1) * q
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return cleaned[lower]
    weight = pos - lower
    return cleaned[lower] * (1.0 - weight) + cleaned[upper] * weight


@dataclass(frozen=True)
class IdentityResolution:
    raw_sap_code: str
    canonical_sap_code: str
    raw_description: str
    canonical_description: str
    confidence_score: float
    method: str
    action: str
    explanation: str


class FactoryIntelligenceService:
    """Factory-wide intelligence foundation for MPPS V10.

    The service deliberately separates operational truth from learning truth.
    Latest OVEN data drives the factory; historical OVEN files enrich evidence,
    actual-production history, identity resolution, capacity models and AI.
    """

    MODEL_VERSION = "MPPS-FI-V10"

    @staticmethod
    def ensure_schema(session) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS mpps_opening_stock_evidence (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT,
                plan_date DATE NOT NULL,
                month_key VARCHAR(7) NOT NULL,
                sap_code TEXT NOT NULL,
                item_description TEXT NOT NULL DEFAULT '',
                raw_stock_qty INTEGER NOT NULL DEFAULT 0,
                normalized_opening_qty INTEGER NOT NULL DEFAULT 0,
                scrap_qty INTEGER NOT NULL DEFAULT 0,
                blocked_qty INTEGER NOT NULL DEFAULT 0,
                import_mode VARCHAR(20) NOT NULL DEFAULT 'HISTORICAL',
                source_workbook TEXT NOT NULL DEFAULT '',
                source_sheet TEXT NOT NULL DEFAULT 'PROD',
                source_row INTEGER,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(import_run_id, sap_code)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_opening_stock_evidence_month_sap
            ON mpps_opening_stock_evidence(month_key, sap_code, plan_date DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_identity_aliases (
                id BIGSERIAL PRIMARY KEY,
                alias_type VARCHAR(30) NOT NULL DEFAULT 'DESCRIPTION',
                alias_key TEXT NOT NULL,
                raw_value TEXT NOT NULL DEFAULT '',
                canonical_sap_code TEXT NOT NULL,
                canonical_description TEXT NOT NULL DEFAULT '',
                confidence_score NUMERIC(8,6) NOT NULL DEFAULT 0,
                evidence_count INTEGER NOT NULL DEFAULT 1,
                source VARCHAR(40) NOT NULL DEFAULT 'HISTORICAL',
                is_approved BOOLEAN NOT NULL DEFAULT FALSE,
                last_seen_plan_date DATE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(alias_type, alias_key, canonical_sap_code)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_identity_aliases_lookup
            ON mpps_identity_aliases(alias_type, alias_key, confidence_score DESC, evidence_count DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_identity_resolution_log (
                id BIGSERIAL PRIMARY KEY,
                import_run_id BIGINT,
                plan_date DATE,
                raw_sap_code TEXT NOT NULL DEFAULT '',
                canonical_sap_code TEXT NOT NULL DEFAULT '',
                raw_description TEXT NOT NULL DEFAULT '',
                canonical_description TEXT NOT NULL DEFAULT '',
                confidence_score NUMERIC(8,6) NOT NULL DEFAULT 0,
                resolution_method VARCHAR(50) NOT NULL DEFAULT '',
                action VARCHAR(30) NOT NULL DEFAULT 'REVIEW',
                explanation TEXT NOT NULL DEFAULT '',
                source_workbook TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_identity_resolution_log_run
            ON mpps_identity_resolution_log(import_run_id, action, confidence_score DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_factory_capacity_models (
                id BIGSERIAL PRIMARY KEY,
                model_key TEXT NOT NULL UNIQUE,
                model_level VARCHAR(30) NOT NULL,
                entity_key TEXT NOT NULL,
                sample_days INTEGER NOT NULL DEFAULT 0,
                safe_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                expected_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                stretch_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                recent_capacity_qty NUMERIC(18,5) NOT NULL DEFAULT 0,
                day_share NUMERIC(8,6) NOT NULL DEFAULT 0.5,
                stability_score NUMERIC(8,6) NOT NULL DEFAULT 0,
                trend_score NUMERIC(8,6) NOT NULL DEFAULT 0,
                confidence_score NUMERIC(8,6) NOT NULL DEFAULT 0,
                confidence_band VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                validation_wape_pct NUMERIC(10,4) NOT NULL DEFAULT 100,
                model_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                last_trained_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS ix_mpps_factory_capacity_models_level
            ON mpps_factory_capacity_models(model_level, confidence_score DESC, sample_days DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_planner_policy_models (
                id BIGSERIAL PRIMARY KEY,
                model_key TEXT NOT NULL UNIQUE,
                sap_code TEXT NOT NULL DEFAULT '',
                sample_days INTEGER NOT NULL DEFAULT 0,
                planning_ratio NUMERIC(8,6) NOT NULL DEFAULT 1,
                conservative_ratio NUMERIC(8,6) NOT NULL DEFAULT 1,
                validation_wape_pct NUMERIC(10,4) NOT NULL DEFAULT 100,
                confidence_score NUMERIC(8,6) NOT NULL DEFAULT 0,
                confidence_band VARCHAR(20) NOT NULL DEFAULT 'LEARNING',
                model_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                last_trained_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_factory_daily_capacity (
                production_date DATE PRIMARY KEY,
                day_actual_qty INTEGER NOT NULL DEFAULT 0,
                night_actual_qty INTEGER NOT NULL DEFAULT 0,
                total_actual_qty INTEGER NOT NULL DEFAULT 0,
                active_sap_count INTEGER NOT NULL DEFAULT 0,
                total_plan_qty INTEGER NOT NULL DEFAULT 0,
                achievement_pct NUMERIC(10,4) NOT NULL DEFAULT 0,
                source_workbook TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mpps_factory_intelligence_state (
                id INTEGER PRIMARY KEY,
                model_version TEXT NOT NULL DEFAULT 'MPPS-FI-V10',
                latest_operational_date DATE,
                historical_workbook_count INTEGER NOT NULL DEFAULT 0,
                actual_production_days INTEGER NOT NULL DEFAULT 0,
                capacity_model_count INTEGER NOT NULL DEFAULT 0,
                identity_alias_count INTEGER NOT NULL DEFAULT 0,
                unresolved_identity_count INTEGER NOT NULL DEFAULT 0,
                data_coverage_pct NUMERIC(8,3) NOT NULL DEFAULT 0,
                capacity_confidence_pct NUMERIC(8,3) NOT NULL DEFAULT 0,
                last_trained_at TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            INSERT INTO mpps_factory_intelligence_state (id, model_version)
            VALUES (1, 'MPPS-FI-V10')
            ON CONFLICT (id) DO NOTHING
            """,
            # Extend existing monthly stock tables without breaking older installs.
            "ALTER TABLE monthly_stock_counts ADD COLUMN IF NOT EXISTS source_authority VARCHAR(40) NOT NULL DEFAULT 'MANUAL'",
            "ALTER TABLE monthly_stock_counts ADD COLUMN IF NOT EXISTS source_plan_date DATE",
            "ALTER TABLE monthly_stock_counts ADD COLUMN IF NOT EXISTS source_import_run_id BIGINT",
            "ALTER TABLE monthly_stock_counts ADD COLUMN IF NOT EXISTS source_confidence NUMERIC(8,6) NOT NULL DEFAULT 1",
            "ALTER TABLE monthly_stock_counts ADD COLUMN IF NOT EXISTS evidence_count INTEGER NOT NULL DEFAULT 1",
        ]
        for statement in statements:
            session.execute(text(statement))

    @staticmethod
    def _master_rows(session) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            rows = [
                dict(row)
                for row in session.execute(
                    text(
                        """
                        SELECT TRIM(sap_code) AS sap_code,
                               COALESCE(material_description, '') AS description,
                               COALESCE(weight_per_tyre_kg, 0) AS weight_kg
                        FROM smds
                        WHERE TRIM(COALESCE(sap_code, '')) <> ''
                        """
                    )
                ).mappings().all()
            ]
        except Exception:
            rows = []
        if rows:
            return rows
        try:
            return [
                dict(row)
                for row in session.execute(
                    text(
                        """
                        SELECT TRIM(sap_code) AS sap_code,
                               COALESCE(tyre_description, item_description, '') AS description,
                               0 AS weight_kg
                        FROM mpps_sap_stock_items
                        WHERE TRIM(COALESCE(sap_code, '')) <> ''
                        """
                    )
                ).mappings().all()
            ]
        except Exception:
            return []

    @classmethod
    def resolve_identity(
        cls,
        session,
        *,
        raw_sap_code: Any,
        description: Any,
        master_rows: list[dict[str, Any]] | None = None,
        workbook_consensus: dict[str, tuple[str, int, int]] | None = None,
    ) -> IdentityResolution:
        raw = _code(raw_sap_code)
        raw_desc = clean_text(description)
        desc_key = _description_key(raw_desc)
        master_rows = master_rows if master_rows is not None else cls._master_rows(session)
        by_sap = {_code(row.get('sap_code')): row for row in master_rows if _code(row.get('sap_code'))}

        # 1) exact canonical SAP is always strongest.
        if raw and raw in by_sap:
            row = by_sap[raw]
            return IdentityResolution(
                raw, raw, raw_desc, clean_text(row.get('description') or raw_desc),
                1.0, 'EXACT_SAP', 'KEEP', 'SAP code exists in the canonical tyre master.'
            )

        # 2) previously learned/approved alias.
        if desc_key:
            try:
                alias = session.execute(
                    text(
                        """
                        SELECT canonical_sap_code, canonical_description,
                               confidence_score, evidence_count, is_approved
                        FROM mpps_identity_aliases
                        WHERE alias_type = 'DESCRIPTION' AND alias_key = :alias_key
                        ORDER BY is_approved DESC, confidence_score DESC, evidence_count DESC
                        LIMIT 1
                        """
                    ),
                    {'alias_key': desc_key},
                ).mappings().first()
            except Exception:
                alias = None
            if alias and _code(alias.get('canonical_sap_code')):
                confidence = max(_float(alias.get('confidence_score')), 0.985 if alias.get('is_approved') else 0.94)
                action = 'AUTO_CORRECT' if confidence >= 0.985 else 'REVIEW'
                return IdentityResolution(
                    raw,
                    _code(alias.get('canonical_sap_code')),
                    raw_desc,
                    clean_text(alias.get('canonical_description') or raw_desc),
                    _clamp(confidence, 0.0, 1.0),
                    'LEARNED_ALIAS',
                    action,
                    f"Historical description alias seen {int(alias.get('evidence_count') or 1)} time(s).",
                )

        # 3) within-workbook consensus can recover one-off SAP typos safely.
        if desc_key and workbook_consensus and desc_key in workbook_consensus:
            canonical, count, total = workbook_consensus[desc_key]
            ratio = count / max(1, total)
            if canonical and canonical in by_sap and count >= 2 and ratio >= 0.80:
                confidence = _clamp(0.965 + min(0.03, count * 0.003), 0.0, 0.995)
                return IdentityResolution(
                    raw, canonical, raw_desc,
                    clean_text(by_sap[canonical].get('description') or raw_desc),
                    confidence, 'WORKBOOK_CONSENSUS',
                    'AUTO_CORRECT' if confidence >= 0.985 else 'REVIEW',
                    f"Same normalized description maps to SAP {canonical} in {count}/{total} workbook rows.",
                )

        # 4) exact unique description match.
        if desc_key:
            exact_desc = [
                row for row in master_rows
                if _description_key(row.get('description')) == desc_key
            ]
            unique_codes = {_code(row.get('sap_code')) for row in exact_desc if _code(row.get('sap_code'))}
            if len(unique_codes) == 1:
                canonical = next(iter(unique_codes))
                row = next(row for row in exact_desc if _code(row.get('sap_code')) == canonical)
                return IdentityResolution(
                    raw, canonical, raw_desc, clean_text(row.get('description') or raw_desc),
                    0.995, 'EXACT_DESCRIPTION', 'AUTO_CORRECT',
                    'Description is an exact unique match in the canonical tyre master.'
                )

        # 5) fuzzy description match.  High threshold protects against false joins.
        best_row: dict[str, Any] | None = None
        best_score = 0.0
        second_score = 0.0
        for row in master_rows:
            candidate_desc = row.get('description')
            if not candidate_desc:
                continue
            score = _description_similarity(raw_desc, candidate_desc)
            if score > best_score:
                second_score = best_score
                best_score = score
                best_row = row
            elif score > second_score:
                second_score = score
        if best_row is not None:
            canonical = _code(best_row.get('sap_code'))
            margin = best_score - second_score
            if best_score >= 0.975 and margin >= 0.035:
                confidence = _clamp(0.90 + 0.08 * best_score + 0.02 * min(1.0, margin / 0.15), 0.0, 0.992)
                return IdentityResolution(
                    raw, canonical, raw_desc, clean_text(best_row.get('description') or raw_desc),
                    confidence, 'FUZZY_DESCRIPTION', 'AUTO_CORRECT' if confidence >= 0.985 else 'REVIEW',
                    f"Best description similarity {best_score:.3f}; separation from next candidate {margin:.3f}.",
                )
            if best_score >= 0.90:
                return IdentityResolution(
                    raw, canonical, raw_desc, clean_text(best_row.get('description') or raw_desc),
                    _clamp(0.72 + 0.18 * best_score, 0.0, 0.94),
                    'FUZZY_DESCRIPTION', 'REVIEW',
                    f"Possible description match ({best_score:.3f}) requires human review.",
                )

        return IdentityResolution(
            raw, raw, raw_desc, raw_desc, 0.25, 'UNRESOLVED', 'REVIEW',
            'No sufficiently reliable historical or master-data identity match was found.'
        )

    @staticmethod
    def _workbook_consensus(analysis) -> dict[str, tuple[str, int, int]]:
        votes: dict[str, Counter[str]] = defaultdict(Counter)
        totals: Counter[str] = Counter()
        for collection_name in ('stock_rows', 'shipment_rows', 'oven_rows', 'production_history_rows'):
            for row in getattr(analysis, collection_name, []) or []:
                desc = row.get('description') or row.get('item_description') or ''
                key = _description_key(desc)
                sap = _code(row.get('sap_code'))
                if not key or not sap:
                    continue
                votes[key][sap] += 1
                totals[key] += 1
        result: dict[str, tuple[str, int, int]] = {}
        for key, counter in votes.items():
            sap, count = counter.most_common(1)[0]
            result[key] = (sap, count, totals[key])
        return result

    def resolve_analysis(self, session, analysis, *, import_run_id: int | None = None, persist: bool = True) -> dict[str, Any]:
        self.ensure_schema(session)
        master_rows = self._master_rows(session)
        consensus = self._workbook_consensus(analysis)
        plan_date = None
        try:
            plan_date = date.fromisoformat(str(analysis.plan_date)) if analysis.plan_date else None
        except Exception:
            plan_date = None

        resolutions: dict[tuple[str, str], IdentityResolution] = {}
        auto_corrected = 0
        reviewed = 0
        unresolved = 0
        touched = 0
        collections = ('stock_rows', 'shipment_rows', 'oven_rows', 'production_history_rows')
        for collection_name in collections:
            for row in getattr(analysis, collection_name, []) or []:
                # Keep the original workbook identity across preview -> commit.
                # The preview pass may already have replaced row['sap_code'] with
                # a high-confidence canonical code; raw_sap_code preserves the
                # evidence needed to learn/audit that correction on commit.
                raw_sap = _code(row.get('raw_sap_code') or row.get('sap_code'))
                description = row.get('description') or row.get('item_description') or ''
                cache_key = (raw_sap, _description_key(description))
                resolution = resolutions.get(cache_key)
                if resolution is None:
                    resolution = self.resolve_identity(
                        session,
                        raw_sap_code=raw_sap,
                        description=description,
                        master_rows=master_rows,
                        workbook_consensus=consensus,
                    )
                    resolutions[cache_key] = resolution
                touched += 1
                if resolution.action == 'AUTO_CORRECT' and resolution.canonical_sap_code and resolution.canonical_sap_code != raw_sap:
                    row['raw_sap_code'] = raw_sap
                    row['sap_code'] = resolution.canonical_sap_code
                    row['identity_resolution_method'] = resolution.method
                    row['identity_confidence'] = resolution.confidence_score
                    auto_corrected += 1
                elif resolution.action == 'REVIEW':
                    reviewed += 1
                    if resolution.method == 'UNRESOLVED':
                        unresolved += 1

        if persist:
            for resolution in resolutions.values():
                if resolution.action == 'AUTO_CORRECT' and resolution.canonical_sap_code:
                    alias_key = _description_key(resolution.raw_description)
                    if alias_key:
                        session.execute(
                            text(
                                """
                                INSERT INTO mpps_identity_aliases (
                                    alias_type, alias_key, raw_value, canonical_sap_code,
                                    canonical_description, confidence_score, evidence_count,
                                    source, is_approved, last_seen_plan_date, updated_at
                                ) VALUES (
                                    'DESCRIPTION', :alias_key, :raw_value, :canonical_sap_code,
                                    :canonical_description, :confidence_score, 1,
                                    :source, FALSE, :plan_date, CURRENT_TIMESTAMP
                                )
                                ON CONFLICT (alias_type, alias_key, canonical_sap_code)
                                DO UPDATE SET
                                    confidence_score = GREATEST(mpps_identity_aliases.confidence_score, EXCLUDED.confidence_score),
                                    evidence_count = mpps_identity_aliases.evidence_count + 1,
                                    last_seen_plan_date = EXCLUDED.last_seen_plan_date,
                                    updated_at = CURRENT_TIMESTAMP
                                """
                            ),
                            {
                                'alias_key': alias_key,
                                'raw_value': resolution.raw_description,
                                'canonical_sap_code': resolution.canonical_sap_code,
                                'canonical_description': resolution.canonical_description,
                                'confidence_score': resolution.confidence_score,
                                'source': resolution.method,
                                'plan_date': plan_date,
                            },
                        )
                session.execute(
                    text(
                        """
                        INSERT INTO mpps_identity_resolution_log (
                            import_run_id, plan_date, raw_sap_code, canonical_sap_code,
                            raw_description, canonical_description, confidence_score,
                            resolution_method, action, explanation, source_workbook
                        ) VALUES (
                            :import_run_id, :plan_date, :raw_sap_code, :canonical_sap_code,
                            :raw_description, :canonical_description, :confidence_score,
                            :resolution_method, :action, :explanation, :source_workbook
                        )
                        """
                    ),
                    {
                        'import_run_id': import_run_id,
                        'plan_date': plan_date,
                        'raw_sap_code': resolution.raw_sap_code,
                        'canonical_sap_code': resolution.canonical_sap_code,
                        'raw_description': resolution.raw_description,
                        'canonical_description': resolution.canonical_description,
                        'confidence_score': resolution.confidence_score,
                        'resolution_method': resolution.method,
                        'action': resolution.action,
                        'explanation': resolution.explanation,
                        'source_workbook': str(getattr(analysis, 'workbook_name', '') or ''),
                    },
                )
        return {
            'identity_rows_checked': touched,
            'identity_unique_pairs': len(resolutions),
            'identity_auto_corrected': auto_corrected,
            'identity_review_rows': reviewed,
            'identity_unresolved_rows': unresolved,
            '_resolutions': resolutions,
        }

    def capture_opening_stock(
        self,
        session,
        *,
        import_run_id: int,
        analysis,
        import_mode: str,
    ) -> dict[str, Any]:
        """Capture PROD column-D stock as monthly opening-stock evidence.

        The OVEN workbook keeps this stock column as a monthly opening balance;
        daily production is represented separately in dated DAY/NIGHT pairs.
        Therefore the stock column must not be treated as a fresh daily physical
        stock count.  LIVE workbooks may establish/revise the month's opening
        authority; historical workbooks only add evidence.
        """
        self.ensure_schema(session)
        try:
            plan_date = date.fromisoformat(str(analysis.plan_date))
        except Exception:
            return {'opening_stock_rows': 0, 'opening_stock_month': None}
        month_key = plan_date.strftime('%Y-%m')
        mode = str(import_mode or 'HISTORICAL').upper()
        rows = [row for row in (analysis.stock_rows or []) if _code(row.get('sap_code'))]

        changes = 0
        negative = 0
        for row in rows:
            raw = _int(row.get('fg_stock'))
            normalized = max(0, raw)
            if raw < 0:
                negative += 1
            session.execute(
                text(
                    """
                    INSERT INTO mpps_opening_stock_evidence (
                        import_run_id, plan_date, month_key, sap_code, item_description,
                        raw_stock_qty, normalized_opening_qty, scrap_qty, blocked_qty,
                        import_mode, source_workbook, source_sheet, source_row
                    ) VALUES (
                        :import_run_id, :plan_date, :month_key, :sap_code, :item_description,
                        :raw_stock_qty, :normalized_opening_qty, :scrap_qty, :blocked_qty,
                        :import_mode, :source_workbook, :source_sheet, :source_row
                    )
                    ON CONFLICT (import_run_id, sap_code)
                    DO UPDATE SET
                        raw_stock_qty = EXCLUDED.raw_stock_qty,
                        normalized_opening_qty = EXCLUDED.normalized_opening_qty,
                        scrap_qty = EXCLUDED.scrap_qty,
                        blocked_qty = EXCLUDED.blocked_qty,
                        item_description = EXCLUDED.item_description
                    """
                ),
                {
                    'import_run_id': import_run_id,
                    'plan_date': plan_date,
                    'month_key': month_key,
                    'sap_code': _code(row.get('sap_code')),
                    'item_description': clean_text(row.get('description') or ''),
                    'raw_stock_qty': raw,
                    'normalized_opening_qty': normalized,
                    'scrap_qty': max(0, _int(row.get('scrap_stock'))),
                    'blocked_qty': max(0, _int(row.get('blocked_stock'))),
                    'import_mode': mode,
                    'source_workbook': str(getattr(analysis, 'workbook_name', '') or ''),
                    'source_sheet': str(row.get('source_sheet') or 'PROD'),
                    'source_row': row.get('source_row'),
                },
            )

        if mode == 'LIVE' and rows:
            # Latest LIVE workbook inside the month is the operational opening-stock
            # authority. Historical evidence remains available for mismatch checks.
            header = session.execute(
                text(
                    """
                    SELECT id, source_plan_date
                    FROM monthly_stock_counts
                    WHERE month_key = :month_key AND is_active = TRUE
                    ORDER BY uploaded_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {'month_key': month_key},
            ).mappings().first()
            if header and header.get('source_plan_date') and header['source_plan_date'] > plan_date:
                # Never move the month's source backwards.
                return {
                    'opening_stock_rows': len(rows),
                    'opening_stock_month': month_key,
                    'opening_stock_live_applied': 0,
                    'opening_stock_negative_evidence': negative,
                }

            if not header:
                count_id = session.execute(
                    text(
                        """
                        INSERT INTO monthly_stock_counts (
                            stock_month_label, month_key, file_name, sheet_name,
                            uploaded_at, uploaded_by, total_rows, is_active, status,
                            remarks, source_authority, source_plan_date,
                            source_import_run_id, source_confidence, evidence_count
                        ) VALUES (
                            :label, :month_key, :file_name, 'PROD', CURRENT_TIMESTAMP,
                            'OVEN Excel Auto', :total_rows, TRUE, 'IMPORTED',
                            'Auto-captured from PROD TOTAL STOCK column.',
                            'OVEN_PROD_STOCK', :source_plan_date, :source_import_run_id,
                            1, 1
                        ) RETURNING id
                        """
                    ),
                    {
                        'label': plan_date.strftime('%B %Y'),
                        'month_key': month_key,
                        'file_name': str(getattr(analysis, 'workbook_name', '') or ''),
                        'total_rows': len(rows),
                        'source_plan_date': plan_date,
                        'source_import_run_id': import_run_id,
                    },
                ).scalar_one()
            else:
                count_id = int(header['id'])
                session.execute(
                    text(
                        """
                        UPDATE monthly_stock_counts
                        SET file_name = :file_name,
                            total_rows = :total_rows,
                            source_authority = 'OVEN_PROD_STOCK',
                            source_plan_date = :source_plan_date,
                            source_import_run_id = :source_import_run_id,
                            evidence_count = COALESCE(evidence_count, 0) + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {
                        'file_name': str(getattr(analysis, 'workbook_name', '') or ''),
                        'total_rows': len(rows),
                        'source_plan_date': plan_date,
                        'source_import_run_id': import_run_id,
                        'id': count_id,
                    },
                )

            # Read the pre-import keys only for the later missing-row zeroing step.
            # Do NOT use this snapshot to decide INSERT vs UPDATE: long-lived MPPS
            # databases can have normalisation triggers / legacy aliases that make a
            # key appear absent to Python but conflict at constraint time.  PostgreSQL
            # is the authority for the natural key, so every line is written with an
            # atomic ON CONFLICT upsert.
            existing = {
                _code(row['material_code']): int(row['id'])
                for row in session.execute(
                    text('SELECT id, material_code FROM monthly_stock_count_lines WHERE stock_count_id = :id'),
                    {'id': count_id},
                ).mappings().all()
            }

            # Defensive de-duplication before the database write.  Real workbooks can
            # occasionally contain repeated/aliased SAP rows.  Keep one canonical row
            # per SAP for the monthly opening authority; the raw workbook evidence is
            # already retained separately in mpps_opening_stock_evidence.
            canonical_rows: dict[str, dict[str, Any]] = {}
            duplicate_rows_merged = 0
            for row in rows:
                sap = _code(row.get('sap_code'))
                if not sap:
                    continue
                if sap in canonical_rows:
                    duplicate_rows_merged += 1
                    current = canonical_rows[sap]
                    # Prefer the row with the stronger/non-zero stock signal. This does
                    # not sum duplicate rows (which would inflate physical stock).
                    if max(0, _int(row.get('fg_stock'))) > max(0, _int(current.get('fg_stock'))):
                        canonical_rows[sap] = row
                else:
                    canonical_rows[sap] = row

            seen: set[str] = set()
            for sap, row in canonical_rows.items():
                seen.add(sap)
                opening = max(0, _int(row.get('fg_stock')))
                params = {
                    'stock_count_id': count_id,
                    'material_code': sap,
                    'material_description': clean_text(row.get('description') or ''),
                    'fg_qty': opening,
                    'source_row_number': row.get('source_row'),
                }
                session.execute(
                    text(
                        """
                        INSERT INTO monthly_stock_count_lines (
                            stock_count_id, material_code, material_description,
                            fg_qty, qc_qty, balance_to_prd_qty, over_prd_qty,
                            source_row_number
                        ) VALUES (
                            :stock_count_id, :material_code, :material_description,
                            :fg_qty, 0, 0, 0, :source_row_number
                        )
                        ON CONFLICT (stock_count_id, material_code)
                        DO UPDATE SET
                            material_description = EXCLUDED.material_description,
                            fg_qty = EXCLUDED.fg_qty,
                            qc_qty = 0,
                            balance_to_prd_qty = 0,
                            over_prd_qty = 0,
                            source_row_number = EXCLUDED.source_row_number,
                            updated_at = CURRENT_TIMESTAMP
                        """
                    ),
                    params,
                )
                changes += 1
            # Rows no longer present in a newer live workbook are not deleted; they
            # are set to zero so history/audit references remain intact.
            missing = set(existing) - seen
            # Update one natural key at a time instead of relying on a driver-specific
            # PostgreSQL ARRAY bind.  This keeps the V10 installer safe across psycopg
            # / SQLAlchemy versions used by existing factory PCs.
            for material_code in sorted(missing):
                session.execute(
                    text(
                        """
                        UPDATE monthly_stock_count_lines
                        SET fg_qty = 0, qc_qty = 0, balance_to_prd_qty = 0,
                            over_prd_qty = 0, updated_at = CURRENT_TIMESTAMP
                        WHERE stock_count_id = :stock_count_id
                          AND material_code = :material_code
                        """
                    ),
                    {
                        'stock_count_id': count_id,
                        'material_code': material_code,
                    },
                )
            return {
                'opening_stock_rows': len(rows),
                'opening_stock_month': month_key,
                'opening_stock_live_applied': changes,
                'opening_stock_negative_evidence': negative,
                'opening_stock_duplicate_rows_merged': duplicate_rows_merged,
            }
        return {
            'opening_stock_rows': len(rows),
            'opening_stock_month': month_key,
            'opening_stock_live_applied': 0,
            'opening_stock_negative_evidence': negative,
        }

    @staticmethod
    def _daily_actual_rows(session) -> list[dict[str, Any]]:
        try:
            return [
                dict(row)
                for row in session.execute(
                    text(
                        """
                        SELECT production_date,
                               SUM(day_actual_qty) AS day_actual_qty,
                               SUM(night_actual_qty) AS night_actual_qty,
                               SUM(total_actual_qty) AS total_actual_qty,
                               COUNT(*) FILTER (WHERE total_actual_qty > 0) AS active_sap_count,
                               MAX(source_workbook) AS source_workbook
                        FROM mpps_actual_production
                        GROUP BY production_date
                        ORDER BY production_date
                        """
                    )
                ).mappings().all()
            ]
        except Exception:
            return []

    def rebuild_daily_capacity(self, session) -> dict[str, int]:
        self.ensure_schema(session)
        actual_rows = self._daily_actual_rows(session)
        plan_by_date: dict[date, int] = {}
        try:
            plan_rows = session.execute(
                text(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (plan_date, sap_code)
                               plan_date, sap_code, total_plan_qty, import_run_id
                        FROM mpps_final_plan_history
                        ORDER BY plan_date, sap_code, import_run_id DESC
                    )
                    SELECT plan_date, SUM(total_plan_qty) AS qty
                    FROM latest GROUP BY plan_date
                    """
                )
            ).mappings().all()
            plan_by_date = {row['plan_date']: _int(row['qty']) for row in plan_rows}
        except Exception:
            plan_by_date = {}

        for row in actual_rows:
            production_date = row['production_date']
            total_actual = max(0, _int(row.get('total_actual_qty')))
            total_plan = max(0, plan_by_date.get(production_date, 0))
            achievement = total_actual / max(total_plan, 1) * 100.0 if total_plan > 0 else 0.0
            session.execute(
                text(
                    """
                    INSERT INTO mpps_factory_daily_capacity (
                        production_date, day_actual_qty, night_actual_qty,
                        total_actual_qty, active_sap_count, total_plan_qty,
                        achievement_pct, source_workbook, updated_at
                    ) VALUES (
                        :production_date, :day_actual_qty, :night_actual_qty,
                        :total_actual_qty, :active_sap_count, :total_plan_qty,
                        :achievement_pct, :source_workbook, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (production_date)
                    DO UPDATE SET
                        day_actual_qty = EXCLUDED.day_actual_qty,
                        night_actual_qty = EXCLUDED.night_actual_qty,
                        total_actual_qty = EXCLUDED.total_actual_qty,
                        active_sap_count = EXCLUDED.active_sap_count,
                        total_plan_qty = EXCLUDED.total_plan_qty,
                        achievement_pct = EXCLUDED.achievement_pct,
                        source_workbook = EXCLUDED.source_workbook,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {
                    'production_date': production_date,
                    'day_actual_qty': max(0, _int(row.get('day_actual_qty'))),
                    'night_actual_qty': max(0, _int(row.get('night_actual_qty'))),
                    'total_actual_qty': total_actual,
                    'active_sap_count': max(0, _int(row.get('active_sap_count'))),
                    'total_plan_qty': total_plan,
                    'achievement_pct': achievement,
                    'source_workbook': str(row.get('source_workbook') or ''),
                },
            )
        return {'factory_daily_capacity_days': len(actual_rows)}

    @staticmethod
    def _capacity_fit(values: list[tuple[date, float, float, float]]) -> dict[str, Any]:
        """Fit a robust capacity envelope with leakage-safe walk-forward validation.

        Input tuples are (date, total_qty, day_qty, night_qty).  The model uses
        robust quantiles, EWMA recency and weekday behavior. It predicts the next
        observation before learning that observation, so validation is not inflated
        by target leakage.
        """
        values = sorted(values, key=lambda item: item[0])
        history: list[float] = []
        weekday: dict[int, list[float]] = defaultdict(list)
        predictions: list[tuple[float, float]] = []
        alpha = 0.30
        ewma: float | None = None
        day_shares: list[float] = []
        for production_date, total, day_qty, night_qty in values:
            total = max(0.0, float(total))
            if history:
                robust = median(history[-30:])
                recent = ewma if ewma is not None else robust
                weekday_values = weekday.get(production_date.weekday(), [])
                weekday_est = median(weekday_values[-8:]) if len(weekday_values) >= 2 else robust
                prediction = 0.45 * robust + 0.35 * recent + 0.20 * weekday_est
                predictions.append((prediction, total))
            history.append(total)
            weekday[production_date.weekday()].append(total)
            ewma = total if ewma is None else alpha * total + (1.0 - alpha) * ewma
            if total > 0:
                day_shares.append(_clamp(day_qty / total, 0.0, 1.0))

        sample_days = len(history)
        window = history[-60:]
        expected = 0.0
        safe = 0.0
        stretch = 0.0
        recent_capacity = 0.0
        if window:
            robust = median(window)
            p25 = _quantile(window, 0.25, robust)
            p80 = _quantile(window, 0.80, robust)
            recent_capacity = ewma if ewma is not None else robust
            expected = 0.55 * robust + 0.45 * recent_capacity
            safe = min(expected, p25 if sample_days >= 5 else expected * 0.90)
            stretch = max(expected, p80)
        if predictions:
            abs_error = sum(abs(pred - actual) for pred, actual in predictions)
            actual_total = sum(abs(actual) for _, actual in predictions)
            wape = abs_error / max(actual_total, 1.0) * 100.0
        else:
            wape = 100.0
        stability = 0.0
        if len(window) >= 2:
            center = max(mean(window), 1.0)
            mad = mean(abs(value - center) for value in window)
            stability = _clamp(1.0 - mad / center, 0.0, 1.0)
        trend = 0.0
        if len(window) >= 8:
            previous = mean(window[-8:-4])
            recent4 = mean(window[-4:])
            trend = _clamp((recent4 - previous) / max(previous, 1.0), -0.30, 0.30)
        sample_score = _clamp(sample_days / 30.0, 0.0, 1.0)
        validation_score = _clamp((100.0 - min(100.0, wape)) / 100.0, 0.0, 1.0)
        confidence = _clamp(0.42 * sample_score + 0.38 * validation_score + 0.20 * stability, 0.0, 1.0)
        if sample_days < 5:
            band = 'LEARNING'
        elif confidence >= 0.82:
            band = 'HIGH'
        elif confidence >= 0.60:
            band = 'MEDIUM'
        else:
            band = 'LOW'
        weekday_model = {
            str(k): {
                'median': round(median(v[-12:]), 4),
                'samples': len(v),
            }
            for k, v in weekday.items() if v
        }
        return {
            'sample_days': sample_days,
            'safe_capacity_qty': round(max(0.0, safe), 4),
            'expected_capacity_qty': round(max(0.0, expected), 4),
            'stretch_capacity_qty': round(max(0.0, stretch), 4),
            'recent_capacity_qty': round(max(0.0, recent_capacity), 4),
            'day_share': round(mean(day_shares[-60:]), 6) if day_shares else 0.5,
            'stability_score': round(stability, 6),
            'trend_score': round(trend, 6),
            'confidence_score': round(confidence, 6),
            'confidence_band': band,
            'validation_wape_pct': round(wape, 4),
            'weekday_model': weekday_model,
            'history_tail': [round(v, 3) for v in window[-30:]],
        }

    def train_capacity_models(self, session) -> dict[str, int]:
        self.ensure_schema(session)
        self.rebuild_daily_capacity(session)
        factory_rows = [
            dict(row)
            for row in session.execute(
                text(
                    """
                    SELECT production_date, total_actual_qty, day_actual_qty, night_actual_qty
                    FROM mpps_factory_daily_capacity
                    ORDER BY production_date
                    """
                )
            ).mappings().all()
        ]
        fitted = 0
        high = 0
        if factory_rows:
            values = [
                (row['production_date'], _float(row['total_actual_qty']), _float(row['day_actual_qty']), _float(row['night_actual_qty']))
                for row in factory_rows
            ]
            model = self._capacity_fit(values)
            self._upsert_capacity_model(session, 'FACTORY', 'FACTORY', model)
            fitted += 1
            if model['confidence_band'] == 'HIGH':
                high += 1

        # Per-SAP actual production capacity. Zero-output days are intentionally not
        # inserted for SAPs that were not planned; the execution model handles plan
        # completion separately.
        sap_rows = session.execute(
            text(
                """
                SELECT production_date, sap_code,
                       day_actual_qty, night_actual_qty, total_actual_qty
                FROM mpps_actual_production
                WHERE total_actual_qty > 0
                ORDER BY sap_code, production_date
                """
            )
        ).mappings().all()
        grouped: dict[str, list[tuple[date, float, float, float]]] = defaultdict(list)
        for row in sap_rows:
            sap = _code(row['sap_code'])
            if not sap:
                continue
            grouped[sap].append((
                row['production_date'], _float(row['total_actual_qty']),
                _float(row['day_actual_qty']), _float(row['night_actual_qty'])
            ))
        for sap, values in grouped.items():
            model = self._capacity_fit(values)
            self._upsert_capacity_model(session, 'SAP', sap, model)
            fitted += 1
            if model['confidence_band'] == 'HIGH':
                high += 1

        return {'factory_capacity_models_trained': fitted, 'factory_capacity_high_confidence': high}

    @classmethod
    def _upsert_capacity_model(cls, session, level: str, entity_key: str, model: dict[str, Any]) -> None:
        session.execute(
            text(
                """
                INSERT INTO mpps_factory_capacity_models (
                    model_key, model_level, entity_key, sample_days,
                    safe_capacity_qty, expected_capacity_qty, stretch_capacity_qty,
                    recent_capacity_qty, day_share, stability_score, trend_score,
                    confidence_score, confidence_band, validation_wape_pct,
                    model_json, last_trained_at, updated_at
                ) VALUES (
                    :model_key, :model_level, :entity_key, :sample_days,
                    :safe_capacity_qty, :expected_capacity_qty, :stretch_capacity_qty,
                    :recent_capacity_qty, :day_share, :stability_score, :trend_score,
                    :confidence_score, :confidence_band, :validation_wape_pct,
                    CAST(:model_json AS JSONB), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT (model_key)
                DO UPDATE SET
                    sample_days = EXCLUDED.sample_days,
                    safe_capacity_qty = EXCLUDED.safe_capacity_qty,
                    expected_capacity_qty = EXCLUDED.expected_capacity_qty,
                    stretch_capacity_qty = EXCLUDED.stretch_capacity_qty,
                    recent_capacity_qty = EXCLUDED.recent_capacity_qty,
                    day_share = EXCLUDED.day_share,
                    stability_score = EXCLUDED.stability_score,
                    trend_score = EXCLUDED.trend_score,
                    confidence_score = EXCLUDED.confidence_score,
                    confidence_band = EXCLUDED.confidence_band,
                    validation_wape_pct = EXCLUDED.validation_wape_pct,
                    model_json = EXCLUDED.model_json,
                    last_trained_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                'model_key': f'{level}|{entity_key}',
                'model_level': level,
                'entity_key': entity_key,
                **{k: model[k] for k in (
                    'sample_days', 'safe_capacity_qty', 'expected_capacity_qty',
                    'stretch_capacity_qty', 'recent_capacity_qty', 'day_share',
                    'stability_score', 'trend_score', 'confidence_score',
                    'confidence_band', 'validation_wape_pct'
                )},
                'model_json': json.dumps({
                    'version': cls.MODEL_VERSION,
                    'algorithm': 'robust quantile + EWMA + weekday walk-forward ensemble',
                    'leakage_safe': True,
                    'weekday_model': model.get('weekday_model', {}),
                    'history_tail': model.get('history_tail', []),
                }, default=str),
            },
        )

    @staticmethod
    def _planner_policy_fit(observations: list[tuple[date, float, float]]) -> dict[str, Any]:
        observations = sorted(observations, key=lambda row: row[0])
        ratios: list[float] = []
        predictions: list[tuple[float, float]] = []
        ewma = 1.0
        initialized = False
        alpha = 0.30
        for _day, required, planned in observations:
            required = max(0.0, required)
            planned = max(0.0, planned)
            if required <= 0:
                continue
            if ratios:
                robust = median(ratios[-30:])
                prediction_ratio = 0.55 * robust + 0.45 * ewma
                predictions.append((required * prediction_ratio, planned))
            ratio = _clamp(planned / required, 0.25, 2.50)
            ratios.append(ratio)
            ewma = ratio if not initialized else alpha * ratio + (1.0 - alpha) * ewma
            initialized = True
        if not ratios:
            return {
                'sample_days': 0, 'planning_ratio': 1.0, 'conservative_ratio': 1.0,
                'validation_wape_pct': 100.0, 'confidence_score': 0.0,
                'confidence_band': 'LEARNING', 'ratios': []
            }
        robust = median(ratios[-60:])
        planning_ratio = _clamp(0.55 * robust + 0.45 * ewma, 0.50, 1.80)
        conservative = _clamp(max(planning_ratio, _quantile(ratios[-60:], 0.70, planning_ratio)), 0.50, 2.0)
        if predictions:
            error = sum(abs(p-a) for p,a in predictions)
            actual = sum(abs(a) for _,a in predictions)
            wape = error / max(actual, 1.0) * 100.0
        else:
            wape = 100.0
        sample_score = _clamp(len(ratios) / 24.0, 0.0, 1.0)
        validation_score = _clamp((100.0 - min(100.0, wape)) / 100.0, 0.0, 1.0)
        stability = 1.0
        if len(ratios) >= 2:
            center = mean(ratios[-30:])
            stability = _clamp(1.0 - mean(abs(r-center) for r in ratios[-30:]) / max(center, 0.1), 0.0, 1.0)
        confidence = _clamp(0.45*sample_score + 0.35*validation_score + 0.20*stability, 0.0, 1.0)
        band = 'LEARNING' if len(ratios) < 4 else ('HIGH' if confidence >= 0.82 else 'MEDIUM' if confidence >= 0.58 else 'LOW')
        return {
            'sample_days': len(ratios),
            'planning_ratio': round(planning_ratio, 6),
            'conservative_ratio': round(conservative, 6),
            'validation_wape_pct': round(wape, 4),
            'confidence_score': round(confidence, 6),
            'confidence_band': band,
            'ratios': [round(r, 5) for r in ratios[-60:]],
        }

    def train_planner_policy(self, session) -> dict[str, int]:
        self.ensure_schema(session)
        try:
            rows = session.execute(text(
                """
                SELECT plan_date, sap_code, excel_production_required, excel_planned_qty
                FROM excel_plan_reconciliation
                WHERE excel_production_required > 0 AND excel_planned_qty >= 0
                ORDER BY sap_code, plan_date, import_run_id
                """
            )).mappings().all()
        except Exception:
            rows = []
        grouped: dict[str, list[tuple[date,float,float]]] = defaultdict(list)
        all_rows: list[tuple[date,float,float]] = []
        for row in rows:
            try:
                d = row['plan_date']
                if not isinstance(d, date): d = date.fromisoformat(str(d))
            except Exception:
                continue
            item = (d, _float(row['excel_production_required']), _float(row['excel_planned_qty']))
            grouped[_code(row['sap_code'])].append(item)
            all_rows.append(item)
        models = 0
        for sap, obs in [('__GLOBAL__', all_rows), *grouped.items()]:
            if not obs:
                continue
            model = self._planner_policy_fit(obs)
            session.execute(text(
                """
                INSERT INTO mpps_planner_policy_models (
                    model_key, sap_code, sample_days, planning_ratio, conservative_ratio,
                    validation_wape_pct, confidence_score, confidence_band, model_json,
                    last_trained_at, updated_at
                ) VALUES (
                    :model_key, :sap_code, :sample_days, :planning_ratio, :conservative_ratio,
                    :validation_wape_pct, :confidence_score, :confidence_band,
                    CAST(:model_json AS JSONB), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                ) ON CONFLICT (model_key) DO UPDATE SET
                    sample_days=EXCLUDED.sample_days, planning_ratio=EXCLUDED.planning_ratio,
                    conservative_ratio=EXCLUDED.conservative_ratio,
                    validation_wape_pct=EXCLUDED.validation_wape_pct,
                    confidence_score=EXCLUDED.confidence_score,
                    confidence_band=EXCLUDED.confidence_band, model_json=EXCLUDED.model_json,
                    last_trained_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                """
            ), {
                'model_key': f'PLANNER_POLICY|{sap}', 'sap_code': '' if sap=='__GLOBAL__' else sap,
                **{k:model[k] for k in ('sample_days','planning_ratio','conservative_ratio','validation_wape_pct','confidence_score','confidence_band')},
                'model_json': json.dumps({'version':self.MODEL_VERSION,'algorithm':'human-final-plan policy ratio walk-forward model','ratios':model['ratios']}, default=str),
            })
            models += 1
        return {'planner_policy_models_trained': models}

    @staticmethod
    def planner_policy_for_sap(session, sap_code: str) -> dict[str, Any]:
        sap = _code(sap_code)
        try:
            row = session.execute(text(
                """
                SELECT * FROM mpps_planner_policy_models
                WHERE model_key IN (:sap_key, 'PLANNER_POLICY|__GLOBAL__')
                ORDER BY CASE WHEN model_key=:sap_key THEN 0 ELSE 1 END LIMIT 1
                """
            ), {'sap_key': f'PLANNER_POLICY|{sap}'}).mappings().first()
            return dict(row) if row else {}
        except Exception:
            return {}

    def approve_identity_mapping(
        self,
        session,
        *,
        raw_description: str,
        canonical_sap_code: str,
        plan_date: date | None = None,
    ) -> dict[str, Any]:
        """Approve a human-reviewed description -> SAP mapping.

        Approved aliases are treated as deterministic high-confidence evidence on
        later OVEN imports.  This is the supervised-learning bridge between a
        planner correction and future automatic data healing.
        """
        self.ensure_schema(session)
        alias_key = _description_key(raw_description)
        sap = _code(canonical_sap_code)
        if not alias_key:
            raise ValueError('A source description is required for identity learning.')
        if not sap:
            raise ValueError('A canonical SAP code is required.')
        master = next((r for r in self._master_rows(session) if _code(r.get('sap_code')) == sap), None)
        if master is None:
            raise ValueError(f'SAP {sap} is not present in the canonical tyre master.')
        canonical_description = clean_text(master.get('description') or '')
        session.execute(
            text(
                """
                INSERT INTO mpps_identity_aliases (
                    alias_type, alias_key, raw_value, canonical_sap_code,
                    canonical_description, confidence_score, evidence_count,
                    source, is_approved, last_seen_plan_date, updated_at
                ) VALUES (
                    'DESCRIPTION', :alias_key, :raw_value, :canonical_sap_code,
                    :canonical_description, 1.0, 1,
                    'USER_APPROVED', TRUE, :plan_date, CURRENT_TIMESTAMP
                )
                ON CONFLICT (alias_type, alias_key, canonical_sap_code)
                DO UPDATE SET
                    raw_value = EXCLUDED.raw_value,
                    canonical_description = EXCLUDED.canonical_description,
                    confidence_score = 1.0,
                    evidence_count = mpps_identity_aliases.evidence_count + 1,
                    source = 'USER_APPROVED',
                    is_approved = TRUE,
                    last_seen_plan_date = COALESCE(EXCLUDED.last_seen_plan_date, mpps_identity_aliases.last_seen_plan_date),
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                'alias_key': alias_key,
                'raw_value': clean_text(raw_description),
                'canonical_sap_code': sap,
                'canonical_description': canonical_description,
                'plan_date': plan_date,
            },
        )
        return {
            'raw_description': clean_text(raw_description),
            'canonical_sap_code': sap,
            'canonical_description': canonical_description,
            'confidence_score': 1.0,
            'source': 'USER_APPROVED',
        }

    @staticmethod
    def capacity_for_sap(session, sap_code: str) -> dict[str, Any]:
        """Compatibility bridge to the V11 authoritative capacity resolver.

        Older AI/planning callers expect mpps_factory_capacity_models-style keys.
        V11 keeps that contract while routing new decisions through the resource-
        aware resolver. If the V11 schema is not available yet, the legacy V10
        model remains a safe fallback during migration.
        """
        sap = _code(sap_code)
        try:
            from app.services.factory_resource_intelligence_service import (
                FactoryResourceIntelligenceService,
            )
            resolved = FactoryResourceIntelligenceService.resolve_capacity(
                session,
                sap,
            )
            if (
                resolved.expected_capacity > 0
                or resolved.technical_capacity > 0
            ):
                return {
                    "model_key": resolved.model_key or f"V11|{sap}",
                    "model_level": "SAP",
                    "entity_key": sap,
                    "safe_capacity_qty": resolved.safe_capacity,
                    "expected_capacity_qty": resolved.expected_capacity,
                    "stretch_capacity_qty": resolved.stretch_capacity,
                    "recent_capacity_qty": resolved.expected_capacity,
                    "confidence_score": resolved.confidence_score,
                    "confidence_band": resolved.confidence_band,
                    "capacity_source": resolved.source,
                    "available_capacity_qty": resolved.available_capacity,
                    "constraint_reason": resolved.constraint_reason,
                    "stable_cavity_count": resolved.stable_cavity_count,
                    "observed_max_cavity_count": resolved.observed_max_cavity_count,
                    "mold_key": resolved.mold_key,
                    "casing_type": resolved.casing_type,
                }
        except Exception:
            pass

        row = session.execute(
            text(
                """
                SELECT * FROM mpps_factory_capacity_models
                WHERE model_key IN (:sap_key, 'FACTORY|FACTORY')
                ORDER BY CASE WHEN model_key = :sap_key THEN 0 ELSE 1 END
                LIMIT 1
                """
            ),
            {'sap_key': f'SAP|{sap}'},
        ).mappings().first()
        return dict(row) if row else {}

    def refresh_state(self, session) -> dict[str, Any]:
        self.ensure_schema(session)
        source = OperationalSourceService.latest(session)
        counts = session.execute(
            text(
                """
                SELECT
                  (SELECT COUNT(*) FROM excel_import_runs WHERE status IN ('COMMITTED','COMMITTED WITH WARNINGS') AND rollback_at IS NULL) AS workbooks,
                  (SELECT COUNT(DISTINCT production_date) FROM mpps_actual_production_dates WHERE is_complete = TRUE) AS actual_days,
                  (SELECT COUNT(*) FROM mpps_factory_capacity_models) AS capacity_models,
                  (SELECT COUNT(*) FROM mpps_identity_aliases) AS aliases,
                  (SELECT COUNT(*) FROM mpps_identity_resolution_log WHERE action = 'REVIEW') AS unresolved,
                  (SELECT COUNT(*) FROM mpps_ai_model_state) AS ai_models,
                  (SELECT COUNT(*) FROM mpps_ai_model_state WHERE confidence_band = 'HIGH') AS ai_high
                """
            )
        ).mappings().first() or {}
        actual_days = _int(counts.get('actual_days'))
        workbooks = _int(counts.get('workbooks'))
        coverage = _clamp(actual_days / max(workbooks, 1) * 100.0, 0.0, 100.0) if workbooks else 0.0
        cap_conf_row = session.execute(
            text("SELECT AVG(confidence_score) AS c FROM mpps_factory_capacity_models")
        ).mappings().first() or {}
        cap_conf = _float(cap_conf_row.get('c')) * 100.0
        session.execute(
            text(
                """
                UPDATE mpps_factory_intelligence_state
                SET model_version = :model_version,
                    latest_operational_date = :latest_operational_date,
                    historical_workbook_count = :workbooks,
                    actual_production_days = :actual_days,
                    capacity_model_count = :capacity_models,
                    identity_alias_count = :aliases,
                    unresolved_identity_count = :unresolved,
                    data_coverage_pct = :coverage,
                    capacity_confidence_pct = :capacity_confidence,
                    last_trained_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """
            ),
            {
                'model_version': self.MODEL_VERSION,
                'latest_operational_date': source.plan_date,
                'workbooks': workbooks,
                'actual_days': actual_days,
                'capacity_models': _int(counts.get('capacity_models')),
                'aliases': _int(counts.get('aliases')),
                'unresolved': _int(counts.get('unresolved')),
                'coverage': coverage,
                'capacity_confidence': cap_conf,
            },
        )
        return {
            'model_version': self.MODEL_VERSION,
            'latest_operational_date': source.plan_date.isoformat() if source.plan_date else None,
            'workbooks': workbooks,
            'actual_days': actual_days,
            'capacity_models': _int(counts.get('capacity_models')),
            'aliases': _int(counts.get('aliases')),
            'unresolved': _int(counts.get('unresolved')),
            'data_coverage_pct': round(coverage, 2),
            'capacity_confidence_pct': round(cap_conf, 2),
            'ai_models': _int(counts.get('ai_models')),
            'ai_high_confidence': _int(counts.get('ai_high')),
        }

    def post_excel_import(self, session, *, import_run_id: int, analysis, import_mode: str) -> dict[str, Any]:
        self.ensure_schema(session)
        result: dict[str, Any] = {}
        result.update(self.capture_opening_stock(
            session,
            import_run_id=import_run_id,
            analysis=analysis,
            import_mode=import_mode,
        ))
        result.update(self.train_capacity_models(session))
        result.update(self.train_planner_policy(session))
        result.update(self.refresh_state(session))
        return result

    def dashboard(self, session, *, limit: int = 300) -> dict[str, Any]:
        self.ensure_schema(session)
        state = self.refresh_state(session)
        capacity = [
            dict(row) for row in session.execute(
                text(
                    """
                    SELECT * FROM mpps_factory_capacity_models
                    ORDER BY CASE WHEN model_level='FACTORY' THEN 0 ELSE 1 END,
                             confidence_score DESC, sample_days DESC
                    LIMIT :limit
                    """
                ), {'limit': max(1, min(5000, int(limit)))}
            ).mappings().all()
        ]
        identity = [
            dict(row) for row in session.execute(
                text(
                    """
                    SELECT * FROM mpps_identity_resolution_log
                    ORDER BY id DESC LIMIT :limit
                    """
                ), {'limit': max(1, min(5000, int(limit)))}
            ).mappings().all()
        ]
        opening = [
            dict(row) for row in session.execute(
                text(
                    """
                    SELECT plan_date, month_key, sap_code, item_description,
                           raw_stock_qty, normalized_opening_qty, import_mode,
                           source_workbook
                    FROM mpps_opening_stock_evidence
                    ORDER BY plan_date DESC, sap_code
                    LIMIT :limit
                    """
                ), {'limit': max(1, min(5000, int(limit)))}
            ).mappings().all()
        ]
        daily = [
            dict(row) for row in session.execute(
                text(
                    """
                    SELECT * FROM mpps_factory_daily_capacity
                    ORDER BY production_date DESC LIMIT :limit
                    """
                ), {'limit': max(1, min(5000, int(limit)))}
            ).mappings().all()
        ]
        return {'state': state, 'capacity_models': capacity, 'identity_log': identity, 'opening_stock_evidence': opening, 'daily_capacity': daily}


__all__ = [
    'FactoryIntelligenceService',
    'IdentityResolution',
    '_description_key',
    '_description_similarity',
]
