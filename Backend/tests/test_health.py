from fastapi.testclient import TestClient

from Backend.app.main import app

client = TestClient(app)


def test_health_ok(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0"
    assert body["llm_backend"] == "stub"


def test_health_reads_llm_backend_from_env(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "real")
    assert client.get("/health").json()["llm_backend"] == "real"
