"""
JWT authentication middleware.
Validates Bearer tokens on protected routes.
Unprotected routes: /health, /auth/*, /docs, /openapi.json
"""
from __future__ import annotations
import os, structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-change-in-production")
ALGORITHM = "HS256"

# Routes that don't need a token
UNPROTECTED_PREFIXES = ("/auth/", "/health", "/docs", "/openapi.json", "/redoc")


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for public routes
        if any(path.startswith(p) for p in UNPROTECTED_PREFIXES):
            return await call_next(request)

        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"}
            )

        token = auth_header.removeprefix("Bearer ").strip()

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            # Attach user info to request state for use in route handlers
            request.state.user_id = payload.get("sub")
            request.state.workspace_id = payload.get("workspace_id")
        except JWTError as e:
            log.warning("auth.invalid_token", error=str(e))
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

        return await call_next(request)
