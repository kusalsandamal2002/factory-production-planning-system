from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, User


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def seed_database(session: Session) -> None:
    if session.scalar(select(Role).limit(1)):
        return

    roles = [Role(role_name="Admin"), Role(role_name="Operation Manager"), Role(role_name="Owner / Viewer")]
    session.add_all(roles)
    session.flush()

    session.add_all(
        [
            User(
                full_name="System Administrator",
                username="admin",
                password_hash=hash_password("admin123"),
                role_id=roles[0].id,
            ),
            User(
                full_name="Operation Manager",
                username="manager",
                password_hash=hash_password("manager123"),
                role_id=roles[1].id,
            ),
            User(
                full_name="Company Owner",
                username="owner",
                password_hash=hash_password("owner123"),
                role_id=roles[2].id,
            ),
        ]
    )
