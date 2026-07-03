import os
import hashlib
from sqlalchemy import text
from app.database import engine


def make_password_hash(password: str) -> str:
    iterations = 260000
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


password_hash = make_password_hash("admin")

with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS app_auth_users (
            id BIGSERIAL PRIMARY KEY,
            username VARCHAR(128) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL DEFAULT '',
            display_name VARCHAR(255) NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role_name VARCHAR(80) NOT NULL DEFAULT 'Operation Manager',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    conn.execute(
        text("""
            INSERT INTO app_auth_users (
                username,
                email,
                display_name,
                password_hash,
                role_name,
                is_active
            )
            VALUES (
                'admin',
                'admin@factory.local',
                'Operation Manager',
                :password_hash,
                'System Administrator',
                TRUE
            )
            ON CONFLICT (username)
            DO UPDATE SET
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                password_hash = EXCLUDED.password_hash,
                role_name = EXCLUDED.role_name,
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP
        """),
        {"password_hash": password_hash},
    )

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT username, display_name, role_name, is_active
        FROM app_auth_users
        ORDER BY username
    """)).all()

print("DB login users:")
for row in rows:
    print(row.username, "|", row.display_name, "|", row.role_name, "| active:", row.is_active)

print("")
print("Login ready:")
print("Username: admin")
print("Password: admin")
