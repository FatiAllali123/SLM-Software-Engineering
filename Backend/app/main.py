"""Point d'entrée du serveur FastAPI.

Lancer : uvicorn Backend.app.main:app --port 8000   (depuis la racine du dépôt)
Documentation automatique : http://localhost:8000/docs
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import API_VERSION
from .errors import AppError
from .routes import health
from .schemas import error_envelope

logger = logging.getLogger("backend")

# Quelle "task" correspond à quelle porte (pour les enveloppes d'erreur)
TASK_BY_PATH = {
    "/analyze": "analyze",
    "/generate-tests": "generate_tests",
    "/review": "review",
    "/execute": "execute",
}

app = FastAPI(title="SLM Software Engineering - Backend", version=API_VERSION)
app.include_router(health.router)


def _task_for(request: Request) -> str:
    return TASK_BY_PATH.get(request.url.path, "analyze")


def _json(envelope, http_status: int) -> JSONResponse:
    return JSONResponse(status_code=http_status, content=envelope.model_dump(mode="json"))


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    envelope = error_envelope(_task_for(request), exc.code, exc.message, status=exc.status)
    return _json(envelope, exc.http_status)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    # On liste seulement les NOMS des champs fautifs (jamais leur valeur : elle pourrait contenir un secret)
    fields = sorted({".".join(str(p) for p in err["loc"][1:]) or "body" for err in exc.errors()})
    message = "Requête invalide. Champs concernés : " + ", ".join(fields)
    envelope = error_envelope(_task_for(request), "INVALID_INPUT", message)
    return _json(envelope, 400)


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    # Le détail technique va dans les logs du serveur, jamais chez l'utilisateur
    logger.exception("Erreur inattendue")
    envelope = error_envelope(_task_for(request), "INTERNAL_ERROR", "Erreur interne du serveur.")
    return _json(envelope, 500)
