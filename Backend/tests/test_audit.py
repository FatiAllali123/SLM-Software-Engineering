"""Tests du journal d'audit : une ligne par appel, même refusé, sans jamais stocker le code."""
import hashlib
import logging
import sqlite3
import sys
import types
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from Backend.app import audit
from Backend.app.main import app

client = TestClient(app, raise_server_exceptions=False)
GOOD = {"code": "def add(a, b):\n    return a + b"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("LLM_MODULE", "faux_b.llm_client")
    monkeypatch.setenv("PIPELINE_MODULE", "faux_d.pipeline")
    monkeypatch.delenv("LLM_BACKEND", raising=False)


def rows(db):
    return audit.read_recent(100, db_path=db)[::-1]   # du plus ancien au plus récent


def install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)


# ---------- Une ligne par appel ----------
def test_successful_call_is_logged(audit_db):
    r = client.post("/analyze", json=GOOD)
    (row,) = rows(audit_db)
    assert row["request_id"] == r.json()["request_id"]
    assert row["action"] == "analyze"
    assert row["decision"] == "allowed"
    assert row["reason"] == "ok"
    assert row["actor"] == "anonymous"
    assert row["input_hash"] == hashlib.sha256(GOOD["code"].encode()).hexdigest()
    assert isinstance(row["duration_ms"], int) and row["duration_ms"] >= 0


def test_timestamp_is_utc_iso(audit_db):
    client.post("/analyze", json=GOOD)
    stamp = rows(audit_db)[0]["timestamp"]
    parsed = datetime.fromisoformat(stamp)
    assert parsed.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("path,action", [
    ("/analyze", "analyze"), ("/generate-tests", "generate_tests"),
    ("/review", "review"), ("/execute", "execute"),
])
def test_each_door_is_logged_with_its_action(audit_db, path, action):
    client.post(path, json=GOOD)
    assert [r["action"] for r in rows(audit_db)] == [action]


def test_one_row_per_call(audit_db):
    for _ in range(3):
        client.post("/analyze", json=GOOD)
    assert len(rows(audit_db)) == 3


def test_health_is_not_logged(audit_db):
    client.get("/health")
    assert rows(audit_db) == []


# ---------- Les appels refusés sont aussi journalisés ----------
def test_unsupported_language_is_logged_as_blocked(audit_db):
    r = client.post("/analyze", json={**GOOD, "language": "java"})
    (row,) = rows(audit_db)
    assert row["decision"] == "blocked"
    assert row["reason"] == "UNSUPPORTED_LANGUAGE"
    assert row["request_id"] == r.json()["request_id"]
    assert row["input_hash"] is not None


def test_code_too_large_is_logged_as_blocked(audit_db):
    client.post("/review", json={"code": "a" * (50 * 1024 + 1)})
    (row,) = rows(audit_db)
    assert (row["decision"], row["reason"]) == ("blocked", "CODE_TOO_LARGE")


def test_invalid_request_is_logged_without_hash(audit_db):
    client.post("/analyze", json={"language": "python"})   # champ "code" manquant
    (row,) = rows(audit_db)
    assert (row["decision"], row["reason"]) == ("blocked", "INVALID_INPUT")
    assert row["input_hash"] is None


def test_bad_timeout_on_execute_is_logged(audit_db):
    client.post("/execute", json={"code": "x = 1", "timeout_s": 99})
    (row,) = rows(audit_db)
    assert (row["action"], row["decision"], row["reason"]) == ("execute", "blocked", "INVALID_INPUT")


def test_forbidden_tool_is_logged_as_blocked(audit_db, monkeypatch):
    class ToolNotAllowedError(Exception):
        pass

    def run_pipeline(**kwargs):
        raise ToolNotAllowedError("rm_rf")

    install_module(monkeypatch, "faux_d.pipeline", run_pipeline=run_pipeline)
    client.post("/analyze", json=GOOD)
    (row,) = rows(audit_db)
    assert (row["decision"], row["reason"]) == ("blocked", "TOOL_NOT_ALLOWED")


def test_model_failure_is_logged_as_error(audit_db, monkeypatch):
    class DeadLLM:
        def generate(self, *a, **k):
            raise TimeoutError("GPU injoignable")

    install_module(monkeypatch, "faux_b.llm_client", get_llm_client=lambda: DeadLLM())
    client.post("/analyze", json=GOOD)
    (row,) = rows(audit_db)
    assert (row["decision"], row["reason"]) == ("error", "MODEL_ERROR")


def test_unexpected_crash_is_logged_as_error(audit_db, monkeypatch):
    def boom(code, timeout_s):
        raise RuntimeError("panne imprévue")

    monkeypatch.setattr("Backend.app.routes.execute.run_code", boom)
    r = client.post("/execute", json=GOOD)
    assert r.status_code == 500
    (row,) = rows(audit_db)
    assert (row["decision"], row["reason"]) == ("error", "INTERNAL_ERROR")


# ---------- Sécurité du journal ----------
def test_the_code_itself_is_never_stored(audit_db):
    secret_code = "api_key = 'FAUX-SECRET-QUI-NE-DOIT-PAS-APPARAITRE-42'"
    client.post("/analyze", json={"code": secret_code})
    client.post("/analyze", json={"code": secret_code, "language": "java"})
    assert b"FAUX-SECRET" not in audit_db.read_bytes()
    for row in rows(audit_db):
        assert "FAUX-SECRET" not in str(row)


def test_same_code_gives_same_hash_and_different_code_a_different_one(audit_db):
    client.post("/analyze", json={"code": "x = 1"})
    client.post("/review", json={"code": "x = 1"})
    client.post("/analyze", json={"code": "x = 2"})
    a, b, c = (r["input_hash"] for r in rows(audit_db))
    assert a == b and a != c


def test_client_cannot_choose_the_actor(audit_db):
    client.post("/analyze", json=GOOD, headers={"X-Actor": "admin", "X-User": "admin"})
    assert rows(audit_db)[0]["actor"] == "anonymous"


def test_journal_is_append_only(audit_db):
    client.post("/analyze", json=GOOD)
    with sqlite3.connect(audit_db) as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE audit_log SET decision = 'allowed'")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_log")
    assert len(rows(audit_db)) == 1


def test_invalid_decision_value_is_refused_by_the_database(audit_db):
    client.post("/analyze", json=GOOD)
    with pytest.raises(sqlite3.IntegrityError):
        audit.record(request_id="x", action="analyze", input_hash=None,
                     decision="peut-etre", reason="test", duration_ms=0, db_path=audit_db)


# ---------- Robustesse ----------
def test_audit_failure_does_not_break_the_request(tmp_path, monkeypatch, caplog):
    fichier = tmp_path / "pas_un_dossier"
    fichier.write_text("je suis un fichier")
    monkeypatch.setenv("AUDIT_DB_PATH", str(fichier / "audit.db"))   # impossible à créer
    with caplog.at_level(logging.ERROR, logger="backend.audit"):
        r = client.post("/analyze", json=GOOD)
    assert r.status_code == 200
    assert "journal d'audit" in caplog.text


def test_read_recent_returns_newest_first(audit_db):
    client.post("/analyze", json=GOOD)
    client.post("/review", json=GOOD)
    assert [r["action"] for r in audit.read_recent(10, db_path=audit_db)] == ["review", "analyze"]


def test_read_recent_on_missing_file_returns_empty(tmp_path):
    assert audit.read_recent(10, db_path=tmp_path / "nexiste_pas.db") == []


# ---------- Correction : caractère Unicode invalide ----------
def test_invalid_unicode_is_refused_not_crashed(audit_db):
    r = client.post("/analyze", content=b'{"code": "\\ud800"}', headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_INPUT"
    (row,) = rows(audit_db)
    assert row["decision"] == "blocked"
