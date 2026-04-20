"""
FastAPI application entrypoint.
Initialises the LangGraph graph on startup and wires routers.
"""
from __future__ import annotations
import os, structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

from memory.pg_checkpointer import get_checkpointer
from graph.supervisor import build_graph
from api.auth import router as auth_router
from api.auth_middleware import JWTMiddleware
from api.scheduler import resume_scheduled_leads
from api.workspace import router as workspace_router
from api.webhook import router as webhook_router
from api.hitl import router as hitl_router
from api.leads import router as leads_router
from api.deps import set_graph, is_graph_ready
from db.connection import create_tables

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger()

# Graph state is now managed in api/deps.py to avoid circular imports.


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create DB tables, build LangGraph, start scheduler."""
    log.info("app.startup")
    await create_tables()
    checkpointer = get_checkpointer()
    graph = build_graph(checkpointer)
    set_graph(graph)

    # Start follow-up scheduler — fires every 15 minutes
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        resume_scheduled_leads,
        trigger="interval",
        minutes=15,
        args=[graph],
        id="follow_up_scheduler",
        replace_existing=True,
    )
    scheduler.start()
    log.info("app.scheduler_started")
    log.info("app.graph_ready")

    yield

    scheduler.shutdown(wait=False)
    log.info("app.shutdown")


app = FastAPI(
    title="SDR Agent API",
    version="0.1.0",
    description="Autonomous SDR pipeline — LangGraph + Claude",
    lifespan=lifespan,
)

# JWT middleware
app.add_middleware(JWTMiddleware)

# CORS middleware — added LAST so it is the outermost layer (handles preflight)
_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173,http://localhost:8080")
ALLOWED_ORIGINS = [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,      prefix="/auth",      tags=["auth"])
app.include_router(workspace_router, prefix="/workspace", tags=["workspace"])
app.include_router(webhook_router,   prefix="/webhook",   tags=["webhook"])
app.include_router(hitl_router,      prefix="/hitl",      tags=["hitl"])
app.include_router(leads_router,     prefix="/leads",     tags=["leads"])


@app.get("/health")
async def health():
    return {"status": "ok", "graph_ready": is_graph_ready()}