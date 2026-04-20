"""
Workspace configuration API.
GET  /workspace/icp       → returns current ICP config
POST /workspace/icp       → saves ICP config
GET  /workspace/sequences → returns current sequence config
POST /workspace/sequences → saves sequence config
"""
from __future__ import annotations
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from db.workspace_config import (
    get_icp_config, save_icp_config,
    get_sequences_config, save_sequences_config,
)

log = structlog.get_logger()
router = APIRouter()


def _get_workspace_id(request: Request) -> str:
    workspace_id = getattr(request.state, "workspace_id", None)
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return workspace_id


# ── ICP Config ──────────────────────────────────────────────────────

@router.get("/icp")
async def get_icp(request: Request):
    workspace_id = _get_workspace_id(request)
    config = await get_icp_config(workspace_id)
    return {"config": config, "workspace_id": workspace_id}


@router.post("/icp")
async def save_icp(request: Request):
    workspace_id = _get_workspace_id(request)
    body = await request.json()
    config = body.get("config", body)  # Accept both {config: {...}} and {...}

    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config must be a JSON object")

    await save_icp_config(workspace_id, config)
    log.info("api.icp_saved", workspace_id=workspace_id)
    return {"status": "saved", "workspace_id": workspace_id}


# ── Sequences Config ────────────────────────────────────────────────

@router.get("/sequences")
async def get_sequences(request: Request):
    workspace_id = _get_workspace_id(request)
    config = await get_sequences_config(workspace_id)
    return {"config": config, "workspace_id": workspace_id}


@router.post("/sequences")
async def save_sequences(request: Request):
    workspace_id = _get_workspace_id(request)
    body = await request.json()
    config = body.get("config", body)

    if not isinstance(config, dict):
        raise HTTPException(status_code=422, detail="config must be a JSON object")

    await save_sequences_config(workspace_id, config)
    log.info("api.sequences_saved", workspace_id=workspace_id)
    return {"status": "saved", "workspace_id": workspace_id}
