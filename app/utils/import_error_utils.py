from __future__ import annotations


def extract_task_error_reason(details: str) -> str:
    """Return the useful DB/runtime reason instead of SQLAlchemy's help URL."""
    lines = [line.strip() for line in str(details or "").splitlines() if line.strip()]
    if not lines:
        return "Unknown import error"

    ignored_prefixes = (
        "Background on this error:",
        "(Background on this error",
        "[SQL:",
        "[parameters:",
        "Traceback (most recent call last):",
    )
    candidates: list[str] = []
    for line in lines:
        if line.startswith(ignored_prefixes):
            continue
        if "sqlalche.me/e/" in line:
            continue
        if line.startswith("File ") or line.startswith("^"):
            continue
        candidates.append(line)

    priority_markers = (
        "duplicate key value violates unique constraint",
        "violates not-null constraint",
        "violates check constraint",
        "violates foreign key constraint",
        "IntegrityError",
        "UniqueViolation",
        "NotNullViolation",
        "CheckViolation",
        "ForeignKeyViolation",
        "DETAIL:",
    )
    for marker in priority_markers:
        for line in reversed(candidates):
            if marker.lower() in line.lower():
                return line

    return candidates[-1] if candidates else lines[-1]
