"""POST /analyze."""
from fastapi import APIRouter, Request

from ..schemas import Envelope, TaskRequest
from ._common import handle_task

router = APIRouter()


@router.post("/analyze", response_model=Envelope, tags=["tasks"])
def analyze(body: TaskRequest, request: Request) -> Envelope:
    return handle_task("analyze", body, request)
