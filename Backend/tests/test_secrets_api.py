"""Le filtre de secrets branché sur l'API : entrée, sortie, journal d'audit.

Tous les secrets sont FAUX et fabriqués à l'exécution (voir test_secret_filter.py).
"""
import hashlib
import sys
import types

import pytest
from fastapi.testclient import TestClient

from Backend.app import audit
from Backend.app.main import app
from Backend.app.schemas import ExecuteResult
from Backend.app.secret_filter import MASK

client = TestClient(app, raise_server_exceptions=False)

FAKE_KEY = "sk" + "-" + "Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7"
CODE_WITH_SECRET = f'API_KEY = "{FAKE_KEY}"\nprint("bonjour")\n'
CODE_MASKED = f'API_KEY = "{MASK}"\nprint("bonjour")\n'


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


def last_row(db):
    return audit.read_recent(1, db_path=db)[0]


# ---------- ENTRÉE : le modèle et les agents ne voient jamais le secret ----------
@pytest.mark.parametrize("path", ["/analyze", "/generate-tests", "/review"])
def test_secret_is_masked_before_reaching_the_agents(monkeypatch, path):
    seen = {}

    def run_pipeline(task, code, language, mode, llm):
        seen["code"] = code
        return {"result": {"issues": [], "summary": "ok"} if task == "analyze" else
                {"tests": "pass", "test_count": 0, "summary": "ok"} if task == "generate_tests" else
                {"findings": [], "verdict": "approve", "summary": "ok"}}

    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=run_pipeline)
    r = client.post(path, json={"code": CODE_WITH_SECRET})
    assert r.status_code == 200                 # la requête n'est PAS refusée
    assert seen["code"] == CODE_MASKED
    assert FAKE_KEY not in r.text


def test_secret_is_masked_before_reaching_the_model(monkeypatch):
    prompts = []

    class SpyLLM:
        def generate(self, prompt, max_new_tokens=512, temperature=0.0):
            prompts.append(prompt)
            return types.SimpleNamespace(text="x", input_tokens=1, output_tokens=1,
                                         latency_ms=1, model="spy", precision="fp16")

    install_module(monkeypatch, "faux_b.llm_client", get_llm_client=lambda: SpyLLM())
    assert client.post("/analyze", json={"code": CODE_WITH_SECRET}).status_code == 200
    assert prompts and all(FAKE_KEY not in p for p in prompts)
    assert MASK in prompts[0]


def test_masking_does_not_change_the_validation_rules():
    r = client.post("/analyze", json={"code": CODE_WITH_SECRET, "language": "java"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_LANGUAGE"


def test_oversized_code_is_refused_without_being_filtered():
    r = client.post("/analyze", json={"code": "a" * (50 * 1024 + 1)})
    assert r.status_code == 413


# ---------- SORTIE : rien de secret ne part vers le client ----------
def test_secret_in_agent_output_is_masked(monkeypatch):
    def run_pipeline(task, code, language, mode, llm):
        return {"result": {
            "issues": [{"line": 1, "severity": "high", "category": "vulnerability",
                        "message": f"Clé en dur : {FAKE_KEY}"}],
            "summary": f'password = "hunter2hunter2" trouvé'}}

    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=run_pipeline)
    r = client.post("/analyze", json={"code": "x = 1"})
    assert r.status_code == 200
    assert FAKE_KEY not in r.text and "hunter2hunter2" not in r.text
    assert MASK in r.json()["result"]["issues"][0]["message"]
    assert r.json()["result"]["issues"][0]["line"] == 1       # le reste du résultat est intact


def test_secret_in_execute_output_is_masked(monkeypatch):
    fake = ExecuteResult(stdout=f"cle={FAKE_KEY}\nbonjour\n", stderr='DB_PASSWORD="hunter2hunter2"',
                         exit_code=0, timed_out=False, duration_ms=5)
    monkeypatch.setattr("Backend.app.routes.execute.run_code", lambda code, timeout_s: fake)
    r = client.post("/execute", json={"code": "print(1)"})
    body = r.json()
    assert FAKE_KEY not in r.text and "hunter2hunter2" not in r.text
    assert "bonjour" in body["result"]["stdout"]
    assert body["result"]["exit_code"] == 0


def test_execute_output_is_truncated_to_10000_characters(monkeypatch):
    fake = ExecuteResult(stdout="x" * 30_000, stderr="e" * 10_001, exit_code=0, timed_out=False, duration_ms=1)
    monkeypatch.setattr("Backend.app.routes.execute.run_code", lambda code, timeout_s: fake)
    result = client.post("/execute", json={"code": "print(1)"}).json()["result"]
    assert len(result["stdout"]) == 10_000
    assert len(result["stderr"]) == 10_000


def test_secret_at_the_truncation_boundary_is_not_half_revealed(monkeypatch):
    # le filtre passe AVANT la coupure : un secret à cheval sur la limite ne laisse aucun morceau
    stdout = "x" * 9_989 + " " + FAKE_KEY      # le secret commence à la position 9 990 : la coupure tombe en plein milieu
    fake = ExecuteResult(stdout=stdout, stderr="", exit_code=0, timed_out=False, duration_ms=1)
    monkeypatch.setattr("Backend.app.routes.execute.run_code", lambda code, timeout_s: fake)
    out = client.post("/execute", json={"code": "print(1)"}).json()["result"]["stdout"]
    assert "Ab3dE6" not in out and "sk-" not in out


def test_executed_code_is_not_modified(monkeypatch):
    received = {}

    def spy(code, timeout_s):
        received["code"] = code
        return ExecuteResult(stdout="", stderr="", exit_code=0, timed_out=False, duration_ms=0)

    monkeypatch.setattr("Backend.app.routes.execute.run_code", spy)
    client.post("/execute", json={"code": CODE_WITH_SECRET})
    assert received["code"] == CODE_WITH_SECRET     # masquer changerait le comportement du programme


# ---------- JOURNAL D'AUDIT ----------
def test_audit_notes_that_a_secret_was_masked_on_input(audit_db):
    client.post("/analyze", json={"code": CODE_WITH_SECRET})
    row = last_row(audit_db)
    assert row["decision"] == "allowed"
    assert row["reason"] == "ok;secrets_masked=in:1,out:0"


def test_audit_notes_masked_secrets_on_output(audit_db, monkeypatch):
    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=lambda **kw: {
        "result": {"issues": [], "summary": f"clé {FAKE_KEY}"}})
    client.post("/analyze", json={"code": "x = 1"})
    assert last_row(audit_db)["reason"] == "ok;secrets_masked=in:0,out:1"


def test_audit_reason_stays_ok_when_nothing_was_masked(audit_db):
    client.post("/analyze", json={"code": "x = 1"})
    assert last_row(audit_db)["reason"] == "ok"


def test_audit_reports_suspects_without_masking_them(audit_db):
    code = "image_ref = 'Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7ZzQq'\n"
    r = client.post("/analyze", json={"code": code})
    assert r.status_code == 200
    assert last_row(audit_db)["reason"] == "ok;suspects=1"


def test_audit_note_also_added_on_refused_calls_after_masking(audit_db):
    client.post("/analyze", json={"code": CODE_WITH_SECRET, "language": "java"})
    row = last_row(audit_db)
    assert row["reason"] == "UNSUPPORTED_LANGUAGE;secrets_masked=in:1,out:0"
    assert row["decision"] == "blocked"


def test_audit_never_contains_the_secret(audit_db):
    client.post("/analyze", json={"code": CODE_WITH_SECRET})
    client.post("/execute", json={"code": CODE_WITH_SECRET})
    client.post("/review", json={"code": CODE_WITH_SECRET, "language": "java"})
    assert FAKE_KEY.encode() not in audit_db.read_bytes()
    assert b"Ab3dE6gH9j" not in audit_db.read_bytes()


def test_audit_hash_is_computed_on_the_masked_code(audit_db):
    client.post("/analyze", json={"code": CODE_WITH_SECRET})
    assert last_row(audit_db)["input_hash"] == hashlib.sha256(CODE_MASKED.encode()).hexdigest()


def test_two_codes_differing_only_by_the_secret_share_the_same_hash(audit_db):
    other = "sk" + "-" + "Zz9yX8wV7uT6sR5qP4oN3mL2kJ1"
    client.post("/analyze", json={"code": CODE_WITH_SECRET})
    client.post("/analyze", json={"code": CODE_WITH_SECRET.replace(FAKE_KEY, other)})
    a, b = (r["input_hash"] for r in audit.read_recent(2, db_path=audit_db))
    assert a == b     # on ne peut donc pas deviner un secret en comparant des empreintes
