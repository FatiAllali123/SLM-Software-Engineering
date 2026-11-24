"""Tests des adaptateurs : branchement du code de B et D, et comportement en cas de panne."""
import sys
import types

import pytest
from fastapi.testclient import TestClient

from Backend.app.main import app

client = TestClient(app, raise_server_exceptions=False)
GOOD_CODE = {"code": "def add(a, b):\n    return a + b"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("LLM_MODULE", "faux_b.llm_client")
    monkeypatch.setenv("PIPELINE_MODULE", "faux_d.pipeline")
    monkeypatch.delenv("LLM_BACKEND", raising=False)


def install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


class FakeResponse:
    def __init__(self, model="faux-modele", precision="fp16"):
        self.text = "ok"
        self.input_tokens = 7
        self.output_tokens = 3
        self.latency_ms = 12
        self.model = model
        self.precision = precision


class FakeLLM:
    def generate(self, prompt, max_new_tokens=512, temperature=0.0):
        return FakeResponse()


def good_analyze_result():
    return {"issues": [], "summary": "rien à signaler"}


# ---------- Modèle (B) ----------
def test_stub_is_used_when_b_has_no_file_yet():
    body = client.post("/analyze", json=GOOD_CODE).json()
    assert body["status"] == "ok"
    assert body["metrics"]["model"] == "stub"
    assert body["metrics"]["precision"] == "none"


def test_real_backend_without_b_code_gives_model_error(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "real")
    r = client.post("/analyze", json=GOOD_CODE)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "MODEL_ERROR"


def test_b_client_is_used_when_present(monkeypatch):
    install_module(monkeypatch, "faux_b.llm_client", get_llm_client=lambda: FakeLLM())
    body = client.post("/analyze", json=GOOD_CODE).json()
    assert body["metrics"]["model"] == "faux-modele"
    assert body["metrics"]["precision"] == "fp16"


def test_broken_b_module_gives_model_error(monkeypatch):
    def boom():
        raise RuntimeError("secret interne : /home/b/token")
    install_module(monkeypatch, "faux_b.llm_client", get_llm_client=boom)
    r = client.post("/analyze", json=GOOD_CODE)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "MODEL_ERROR"
    assert "secret interne" not in r.text


def test_llm_failure_during_pipeline_gives_model_error(monkeypatch):
    class DeadLLM:
        def generate(self, prompt, max_new_tokens=512, temperature=0.0):
            raise TimeoutError("GPU injoignable")
    install_module(monkeypatch, "faux_b.llm_client", get_llm_client=lambda: DeadLLM())
    r = client.post("/analyze", json=GOOD_CODE)
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "MODEL_ERROR"
    assert "GPU" not in r.text


# ---------- Pipeline (D) ----------
def test_fake_pipeline_is_used_when_d_has_no_file_yet():
    body = client.post("/generate-tests", json=GOOD_CODE).json()
    assert body["status"] == "ok"
    assert body["result"]["test_count"] == 1


def test_d_pipeline_is_used_when_present(monkeypatch):
    calls = {}

    def run_pipeline(task, code, language, mode, llm):
        calls.update(task=task, code=code, language=language, mode=mode)
        response = llm.generate("bonjour")
        return {
            "result": good_analyze_result(),
            "metrics": {"input_tokens": 100, "output_tokens": 40, "latency_ms": 500, "llm_calls": 2},
            "trace": [{"agent": "analysis", "step": "analyze"}],
        }

    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=run_pipeline)
    body = client.post("/analyze", json={**GOOD_CODE, "mode": "multi_agent"}).json()
    assert calls == {"task": "analyze", "code": GOOD_CODE["code"], "language": "python", "mode": "multi_agent"}
    assert body["result"] == good_analyze_result()
    assert body["metrics"]["input_tokens"] == 100
    assert body["metrics"]["llm_calls"] == 2
    assert body["metrics"]["mode"] == "multi_agent"
    assert body["metrics"]["model"] == "stub"   # ajouté par le backend


def test_metrics_fall_back_to_measured_values_when_d_omits_them(monkeypatch):
    def run_pipeline(task, code, language, mode, llm):
        llm.generate("un deux trois")
        return {"result": good_analyze_result()}

    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=run_pipeline)
    m = client.post("/analyze", json=GOOD_CODE).json()["metrics"]
    assert m["llm_calls"] == 1
    assert m["input_tokens"] == 3


def test_invalid_pipeline_result_gives_internal_error(monkeypatch):
    def run_pipeline(task, code, language, mode, llm):
        return {"result": {"issues": "pas une liste"}}

    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=run_pipeline)
    r = client.post("/analyze", json=GOOD_CODE)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"


def test_pipeline_returning_garbage_gives_internal_error(monkeypatch):
    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=lambda **kw: "n'importe quoi")
    r = client.post("/review", json=GOOD_CODE)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"


def test_forbidden_tool_gives_blocked_403(monkeypatch):
    class ToolNotAllowedError(Exception):
        pass

    def run_pipeline(task, code, language, mode, llm):
        raise ToolNotAllowedError("rm_rf")

    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=run_pipeline)
    r = client.post("/analyze", json=GOOD_CODE)
    assert r.status_code == 403
    body = r.json()
    assert body["status"] == "blocked"
    assert body["error"]["code"] == "TOOL_NOT_ALLOWED"
    assert "rm_rf" not in r.text


def test_unexpected_pipeline_crash_gives_internal_error_without_details(monkeypatch):
    def run_pipeline(task, code, language, mode, llm):
        raise ValueError("chemin secret C:\\Users\\d\\cle.txt")

    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=run_pipeline)
    r = client.post("/analyze", json=GOOD_CODE)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in r.text
    assert r.headers["X-Request-ID"] == r.json()["request_id"]


def test_d_module_without_run_pipeline_gives_internal_error(monkeypatch):
    install_module(monkeypatch, "faux_d.pipeline")
    r = client.post("/analyze", json=GOOD_CODE)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"


def test_d_module_with_missing_dependency_is_not_hidden(monkeypatch):
    """Si le code de D plante à cause d'une bibliothèque manquante (ex. langgraph),
    on ne le cache pas derrière le faux pipeline : erreur claire."""
    import importlib
    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "faux_d.pipeline":
            raise ModuleNotFoundError("No module named 'langgraph'", name="langgraph")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("Backend.app.adapters.loader.importlib.import_module", fake_import)
    r = client.post("/analyze", json=GOOD_CODE)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "langgraph" not in r.text
