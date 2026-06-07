from __future__ import annotations

import hashlib
from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Oven, ProductionRule, Role, Shift, TireType, User


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

    session.add_all(
        [
            Customer(customer_code=f"CUS-{i:03d}", customer_name=f"Customer {i:02d}", contact_person=f"Contact {i:02d}")
            for i in range(1, 11)
        ]
    )

    tire_data = [
        ("TYPE-01", "Tire Type 1", 30),
        ("TYPE-02", "Tire Type 2", 45),
        ("TYPE-03", "Tire Type 3", 90),
        ("TYPE-04", "Tire Type 4", 180),
        ("TYPE-05", "Tire Type 5", 300),
    ]
    session.add_all([TireType(tire_code=code, tire_name=name, curing_minutes=minutes) for code, name, minutes in tire_data])

    session.add_all([Oven(oven_code=f"OVEN-{i:02d}", oven_name=f"Oven {i:02d}") for i in range(1, 26)])

    session.add_all(
        [
            Shift(shift_name="Day Shift", start_time=time(8, 0), end_time=time(18, 0), max_working_minutes=600),
            Shift(shift_name="Night Shift", start_time=time(20, 0), end_time=time(4, 0), max_working_minutes=480),
        ]
    )

    session.add(ProductionRule(rule_name="BREAK_BETWEEN_TIRES", rule_value=20, unit="minutes"))
