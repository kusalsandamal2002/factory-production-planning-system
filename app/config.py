from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _portable_root() -> Path:
    configured = os.getenv("MPPS_PORTABLE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


BASE_DIR = _portable_root()
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv(
        "APP_NAME",
        "MPPS Factory Production Planning System",
    )
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://mpps_admin@127.0.0.1:55432/factory_planner",
    )
    project_root: Path = BASE_DIR
    data_sources_dir: Path = BASE_DIR / "data_sources"
    raw_historical_dir: Path = BASE_DIR / "data_sources" / "raw_historical"
    import_archive_dir: Path = BASE_DIR / "data_sources" / "import_archive"
    ml_workspace_dir: Path = BASE_DIR / "ml_workspace"
    models_dir: Path = BASE_DIR / "models"
    checkpoints_dir: Path = BASE_DIR / "models" / "checkpoints"
    reports_dir: Path = BASE_DIR / "reports"
    logs_dir: Path = BASE_DIR / "logs"
    backups_dir: Path = BASE_DIR / "backups"


settings = Settings()
