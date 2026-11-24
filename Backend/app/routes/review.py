"""POST /review."""
from fastapi import APIRouter, Request

from ..schemas import Envelope, TaskRequest
from ._common import handle_task

router = APIRouter()


@router.post("/review", response_model=Envelope, tags=["tasks"])
def review(body: TaskRequest, request: Request) -> Envelope:
    return handle_task("review", body, request)
