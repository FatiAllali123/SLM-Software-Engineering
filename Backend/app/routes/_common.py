"""Logique commune aux portes /analyze, /generate-tests et /review."""
from fastapi import Request

from ..adapters.llm import get_llm
from ..adapters.pipeline import run_task
from ..audit import add_secret_stats, set_input
from ..config import get_settings
from ..request_id import request_id_of
from ..schemas import Envelope, TaskRequest, ok_envelope
from ..secret_filter import mask_json, mask_secrets
from ..validation import validate_code


def handle_task(task: str, body: TaskRequest, request: Request) -> Envelope:
    settings = get_settings()

    # 1) Filtre d'ENTRÉE : le modèle et les agents ne voient jamais les secrets.
    #    (Un code déjà trop gros n'est pas filtré : il sera refusé juste après.)
    too_large = len(body.code) > settings.max_code_bytes
    masked = None if too_large else mask_secrets(body.code, settings)
    code_for_agents = body.code if masked is None else masked.text
    # L'empreinte du journal est calculée sur le texte filtré (on ne peut pas retrouver un secret à partir d'elle).
    set_input(request, code_for_agents)
    if masked is not None:
        add_secret_stats(request, masked_in=masked.count, suspects=masked.suspects)

    validate_code(body.code, body.language, settings)
    outcome = run_task(task, code_for_agents, body.language, body.mode, get_llm())

    # 2) Filtre de SORTIE : rien de secret ne part vers le client.
    result, masked_out = mask_json(outcome.result, settings)
    add_secret_stats(request, masked_out=masked_out)
    return ok_envelope(task, result, outcome.metrics, request_id=request_id_of(request))
