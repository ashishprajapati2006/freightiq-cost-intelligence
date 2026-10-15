"""Natural language AI query endpoint with verifiable grounded responses."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.assistant import AssistantQueryRequest, AssistantQueryResponse
from backend.app.services.assistant import assistant_service
from backend.app.services.storage import storage

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


@router.post("/query", response_model=AssistantQueryResponse, summary="Grounded Query to Assistant")
def query_assistant(request: AssistantQueryRequest) -> AssistantQueryResponse:
    """Ask a question about freight trends, anomalies, or evidence notes without hallucination."""
    from backend.app.api.v1.dashboard import get_or_create_active_run_df
    df, meta = get_or_create_active_run_df()
    _, notes, _ = storage.get_dataset(meta["dataset_id"])

    return assistant_service.query(request, df, notes)
