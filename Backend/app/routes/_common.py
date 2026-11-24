"""Logique commune aux portes /analyze, /generate-tests et /review."""
from fastapi import Request

from ..adapters.llm import get_llm
from ..adapters.pipeline import run_task
from ..config import get_settings
from ..request_id import request_id_of
from ..schemas import Envelope, TaskRequest, ok_envelope
from ..validation import validate_code


def handle_task(task: str, body: TaskRequest, request: Request) -> Envelope:
    validate_code(body.code, body.language, get_settings())
    outcome = run_task(task, body.code, body.language, body.mode, get_llm())
    return ok_envelope(task, outcome.result, outcome.metrics, request_id=request_id_of(request))
