from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    if user is None:
        return None
    if user.password_hash != hash_password(password):
        return None
    return user
