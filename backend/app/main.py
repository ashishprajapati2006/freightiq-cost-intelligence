"""FreightIQ Production-Oriented FastAPI Application.

Assembles API routers, middlewares, custom exception handlers, and storage lifecycle.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root and backend directory are in sys.path
_current = Path(__file__).resolve()
for _parent in [_current.parents[2], _current.parents[1]]:  # root, backend
    _p_str = str(_parent)
    if _p_str not in sys.path:
        sys.path.insert(0, _p_str)

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.v1 import api_router
from backend.app.core.config import settings
from backend.app.core.exceptions import FreightIQException
from backend.app.core.logging import logger
from backend.app.core.middleware import RequestContextMiddleware
from backend.app.schemas.api import ErrorDetail, ErrorResponse
from backend.app.services.storage import storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    logger.info("Initializing FreightIQ API engine...")
    settings.ensure_directories()
    # Prime baseline run
    from backend.app.api.v1.dashboard import get_or_create_active_run_df
    get_or_create_active_run_df()
    logger.info("FreightIQ API engine initialized and ready to serve requests.")
    yield
    logger.info("Shutting down FreightIQ API engine.")


def create_application() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "FreightIQ — Production-Oriented FastAPI Backend for Smart Freight Cost Intelligence. "
            "Tracks work-weighted freight costs, trailing historical and peer baselines, "
            "deterministic anomaly detection, and anti-hallucination evidence validation."
        ),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # 1. Middlewares
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS if "*" not in settings.CORS_ORIGINS else ["*"],
        allow_origin_regex=settings.CORS_ORIGIN_REGEX,
        allow_credentials=True if "*" not in settings.CORS_ORIGINS else False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Exception Handlers
    @app.exception_handler(FreightIQException)
    async def freightiq_exception_handler(request: Request, exc: FreightIQException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        logger.warning(f"Domain error [{exc.error_code}]: {exc.message} (Request ID: {req_id})")
        payload = ErrorResponse(
            error=ErrorDetail(code=exc.error_code, message=exc.message, details=exc.details),
            request_id=req_id,
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        logger.warning(f"Request validation error (Request ID: {req_id}): {exc.errors()}")
        payload = ErrorResponse(
            error=ErrorDetail(
                code="UNPROCESSABLE_ENTITY",
                message="Invalid request payload or query parameters.",
                details=exc.errors(),
            ),
            request_id=req_id,
        )
        return JSONResponse(status_code=422, content=payload.model_dump())

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        payload = ErrorResponse(
            error=ErrorDetail(code="HTTP_ERROR", message=str(exc.detail)),
            request_id=req_id,
        )
        return JSONResponse(status_code=exc.status_code, content=payload.model_dump())

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", None)
        logger.error(f"Unhandled server exception (Request ID: {req_id}): {str(exc)}", exc_info=True)
        payload = ErrorResponse(
            error=ErrorDetail(code="INTERNAL_SERVER_ERROR", message="An unexpected server error occurred."),
            request_id=req_id,
        )
        return JSONResponse(status_code=500, content=payload.model_dump())

    # 3. Mount Routers
    app.include_router(api_router, prefix=settings.API_V1_STR)

    @app.get("/health", tags=["Health & Readiness"], summary="Root Health Check for Cloud Hosting")
    def health_check():
        """Lightweight root health check endpoint for cloud platforms (e.g., Render, Railway, AWS)."""
        return {
            "status": "healthy",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    @app.get("/", tags=["Root"])
    def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "operational",
            "docs": "/docs",
            "api_v1": settings.API_V1_STR,
        }

    return app


app = create_application()
