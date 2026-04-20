"""
Per-workspace configuration storage.
Stores ICP criteria and sequence settings in Postgres.
Falls back to YAML file defaults if no DB config exists yet.
"""
from __future__ import annotations
import json, yaml, structlog
from pathlib import Path
from db.connection import get_pool

log = structlog.get_logger()

_ICP_DEFAULT_PATH = Path(__file__).parent.parent / "config" / "icp.yaml"
_SEQ_DEFAULT_PATH = Path(__file__).parent.parent / "config" / "sequences.yaml"


async def create_workspace_config_table() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS workspace_config (
                workspace_id    TEXT NOT NULL,
                config_type     TEXT NOT NULL,
                config_data     JSONB NOT NULL,
                updated_at      TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (workspace_id, config_type)
            );
        """)
    log.info("db.workspace_config_table_ready")


async def get_icp_config(workspace_id: str) -> dict:
    """Return ICP config for a workspace. Falls back to YAML defaults."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT config_data FROM workspace_config WHERE workspace_id=$1 AND config_type='icp'",
            workspace_id
        )
    if row:
        data = row["config_data"]
        return json.loads(data) if isinstance(data, str) else data

    # Fall back to YAML defaults
    with open(_ICP_DEFAULT_PATH) as f:
        return yaml.safe_load(f)


async def save_icp_config(workspace_id: str, config: dict) -> None:
    """Upsert ICP config for a workspace."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO workspace_config (workspace_id, config_type, config_data, updated_at)
            VALUES ($1, 'icp', $2, NOW())
            ON CONFLICT (workspace_id, config_type) DO UPDATE
            SET config_data = EXCLUDED.config_data, updated_at = NOW()
        """, workspace_id, json.dumps(config))
    log.info("db.icp_config_saved", workspace_id=workspace_id)


async def get_sequences_config(workspace_id: str) -> dict:
    """Return sequences config for a workspace. Falls back to YAML defaults."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT config_data FROM workspace_config WHERE workspace_id=$1 AND config_type='sequences'",
            workspace_id
        )
    if row:
        data = row["config_data"]
        return json.loads(data) if isinstance(data, str) else data

    with open(_SEQ_DEFAULT_PATH) as f:
        return yaml.safe_load(f)


async def save_sequences_config(workspace_id: str, config: dict) -> None:
    """Upsert sequences config for a workspace."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO workspace_config (workspace_id, config_type, config_data, updated_at)
            VALUES ($1, 'sequences', $2, NOW())
            ON CONFLICT (workspace_id, config_type) DO UPDATE
            SET config_data = EXCLUDED.config_data, updated_at = NOW()
        """, workspace_id, json.dumps(config))
    log.info("db.sequences_config_saved", workspace_id=workspace_id)
