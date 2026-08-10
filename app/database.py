from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


_CPU_COUNT = max(1, int(os.cpu_count() or 1))
_DB_POOL_SIZE = min(16, max(6, _CPU_COUNT))

engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=_DB_POOL_SIZE,
    max_overflow=_DB_POOL_SIZE,
    pool_timeout=20,
    pool_recycle=1800,
    pool_use_lifo=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)