"""Tests des 4 portes : bon format, refus des mauvaises entrées, request_id."""
import pytest
from fastapi.testclient import TestClient

from Backend.app.main import app

client = TestClient(app, raise_server_exceptions=False)

TASK_ROUTES = [
    ("/analyze", "analyze", {"issues", "summary"}),
    ("/generate-tests", "generate_tests", {"tests", "test_count", "summary"}),
    ("/review", "review", {"findings", "verdict", "summary"}),
]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    """Les tests ne dépendent pas du code de B et D : on pointe vers des modules inexistants."""
    monkeypatch.setenv("LLM_MODULE", "inexistant_b.llm_client")
    monkeypatch.setenv("PIPELINE_MODULE", "inexistant_d.pipeline")
    monkeypatch.delenv("LLM_BACKEND", raising=False)


@pytest.mark.parametrize("path,task,keys", TASK_ROUTES)
def test_task_route_returns_contract_envelope(path, task, keys):
    r = client.post(path, json={"code": "def add(a, b):\n    return a + b"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["task"] == task
    assert body["error"] is None
    assert set(body["result"]) == keys
    m = body["metrics"]
    assert m["model"] == "stub"
    assert m["mode"] == "single_agent"
    assert m["llm_calls"] == 1


def test_multi_agent_mode_is_reported_in_metrics():
    r = client.post("/analyze", json={"code": "x = 1", "mode": "multi_agent"})
    assert r.json()["metrics"]["mode"] == "multi_agent"


def test_execute_returns_contract_envelope():
    r = client.post("/execute", json={"code": "print('bonjour')"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["task"] == "execute"
    assert body["metrics"] is None
    assert set(body["result"]) == {"stdout", "stderr", "exit_code", "timed_out", "duration_ms"}
    assert body["result"]["timed_out"] is False


def test_execute_does_not_run_the_code(tmp_path):
    marker = tmp_path / "ne_doit_pas_exister.txt"
    code = f"open(r'{marker}', 'w').write('x')"
    r = client.post("/execute", json={"code": code})
    assert r.status_code == 200
    assert not marker.exists()


@pytest.mark.parametrize("path", ["/analyze", "/generate-tests", "/review", "/execute"])
def test_unsupported_language_is_refused(path):
    r = client.post(path, json={"code": "x = 1", "language": "java"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_LANGUAGE"
    assert r.json()["status"] == "error"


@pytest.mark.parametrize("code", ["", "   \n\t "])
def test_empty_code_is_refused(code):
    r = client.post("/analyze", json={"code": code})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_code_too_large_is_refused():
    r = client.post("/analyze", json={"code": "a" * (50 * 1024 + 1)})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "CODE_TOO_LARGE"


def test_code_at_the_limit_is_accepted():
    r = client.post("/analyze", json={"code": "a" * (50 * 1024)})
    assert r.status_code == 200


def test_unknown_mode_is_refused():
    r = client.post("/analyze", json={"code": "x = 1", "mode": "many_agents"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_missing_code_field_is_refused():
    r = client.post("/review", json={"language": "python"})
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "code" in body["error"]["message"]
    assert body["task"] == "review"


def test_invalid_json_body_is_refused():
    r = client.post("/analyze", content="pas du json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("timeout", [0, -3, 11, 999])
def test_execute_bad_timeout_is_refused(timeout):
    r = client.post("/execute", json={"code": "x = 1", "timeout_s": timeout})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_INPUT"


def test_execute_timeout_at_maximum_is_accepted():
    r = client.post("/execute", json={"code": "x = 1", "timeout_s": 10})
    assert r.status_code == 200


def test_error_messages_never_repeat_what_the_user_sent():
    secret = "sk-FAUX-SECRET-1234567890"
    cases = [
        ("/analyze", {"code": secret, "language": secret}),
        ("/analyze", {"code": secret, "mode": secret}),
        ("/execute", {"code": secret, "timeout_s": secret}),
        ("/analyze", {"code": secret * 5000}),
    ]
    for path, payload in cases:
        r = client.post(path, json=payload)
        assert r.status_code >= 400
        assert secret not in r.text


def test_request_id_in_body_matches_header():
    r = client.post("/analyze", json={"code": "x = 1"})
    assert r.headers["X-Request-ID"] == r.json()["request_id"]


def test_request_id_is_present_on_errors_too():
    r = client.post("/analyze", json={"code": ""})
    assert r.headers["X-Request-ID"] == r.json()["request_id"]


def test_each_request_gets_a_different_request_id():
    ids = {client.post("/analyze", json={"code": "x = 1"}).json()["request_id"] for _ in range(5)}
    assert len(ids) == 5


def test_client_cannot_choose_the_request_id():
    r = client.post("/analyze", json={"code": "x = 1"}, headers={"X-Request-ID": "pirate"})
    assert r.json()["request_id"] != "pirate"
    assert r.headers["X-Request-ID"] != "pirate"
