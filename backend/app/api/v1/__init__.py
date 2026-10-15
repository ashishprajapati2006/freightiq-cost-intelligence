"""Central API Router bundling all v1 route handlers."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1 import (
    analysis,
    anomalies,
    assistant,
    dashboard,
    datasets,
    evaluation,
    exports,
    health,
    ml,
    notes,
    shipments,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(datasets.router)
api_router.include_router(exports.router)
api_router.include_router(analysis.router)
api_router.include_router(dashboard.router)
api_router.include_router(shipments.router)
api_router.include_router(anomalies.router)
api_router.include_router(notes.router)
api_router.include_router(assistant.router)
api_router.include_router(evaluation.router)
api_router.include_router(ml.router)
