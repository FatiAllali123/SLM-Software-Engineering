"""Formats JSON du backend : traduction en code de docs/api_contract.md.

Si le contrat change, on modifie ce fichier.
"""
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Mode = Literal["single_agent", "multi_agent"]
Status = Literal["ok", "error", "blocked", "needs_approval"]
Task = Literal["analyze", "generate_tests", "review", "execute"]
Severity = Literal["low", "medium", "high"]


def new_request_id() -> str:
    """Identifiant unique d'une requête (aussi écrit dans le journal d'audit)."""
    return uuid.uuid4().hex[:12]


# ---------- Requêtes (section 4 du contrat) ----------
class TaskRequest(BaseModel):
    """Pour /analyze, /generate-tests et /review."""
    code: str
    language: str = "python"
    mode: Mode = "single_agent"


class ExecuteRequest(BaseModel):
    """Pour /execute."""
    code: str
    language: str = "python"
    timeout_s: Optional[int] = Field(default=None, ge=1)


# ---------- Contenu de "result" (section 5.1 du contrat) ----------
class Issue(BaseModel):
    line: Optional[int] = None
    severity: Severity
    category: Literal["bug", "vulnerability", "quality", "style"]
    message: str


class AnalyzeResult(BaseModel):
    issues: list[Issue] = Field(default_factory=list)
    summary: str


class GenerateTestsResult(BaseModel):
    tests: str
    test_count: int
    summary: str


class Finding(BaseModel):
    line: Optional[int] = None
    severity: Severity
    message: str


class ReviewResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    verdict: Literal["approve", "approve_with_comments", "request_changes"]
    summary: str


class ExecuteResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: Optional[int] = None   # None si le processus a été arrêté
    timed_out: bool
    duration_ms: int


# ---------- Enveloppe commune (section 5 du contrat) ----------
class Metrics(BaseModel):
    model: str
    precision: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    llm_calls: int
    mode: Mode


class ErrorInfo(BaseModel):
    code: str
    message: str


class Envelope(BaseModel):
    request_id: str
    status: Status
    task: Task
    result: Optional[dict[str, Any]] = None
    metrics: Optional[Metrics] = None
    error: Optional[ErrorInfo] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_backend: str


# ---------- Fabriques d'enveloppes ----------
def ok_envelope(task, result, metrics=None, request_id=None) -> Envelope:
    """Enveloppe d'une réponse réussie."""
    data = result.model_dump() if isinstance(result, BaseModel) else result
    return Envelope(
        request_id=request_id or new_request_id(),
        status="ok",
        task=task,
        result=data,
        metrics=metrics,
        error=None,
    )


def error_envelope(task, code, message, status="error", request_id=None) -> Envelope:
    """Enveloppe d'une réponse en erreur (result et metrics valent null)."""
    return Envelope(
        request_id=request_id or new_request_id(),
        status=status,
        task=task,
        result=None,
        metrics=None,
        error=ErrorInfo(code=code, message=message),
    )
