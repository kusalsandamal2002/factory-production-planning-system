from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath


ROOT = Path(
    os.getenv("MPPS_PORTABLE_ROOT")
    or Path(__file__).resolve().parent.parent
).resolve()


def portable_root() -> Path:
    return ROOT


def resolve_portable_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None

    path = Path(str(value))

    if path.is_absolute() and path.exists():
        return path

    if not path.is_absolute():
        return (ROOT / path).resolve()

    try:
        name = PureWindowsPath(str(value)).name
    except Exception:
        name = path.name

    for base in (
        ROOT / "data_sources" / "import_archive",
        ROOT / "data_sources" / "raw_historical",
        ROOT / "models",
        ROOT / "ml_workspace",
    ):
        candidate = base / name
        if candidate.exists():
            return candidate

    return path


def relative_to_root(path: str | Path) -> str:
    candidate = Path(path).resolve()
    try:
        return str(candidate.relative_to(ROOT))
    except Exception:
        return str(candidate)
