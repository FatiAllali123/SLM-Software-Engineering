"""POST /generate-tests."""
from fastapi import APIRouter, Request

from ..schemas import Envelope, TaskRequest
from ._common import handle_task

router = APIRouter()


@router.post("/generate-tests", response_model=Envelope, tags=["tasks"])
def generate_tests(body: TaskRequest, request: Request) -> Envelope:
    return handle_task("generate_tests", body, request)
