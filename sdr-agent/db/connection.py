"""
Async Postgres connection pool for the leads table.
Separate from the LangGraph psycopg2 checkpointer pool — this one is async-native.
"""
from __future__ import annotations
import os, structlog
import asyncpg

log = structlog.get_logger()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sdr:sdrpass@localhost:5432/sdrdb")

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the singleton asyncpg connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        # asyncpg wants postgresql:// not postgres://
        dsn = DATABASE_URL.replace("postgres://", "postgresql://")
        _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        log.info("db.pool_created")
    return _pool


async def create_tables() -> None:
    """Create the leads table and indexes if they don't already exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                lead_id         TEXT PRIMARY KEY,
                email           TEXT NOT NULL,
                name            TEXT,
                first_name      TEXT,
                last_name       TEXT,
                company         TEXT,
                domain          TEXT,
                title           TEXT,
                linkedin_url    TEXT,
                status          TEXT DEFAULT 'prospecting',
                fit_score       FLOAT DEFAULT 0,
                intent_score    FLOAT DEFAULT 0,
                final_score     FLOAT DEFAULT 0,
                channel         TEXT DEFAULT 'email',
                touch_number    INT DEFAULT 0,
                confidence      FLOAT DEFAULT 0,
                draft_subject   TEXT,
                draft_body      TEXT,
                reply_status    TEXT,
                meeting_booked  BOOLEAN DEFAULT FALSE,
                hitl_required   BOOLEAN DEFAULT TRUE,
                signals         JSONB DEFAULT '{}',
                firmographics   JSONB DEFAULT '{}',
                disqualification_reason TEXT,
                last_contacted_at TIMESTAMPTZ,
                scheduled_at    TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE UNIQUE INDEX IF NOT EXISTS leads_email_idx ON leads (email);
            CREATE INDEX IF NOT EXISTS leads_status_idx ON leads (status);
            
            ALTER TABLE leads ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ;
        """)
    
    from db.users import create_users_table
    await create_users_table()
    
    from db.workspace_config import create_workspace_config_table
    await create_workspace_config_table()
    
    log.info("db.tables_ready")
