# SDR Agent Runbook

**Project Purpose:** Autonomous SDR (Sales Development Representative) agent using LangGraph + Claude.

## Key Files
- `graph/state.py` (`SDRState` TypedDict)
- `graph/supervisor.py` (`StateGraph`)
- `graph/nodes/` (one file per agent node)

## Quick Start
1. Copy `.env.example` to `.env` and fill in API keys.
2. Run the environment:
   ```bash
   docker-compose up -d && uvicorn api.main:app --reload
   ```

## Usage
- **Trigger a Lead:** `POST` to `/webhook/lead` with JSON body.
- **Approve a Draft (HITL):** `POST` to `/hitl/approve` with `{"lead_id": "<id>", "approved": true}`.

## Observability
- **LangSmith Traces:** Set `LANGCHAIN_TRACING_V2=true` in `.env`.

## Coding Conventions
- Use `async` everywhere.
- Use `tenacity` for retries.
- Use `structlog` for structured logging.
- **No hardcoded keys** (use environment variables/settings).
