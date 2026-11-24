"""Réglages communs à tous les tests."""
import pytest


@pytest.fixture(autouse=True)
def audit_db(tmp_path, monkeypatch):
    """Chaque test écrit dans son propre journal temporaire : le vrai journal n'est jamais touché."""
    path = tmp_path / "audit.db"
    monkeypatch.setenv("AUDIT_DB_PATH", str(path))
    return path
