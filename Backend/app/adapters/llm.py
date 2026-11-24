"""Adaptateur vers le modèle de B (models/llm_client.py, fonction get_llm_client()).

- Fichier de B présent  -> on l'utilise.
- Fichier de B absent   -> faux modèle (StubLLM), sauf si LLM_BACKEND=real
  (dans ce cas on refuse : on ne fait pas semblant d'avoir un vrai modèle).
- Toute panne            -> AppError MODEL_ERROR (jamais de détail technique au client).
"""
import logging
from dataclasses import dataclass

from ..config import get_settings
from ..errors import AppError
from .loader import load_optional

logger = logging.getLogger("backend.adapters.llm")


@dataclass
class LLMResponse:
    """Même forme que LLMResponse du contrat (section 9)."""
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str
    precision: str


class StubLLM:
    """Faux modèle de secours : réponse fixe et instantanée."""

    def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.0) -> LLMResponse:
        text = "[réponse fictive du faux modèle]"
        return LLMResponse(
            text=text,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            latency_ms=0,
            model="stub",
            precision="none",
        )


def get_llm():
    settings = get_settings()
    try:
        module = load_optional(settings.llm_module)
        if module is None:
            if settings.llm_backend == "real":
                raise AppError("MODEL_ERROR", "Le modèle réel n'est pas disponible.")
            return StubLLM()
        return module.get_llm_client()
    except AppError:
        raise
    except Exception as exc:
        logger.exception("Impossible de charger le modèle")
        raise AppError("MODEL_ERROR", "Le modèle n'a pas pu être chargé.") from exc
