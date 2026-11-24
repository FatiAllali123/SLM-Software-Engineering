"""POST /execute : exécuter du code dans le bac à sable (fictif pour l'instant)."""
from fastapi import APIRouter, Request

from ..audit import set_input
from ..config import get_settings
from ..request_id import request_id_of
from ..sandbox import run_code
from ..schemas import Envelope, ExecuteRequest, ok_envelope
from ..validation import validate_code, validate_timeout

router = APIRouter()


@router.post("/execute", response_model=Envelope, tags=["tasks"])
def execute(body: ExecuteRequest, request: Request) -> Envelope:
    settings = get_settings()
    set_input(request, body.code)
    validate_code(body.code, body.language, settings)
    timeout_s = validate_timeout(body.timeout_s, settings)
    result = run_code(body.code, timeout_s)
    return ok_envelope("execute", result, metrics=None, request_id=request_id_of(request))
