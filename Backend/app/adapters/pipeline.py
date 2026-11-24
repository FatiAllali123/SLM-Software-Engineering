"""Adaptateur vers les agents de D (agents/pipeline.py, fonction run_pipeline()).

- Fichier de D présent -> on l'utilise.
- Fichier de D absent  -> faux pipeline qui renvoie des réponses fictives au bon format.
- Le résultat de D est VÉRIFIÉ : un mauvais format donne INTERNAL_ERROR.
- ToolNotAllowedError (outil interdit) -> TOOL_NOT_ALLOWED (status "blocked").
- Panne du modèle pendant le pipeline  -> MODEL_ERROR.
"""
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ..config import get_settings
from ..errors import AppError
from ..schemas import AnalyzeResult, GenerateTestsResult, Metrics, ReviewResult
from .loader import load_optional

logger = logging.getLogger("backend.adapters.pipeline")

RESULT_MODELS = {
    "analyze": AnalyzeResult,
    "generate_tests": GenerateTestsResult,
    "review": ReviewResult,
}


@dataclass
class TaskOutcome:
    result: dict
    metrics: Metrics
    trace: list = field(default_factory=list)   # servira au journal d'audit (étape 2)


class _GuardedLLM:
    """Enveloppe le modèle : note les mesures et sait si le modèle a planté."""

    def __init__(self, llm):
        self._llm = llm
        self.failed = False
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.latency_ms = 0
        self.model = "unknown"
        self.precision = "unknown"

    def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.0):
        try:
            response = self._llm.generate(prompt, max_new_tokens=max_new_tokens, temperature=temperature)
        except Exception:
            self.failed = True
            raise
        self.calls += 1
        self.input_tokens += int(getattr(response, "input_tokens", 0))
        self.output_tokens += int(getattr(response, "output_tokens", 0))
        self.latency_ms += int(getattr(response, "latency_ms", 0))
        self.model = str(getattr(response, "model", self.model))
        self.precision = str(getattr(response, "precision", self.precision))
        return response


def _fake_pipeline(task: str, code: str, language: str, mode: str, llm) -> dict:
    """Faux pipeline : un seul appel au modèle, résultat fictif au bon format."""
    response = llm.generate(f"[{task}]\n{code}")
    fakes = {
        "analyze": {
            "issues": [{"line": 1, "severity": "low", "category": "quality",
                        "message": "Réponse fictive : le vrai pipeline n'est pas branché."}],
            "summary": "Analyse fictive",
        },
        "generate_tests": {
            "tests": "def test_placeholder():\n    assert True\n",
            "test_count": 1,
            "summary": "Test fictif",
        },
        "review": {
            "findings": [{"line": 1, "severity": "low",
                          "message": "Réponse fictive : le vrai pipeline n'est pas branché."}],
            "verdict": "approve_with_comments",
            "summary": "Revue fictive",
        },
    }
    step = {"agent": "fake", "step": task, "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens, "latency_ms": response.latency_ms}
    return {
        "result": fakes[task],
        "metrics": {"input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
                    "latency_ms": response.latency_ms, "llm_calls": 1},
        "trace": [step],
    }


def _load_runner():
    settings = get_settings()
    try:
        module = load_optional(settings.pipeline_module)
        if module is None:
            return _fake_pipeline
        return module.run_pipeline
    except Exception as exc:
        logger.exception("Impossible de charger le pipeline des agents")
        raise AppError("INTERNAL_ERROR", "Erreur interne du serveur.") from exc


def _int(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else fallback


def _is_tool_error(exc: Exception) -> bool:
    return any(cls.__name__ == "ToolNotAllowedError" for cls in type(exc).__mro__)


def run_task(task: str, code: str, language: str, mode: str, llm) -> TaskOutcome:
    guarded = _GuardedLLM(llm)
    runner = _load_runner()

    try:
        raw = runner(task=task, code=code, language=language, mode=mode, llm=guarded)
    except AppError:
        raise
    except Exception as exc:
        if _is_tool_error(exc):
            raise AppError("TOOL_NOT_ALLOWED", "Un agent a demandé un outil non autorisé.") from exc
        logger.exception("Le pipeline a échoué")
        if guarded.failed:
            raise AppError("MODEL_ERROR", "Le modèle n'a pas répondu.") from exc
        raise AppError("INTERNAL_ERROR", "Erreur interne du serveur.") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("result"), dict):
        logger.error("Le pipeline n'a pas renvoyé un dictionnaire avec un champ 'result'")
        raise AppError("INTERNAL_ERROR", "Le pipeline a renvoyé un format invalide.")
    try:
        result = RESULT_MODELS[task].model_validate(raw["result"]).model_dump()
    except ValidationError as exc:
        logger.error("Résultat du pipeline invalide, champs : %s", [e["loc"] for e in exc.errors()])
        raise AppError("INTERNAL_ERROR", "Le pipeline a renvoyé un format invalide.") from exc

    raw_metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    metrics = Metrics(
        model=guarded.model,
        precision=guarded.precision,
        input_tokens=_int(raw_metrics.get("input_tokens"), guarded.input_tokens),
        output_tokens=_int(raw_metrics.get("output_tokens"), guarded.output_tokens),
        latency_ms=_int(raw_metrics.get("latency_ms"), guarded.latency_ms),
        llm_calls=_int(raw_metrics.get("llm_calls"), guarded.calls),
        mode=mode,
    )
    trace = raw.get("trace") if isinstance(raw.get("trace"), list) else []
    return TaskOutcome(result=result, metrics=metrics, trace=trace)
