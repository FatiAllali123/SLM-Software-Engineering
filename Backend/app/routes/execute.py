"""POST /execute : exécuter du code dans le bac à sable (fictif pour l'instant)."""
from fastapi import APIRouter, Request

from ..audit import add_secret_stats, set_input
from ..config import get_settings
from ..request_id import request_id_of
from ..sandbox import run_code
from ..schemas import Envelope, ExecuteRequest, ok_envelope
from ..secret_filter import mask_secrets
from ..validation import validate_code, validate_timeout

router = APIRouter()


def _clean_output(text: str, max_chars: int) -> tuple:
    """Filtre les secrets PUIS tronque (dans cet ordre : couper d'abord pourrait laisser un morceau de secret)."""
    result = mask_secrets(text)
    return result.text[:max_chars], result.count


@router.post("/execute", response_model=Envelope, tags=["tasks"])
def execute(body: ExecuteRequest, request: Request) -> Envelope:
    settings = get_settings()
    # Le code exécuté n'est PAS modifié (le masquer changerait son comportement). Il ne va pas au modèle ;
    # seule son empreinte (calculée sur la version filtrée) est écrite dans le journal.
    too_large = len(body.code) > settings.max_code_bytes
    set_input(request, body.code if too_large else mask_secrets(body.code, settings).text)

    validate_code(body.code, body.language, settings)
    timeout_s = validate_timeout(body.timeout_s, settings)
    data = run_code(body.code, timeout_s).model_dump()

    # Filtre de SORTIE : stdout et stderr
    total = 0
    for stream in ("stdout", "stderr"):
        data[stream], n = _clean_output(data[stream], settings.max_output_chars)
        total += n
    add_secret_stats(request, masked_out=total)
    return ok_envelope("execute", data, metrics=None, request_id=request_id_of(request))
