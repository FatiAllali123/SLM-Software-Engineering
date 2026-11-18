"""GET /health : vérifier que le serveur répond."""
from fastapi import APIRouter

from ..config import API_VERSION, get_settings
from ..schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", version=API_VERSION, llm_backend=settings.llm_backend)
