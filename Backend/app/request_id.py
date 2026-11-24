"""Numéro de suivi (request_id) attribué à chaque requête.

Il est généré par le serveur (jamais pris chez le client, pour éviter qu'on injecte
n'importe quoi dans les journaux). Il est écrit dans la réponse JSON et dans
l'en-tête HTTP X-Request-ID.
"""
from fastapi import Request

from .schemas import new_request_id

HEADER = "X-Request-ID"


async def request_id_middleware(request: Request, call_next):
    request.state.request_id = new_request_id()
    response = await call_next(request)
    response.headers[HEADER] = request.state.request_id
    return response


def request_id_of(request: Request) -> str:
    """Le request_id de la requête en cours (en crée un si le middleware n'a pas tourné)."""
    rid = getattr(request.state, "request_id", None)
    if rid is None:
        rid = new_request_id()
        request.state.request_id = rid
    return rid
