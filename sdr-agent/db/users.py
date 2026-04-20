"""
Users table — stores accounts and workspace associations.
Each user owns exactly one workspace_id (for future multi-tenancy).
"""
from __future__ import annotations
import uuid, structlog
from db.connection import get_pool

log = structlog.get_logger()


async def create_users_table() -> None:
    """Create the users table if it doesn't already exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email           TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                workspace_id    UUID NOT NULL DEFAULT gen_random_uuid(),
                full_name       TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS users_email_idx ON users (email);
        """)
    log.info("db.users_table_ready")


async def create_user(email: str, hashed_password: str, full_name: str = "") -> dict:
    """Insert a new user. Raises asyncpg.UniqueViolationError if email exists."""
    pool = await get_pool()
    workspace_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (email, hashed_password, workspace_id, full_name)
            VALUES ($1, $2, $3, $4)
            RETURNING id, email, workspace_id, full_name, created_at
            """,
            email, hashed_password, workspace_id, full_name
        )
    return dict(row)


async def get_user_by_email(email: str) -> dict | None:
    """Fetch a user by email address."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, hashed_password, workspace_id, full_name FROM users WHERE email = $1",
            email
        )
    return dict(row) if row else None
