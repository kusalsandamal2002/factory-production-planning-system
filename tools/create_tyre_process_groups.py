from sqlalchemy import text
from app.database import engine
import re


def clean(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def extract_tyre_size(description: str) -> str:
    desc = clean(description).upper()

    patterns = [
        r"\d{1,2}\.\d{2}-\d{1,2}",
        r"\d{1,2}\.\d{2}\s*-\s*\d{1,2}",
        r"\d{2,3}/\d{2,3}-\d{1,2}",
        r"\d{1,2}X\d{1,2}(?:\s+\d/\d)?-\d{1,2}(?:\s+\d/\d)?",
        r"\d{1,2}X\d{1,2}(?:\s+\d/\d)?",
    ]

    for pattern in patterns:
        match = re.search(pattern, desc)
        if match:
            return clean(match.group(0).replace(" ", ""))

    parts = desc.split()
    return parts[0] if parts else ""


def extract_layer(description: str) -> str:
    desc = clean(description).upper()

    if " 2L" in f" {desc} " or "-2L" in desc or "STD-2L" in desc:
        return "2L"
    if " 3L" in f" {desc} " or "-3L" in desc or "STD-3L" in desc:
        return "3L"

    return "NM"


def extract_color(description: str) -> str:
    desc = clean(description).upper()

    if " GREY" in f" {desc} " or " GRAY" in f" {desc} ":
        return "GREY"
    if " BLACK" in f" {desc} ":
        return "BLACK"
    if " NM" in f" {desc} " or desc.endswith("NM"):
        return "NM"

    return "NM"


def extract_pattern(description: str) -> str:
    desc = clean(description).upper()
    tokens = desc.split()

    known_patterns = [
        "SM", "TR", "TRX", "LA", "XT", "XT+", "BB", "LGR", "AMS",
        "ROV", "SUP", "NOR", "EF", "OPT", "ULT"
    ]

    found = []
    for token in tokens:
        token_clean = token.strip().replace('"', "")
        if token_clean in known_patterns:
            found.append(token_clean)

    # Keep production-relevant pattern simple.
    for preferred in ["SM", "TR", "TRX", "LGR", "AMS", "ROV"]:
        if preferred in found:
            return preferred

    return found[0] if found else "GENERAL"


def make_group_key(description: str) -> tuple[str, str, str, str, str]:
    tyre_size = extract_tyre_size(description)
    pattern = extract_pattern(description)
    layer = extract_layer(description)
    color = extract_color(description)

    group_key = "|".join([
        tyre_size or "UNKNOWN_SIZE",
        pattern or "GENERAL",
        layer or "NM",
        color or "NM",
    ])

    return group_key, tyre_size, pattern, layer, color


with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tyre_process_groups (
            id BIGSERIAL PRIMARY KEY,
            group_key VARCHAR(255) NOT NULL UNIQUE,
            tyre_size VARCHAR(128) NOT NULL DEFAULT '',
            pattern VARCHAR(128) NOT NULL DEFAULT '',
            layer VARCHAR(64) NOT NULL DEFAULT '',
            color VARCHAR(64) NOT NULL DEFAULT '',
            normal_curing_minutes NUMERIC(12, 2) NOT NULL DEFAULT 0,
            short_cycle_curing_minutes NUMERIC(12, 2) NOT NULL DEFAULT 0,
            handling_minutes NUMERIC(12, 2) NOT NULL DEFAULT 0,
            preferred_line VARCHAR(255) NOT NULL DEFAULT '',
            remarks TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS tyre_process_group_items (
            id BIGSERIAL PRIMARY KEY,
            group_id BIGINT NOT NULL REFERENCES tyre_process_groups(id) ON DELETE CASCADE,
            sap_code VARCHAR(64) NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    conn.execute(text("""
        ALTER TABLE tyre_item_master
        ADD COLUMN IF NOT EXISTS process_group_key VARCHAR(255) NOT NULL DEFAULT ''
    """))

    # Clear generated mapping and regenerate from current tyre_item_master.
    conn.execute(text("DELETE FROM tyre_process_group_items"))
    conn.execute(text("DELETE FROM tyre_process_groups"))

    rows = conn.execute(text("""
        SELECT
            sap_code,
            description,
            normal_curing_minutes,
            short_cycle_curing_minutes,
            handling_minutes
        FROM tyre_item_master
        WHERE sap_code IS NOT NULL
          AND sap_code <> ''
        ORDER BY sap_code
    """)).mappings().all()

    group_cache = {}
    linked = 0

    for row in rows:
        sap_code = clean(row["sap_code"])
        description = clean(row["description"])

        if not sap_code or not description:
            continue

        group_key, tyre_size, pattern, layer, color = make_group_key(description)

        if group_key not in group_cache:
            result = conn.execute(
                text("""
                    INSERT INTO tyre_process_groups (
                        group_key,
                        tyre_size,
                        pattern,
                        layer,
                        color,
                        normal_curing_minutes,
                        short_cycle_curing_minutes,
                        handling_minutes,
                        updated_at
                    )
                    VALUES (
                        :group_key,
                        :tyre_size,
                        :pattern,
                        :layer,
                        :color,
                        :normal_curing_minutes,
                        :short_cycle_curing_minutes,
                        :handling_minutes,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING id
                """),
                {
                    "group_key": group_key,
                    "tyre_size": tyre_size,
                    "pattern": pattern,
                    "layer": layer,
                    "color": color,
                    "normal_curing_minutes": row["normal_curing_minutes"] or 0,
                    "short_cycle_curing_minutes": row["short_cycle_curing_minutes"] or 0,
                    "handling_minutes": row["handling_minutes"] or 0,
                },
            )

            group_cache[group_key] = result.scalar_one()

        group_id = group_cache[group_key]

        conn.execute(
            text("""
                INSERT INTO tyre_process_group_items (
                    group_id,
                    sap_code,
                    description
                )
                VALUES (
                    :group_id,
                    :sap_code,
                    :description
                )
                ON CONFLICT (sap_code) DO NOTHING
            """),
            {
                "group_id": group_id,
                "sap_code": sap_code,
                "description": description,
            },
        )

        conn.execute(
            text("""
                UPDATE tyre_item_master
                SET process_group_key = :group_key,
                    updated_at = CURRENT_TIMESTAMP
                WHERE sap_code = :sap_code
            """),
            {
                "group_key": group_key,
                "sap_code": sap_code,
            },
        )

        linked += 1

    summary = conn.execute(text("""
        SELECT
            COUNT(*) AS group_count,
            COALESCE(SUM(item_count), 0) AS item_count
        FROM (
            SELECT
                g.id,
                COUNT(i.id) AS item_count
            FROM tyre_process_groups g
            LEFT JOIN tyre_process_group_items i ON i.group_id = g.id
            GROUP BY g.id
        ) x
    """)).mappings().one()

    top_groups = conn.execute(text("""
        SELECT
            g.group_key,
            g.tyre_size,
            g.pattern,
            g.layer,
            g.color,
            g.normal_curing_minutes,
            g.handling_minutes,
            COUNT(i.id) AS sap_count
        FROM tyre_process_groups g
        LEFT JOIN tyre_process_group_items i ON i.group_id = g.id
        GROUP BY
            g.id,
            g.group_key,
            g.tyre_size,
            g.pattern,
            g.layer,
            g.color,
            g.normal_curing_minutes,
            g.handling_minutes
        ORDER BY COUNT(i.id) DESC, g.group_key
        LIMIT 30
    """)).mappings().all()

print("Tyre process groups created:", summary["group_count"])
print("SAP codes linked:", summary["item_count"])

print("")
print("Top grouped tyres:")
for row in top_groups:
    print(
        row["group_key"],
        "| SAP Count:", row["sap_count"],
        "| Normal:", row["normal_curing_minutes"],
        "| Handling:", row["handling_minutes"],
    )
