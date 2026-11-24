"""Point d'entrée du serveur FastAPI.

Lancer : python -m uvicorn Backend.app.main:app --port 8000   (depuis la racine du dépôt)
Documentation automatique : http://localhost:8000/docs
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .audit import audit_middleware, set_error
from .config import API_VERSION
from .errors import AppError
from .request_id import HEADER, request_id_middleware, request_id_of
from .routes import analyze, execute, generate_tests, health, review
from .schemas import error_envelope
from .tasks import TASK_BY_PATH

logger = logging.getLogger("backend")

app = FastAPI(title="SLM Software Engineering - Backend", version=API_VERSION)
# Le dernier middleware ajouté est le plus extérieur : request_id tourne AVANT l'audit
app.middleware("http")(audit_middleware)
app.middleware("http")(request_id_middleware)
for _module in (health, analyze, generate_tests, review, execute):
    app.include_router(_module.router)


def _task_for(request: Request) -> str:
    return TASK_BY_PATH.get(request.url.path, "analyze")


def _json(envelope, http_status: int) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content=envelope.model_dump(mode="json"),
        headers={HEADER: envelope.request_id},
    )


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    set_error(request, exc.code)
    envelope = error_envelope(_task_for(request), exc.code, exc.message,
                              status=exc.status, request_id=request_id_of(request))
    return _json(envelope, exc.http_status)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    set_error(request, "INVALID_INPUT")
    # On liste seulement les NOMS des champs fautifs (jamais leur valeur : elle pourrait contenir un secret)
    fields = sorted({".".join(str(p) for p in err["loc"][1:]) or "body" for err in exc.errors()})
    message = "Requête invalide. Champs concernés : " + ", ".join(fields)
    envelope = error_envelope(_task_for(request), "INVALID_INPUT", message,
                              request_id=request_id_of(request))
    return _json(envelope, 400)


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    # Le détail technique va dans les logs du serveur, jamais chez l'utilisateur
    logger.exception("Erreur inattendue")
    envelope = error_envelope(_task_for(request), "INTERNAL_ERROR", "Erreur interne du serveur.",
                              request_id=request_id_of(request))
    return _json(envelope, 500)
