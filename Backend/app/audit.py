"""Journal d'audit (SQLite) : une ligne par appel d'une porte, MÊME REFUSÉ.

Règles de sécurité :
- On ne stocke JAMAIS le code de l'utilisateur, seulement son empreinte SHA-256.
- Le journal est en "ajout seulement" : des déclencheurs SQLite interdisent
  de modifier ou d'effacer une ligne (un fichier peut toujours être supprimé
  directement sur le disque : à signaler dans les limites du rapport).
- Qui appelle ? Il n'y a pas encore d'authentification : l'acteur vaut "anonymous"
  (on ne fait pas confiance à un en-tête envoyé par le client).
- Si l'écriture échoue, la requête n'est pas bloquée (la décision est déjà prise) :
  l'erreur est écrite dans les logs du serveur.

Secrets : si le filtre a masqué quelque chose, la colonne reason le note, par exemple
"ok;secrets_masked=in:1,out:0" (seulement des nombres : jamais le secret lui-même).

Décisions : allowed (accepté), blocked (refusé par une règle : entrée invalide ou
outil interdit), needs_approval (réservé, validation humaine), error (panne technique).

Voir les dernières lignes :  python -m Backend.app.audit
"""
import hashlib
import logging
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from .config import get_settings
from .request_id import request_id_of
from .tasks import TASK_BY_PATH

logger = logging.getLogger("backend.audit")

ACTOR = "anonymous"
BLOCKED_CODES = {"INVALID_INPUT", "UNSUPPORTED_LANGUAGE", "CODE_TOO_LARGE", "TOOL_NOT_ALLOWED"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    request_id  TEXT    NOT NULL,
    actor       TEXT    NOT NULL,
    action      TEXT    NOT NULL,
    input_hash  TEXT,
    decision    TEXT    NOT NULL CHECK (decision IN ('allowed','blocked','needs_approval','error')),
    reason      TEXT    NOT NULL,
    duration_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_log (request_id);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'journal en ajout seulement'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'journal en ajout seulement'); END;
"""

COLUMNS = ("id", "timestamp", "request_id", "actor", "action",
           "input_hash", "decision", "reason", "duration_ms")


# ---------- Écriture et lecture ----------
def hash_code(code: str) -> str:
    """Empreinte SHA-256 du code (on prouve l'appel sans garder le code)."""
    return hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest()


def record(*, request_id, action, input_hash, decision, reason, duration_ms, db_path=None) -> None:
    path = Path(db_path or get_settings().audit_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with closing(sqlite3.connect(path, timeout=5)) as conn:
        conn.executescript(SCHEMA)
        with conn:
            conn.execute(
                "INSERT INTO audit_log (timestamp, request_id, actor, action, input_hash,"
                " decision, reason, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (timestamp, request_id, ACTOR, action, input_hash, decision, reason, duration_ms),
            )


def read_recent(limit: int = 20, db_path=None) -> list[dict]:
    """Les dernières lignes du journal, la plus récente en premier."""
    path = Path(db_path or get_settings().audit_db_path)
    if not path.exists():
        return []
    with closing(sqlite3.connect(path, timeout=5)) as conn:
        rows = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(zip(COLUMNS, row)) for row in rows]


# ---------- Ce que les routes et les gestionnaires d'erreurs signalent ----------
def set_input(request: Request, code: str) -> None:
    """Appelée par les routes dès qu'elles ont le code (avant toute vérification)."""
    request.state.audit_input_hash = hash_code(code)


def add_secret_stats(request: Request, masked_in: int = 0, masked_out: int = 0, suspects: int = 0) -> None:
    """Cumule les secrets masqués à l'entrée / à la sortie (juste des NOMBRES, jamais les secrets)."""
    stats = getattr(request.state, "audit_secrets", (0, 0, 0))
    request.state.audit_secrets = (stats[0] + masked_in, stats[1] + masked_out, stats[2] + suspects)


def _with_secret_note(reason: str, request: Request) -> str:
    masked_in, masked_out, suspects = getattr(request.state, "audit_secrets", (0, 0, 0))
    if masked_in + masked_out:
        reason += f";secrets_masked=in:{masked_in},out:{masked_out}"
    if suspects:
        reason += f";suspects={suspects}"
    return reason


def set_error(request: Request, code: str) -> None:
    """Appelée par les gestionnaires d'erreurs : note la décision selon le code d'erreur."""
    decision = "blocked" if code in BLOCKED_CODES else "error"
    request.state.audit_outcome = (decision, code)


# ---------- Le middleware : écrit la ligne après chaque appel d'une porte ----------
async def _write(request: Request, start: float, decision: str, reason: str) -> None:
    try:
        await run_in_threadpool(
            record,
            request_id=request_id_of(request),
            action=TASK_BY_PATH[request.url.path],
            input_hash=getattr(request.state, "audit_input_hash", None),
            decision=decision,
            reason=reason,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
    except Exception:
        logger.exception("Écriture dans le journal d'audit impossible")


async def audit_middleware(request: Request, call_next):
    if request.method != "POST" or request.url.path not in TASK_BY_PATH:
        return await call_next(request)   # /health, /docs... ne sont pas journalisés
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        await _write(request, start, "error", _with_secret_note("INTERNAL_ERROR", request))
        raise
    outcome = getattr(request.state, "audit_outcome", None)
    if outcome is None:
        outcome = ("allowed", "ok") if response.status_code < 400 else ("error", f"HTTP_{response.status_code}")
    await _write(request, start, outcome[0], _with_secret_note(outcome[1], request))
    return response


if __name__ == "__main__":
    for row in read_recent():
        print(row)
