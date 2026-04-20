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

load_dotenv()

from memory.pg_checkpointer import get_checkpointer
from graph.supervisor import build_graph
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
    """Startup: create DB tables, build LangGraph. Shutdown: nothing to clean up."""
    log.info("app.startup")
    await create_tables()
    checkpointer = get_checkpointer()
    graph = build_graph(checkpointer)
    set_graph(graph)
    log.info("app.graph_ready")
    yield
    log.info("app.shutdown")


app = FastAPI(
    title="SDR Agent API",
    version="0.1.0",
    description="Autonomous SDR pipeline — LangGraph + Claude",
    lifespan=lifespan,
)

# Allow the Vite dev server (5173) and preview (4173).
# Override via ALLOWED_ORIGINS env var for production.
_origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173")
ALLOWED_ORIGINS = [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router, prefix="/webhook", tags=["webhook"])
app.include_router(hitl_router,    prefix="/hitl",    tags=["hitl"])
app.include_router(leads_router,   prefix="/leads",   tags=["leads"])


@app.get("/health")
async def health():
    return {"status": "ok", "graph_ready": is_graph_ready()}
