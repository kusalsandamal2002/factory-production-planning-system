from __future__ import annotations

import re
import unicodedata
from typing import Any


_SPACE_RE = re.compile(r"\s+")
_HYPHEN_SPACE_RE = re.compile(r"\s*-\s*")
_SLASH_SPACE_RE = re.compile(r"\s*/\s*")
_X_BETWEEN_DIGITS_RE = re.compile(
    r"(?<=\d)\s*[xX×✕]\s*(?=\d)"
)

_DASH_TRANSLATION = str.maketrans(
    {
        "‐": "-",
        "‑": "-",
        "‒": "-",
        "–": "-",
        "—": "-",
        "−": "-",
        "﹘": "-",
        "﹣": "-",
        "－": "-",
        "×": "X",
        "✕": "X",
    }
)

_UNKNOWN_VALUES = {
    "",
    "-",
    "--",
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "UNKNOWN",
    "NOT AVAILABLE",
}

_NO_CASING_IDENTITIES = {
    "NO CASING",
    "NOCASING",
    "WITHOUT CASING",
    "WITHOUT TYRE CASING",
    "NOT REQUIRED",
    "NONE",
    "N/A",
    "NA",
}


def clean_text(value: Any) -> str:
    """Return display-safe text with Unicode and whitespace normalized."""
    text_value = unicodedata.normalize(
        "NFKC",
        str(value or ""),
    )
    text_value = text_value.translate(
        _DASH_TRANSLATION
    )
    text_value = text_value.replace(
        "\u00a0",
        " ",
    )
    return _SPACE_RE.sub(
        " ",
        text_value.strip(),
    )


def identifier_key(value: Any) -> str:
    """Return a stable comparison key for master-data identifiers."""
    text_value = clean_text(value)
    text_value = _X_BETWEEN_DIGITS_RE.sub(
        "X",
        text_value,
    )
    text_value = _HYPHEN_SPACE_RE.sub(
        "-",
        text_value,
    )
    text_value = _SLASH_SPACE_RE.sub(
        "/",
        text_value,
    )
    return text_value.upper()


def normalize_sap_code(value: Any) -> str:
    return identifier_key(value)


def normalize_mold_key(
    value: Any,
    *,
    unknown_value: str = "-",
) -> str:
    key = identifier_key(value)
    if key in _UNKNOWN_VALUES:
        return unknown_value
    return key


def normalize_casing_type(
    value: Any,
    *,
    unknown_value: str = "-",
) -> str:
    display = clean_text(value)
    key = identifier_key(display)

    compact_key = re.sub(
        r"[^A-Z0-9]+",
        "",
        key,
    )
    no_casing_compact = {
        re.sub(r"[^A-Z0-9]+", "", item)
        for item in _NO_CASING_IDENTITIES
    }

    if (
        key in _NO_CASING_IDENTITIES
        or compact_key in no_casing_compact
    ):
        return "No Casing"

    if key in _UNKNOWN_VALUES:
        return unknown_value

    return display


def line_identity(value: Any) -> str:
    return " ".join(
        re.sub(
            r"[^A-Z0-9]+",
            " ",
            identifier_key(value),
        ).split()
    )


def normalize_line_name(
    value: Any,
    *,
    unknown_value: str = "",
) -> str:
    display = clean_text(value)
    if identifier_key(display) in _UNKNOWN_VALUES:
        return unknown_value
    return display


def resource_key(
    resource_type: Any,
    value: Any,
) -> str:
    resource = clean_text(
        resource_type
    ).lower()

    if resource == "mold":
        return normalize_mold_key(value)

    if resource == "casing":
        return normalize_casing_type(value)

    if resource in {
        "line",
        "line_cavity",
        "production_line",
    }:
        return normalize_line_name(value)

    return clean_text(value)


def resource_identity(
    resource_type: Any,
    value: Any,
) -> str:
    resource = clean_text(
        resource_type
    ).lower()
    canonical = resource_key(
        resource_type,
        value,
    )

    if resource in {
        "line",
        "line_cavity",
        "production_line",
    }:
        return line_identity(canonical)

    return identifier_key(canonical)


def is_no_casing(value: Any) -> bool:
    return (
        normalize_casing_type(value)
        == "No Casing"
    )


__all__ = [
    "clean_text",
    "identifier_key",
    "is_no_casing",
    "line_identity",
    "normalize_casing_type",
    "normalize_line_name",
    "normalize_mold_key",
    "normalize_sap_code",
    "resource_identity",
    "resource_key",
]
