import pytest
from pydantic import ValidationError

from Backend.app.schemas import AnalyzeResult, TaskRequest, error_envelope, ok_envelope


def test_task_request_defaults():
    req = TaskRequest(code="print(1)")
    assert req.language == "python"
    assert req.mode == "single_agent"


def test_task_request_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        TaskRequest(code="x", mode="many_agents")


def test_error_envelope_shape():
    data = error_envelope("analyze", "CODE_TOO_LARGE", "Le code dépasse 50 Ko.").model_dump(mode="json")
    assert data["status"] == "error"
    assert data["result"] is None
    assert data["metrics"] is None
    assert data["error"]["code"] == "CODE_TOO_LARGE"


def test_ok_envelope_wraps_result():
    env = ok_envelope("analyze", AnalyzeResult(summary="ok"))
    assert env.status == "ok"
    assert env.result == {"issues": [], "summary": "ok"}
    assert env.error is None
