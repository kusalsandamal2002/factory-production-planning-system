import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Factory Oven Production Planning System")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://factory_user:factory_pass@localhost:5432/factory_planner",
    )


settings = Settings()
