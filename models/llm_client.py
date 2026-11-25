
# Le dossier models/ contient l'adaptateur entre l'interface
# attendue par les agents et notre système actuel de backends.
#
# LLMResponse : structure standard de la réponse du modèle.
# LLMClient : contrat commun utilisé par les agents.
# StubLLMClient : client utilisant le backend fictif.
# RealLLMClient : adaptateur vers notre client interne llm/client.py.


from dataclasses import dataclass
from typing import Protocol

from llm.client import LLMClient as BackendLLMClient
from llm.backends.stub import StubBackend


# ============================================================
# 1. Structure standard de la réponse
# ============================================================

@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str
    precision: str


# ============================================================
# 2. Interface commune utilisée par les agents
# ============================================================

class LLMClient(Protocol):

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.0
    ) -> LLMResponse:
        ...


# ============================================================
# 3. Fonction de validation des paramètres
# ============================================================

def validate_generation_params(prompt, max_new_tokens, temperature):

    if not isinstance(prompt, str):
        raise TypeError("prompt doit être une chaîne de caractères")

    if not prompt.strip():
        raise ValueError("prompt ne doit pas être vide")

    if not isinstance(max_new_tokens, int) or isinstance(max_new_tokens, bool):
        raise TypeError("max_new_tokens doit être un entier.")

    if max_new_tokens <= 0:
        raise ValueError("max_new_tokens doit être positif.")

    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise TypeError("temperature doit être un nombre.")

    if not 0 <= temperature <= 2:
        raise ValueError("temperature doit être comprise entre 0 et 2.")


# ============================================================
# 4. Client fictif pour les tests
# ============================================================

class StubLLMClient:

    def __init__(self):
        self.client = BackendLLMClient(StubBackend())

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.0
    ) -> LLMResponse:

        validate_generation_params(
            prompt,
            max_new_tokens,
            temperature
        )

        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        result = self.client.generate(
            messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature
        )

        return LLMResponse(
            text=result["text"],
            input_tokens=result["tokens_in"],
            output_tokens=result["tokens_out"],
            latency_ms=round(result["latency_s"] * 1000),
            model="stub",
            precision="none"
        )


# ============================================================
# 5. Client réel : adaptateur vers llm/client.py
# ============================================================

class RealLLMClient:

    def __init__(self, backend):

        if backend is None:
            raise ValueError("Un backend doit être fourni.")

        self.client = BackendLLMClient(backend)

        self.model = getattr(
            backend,
            "model_name",
            "stub" if isinstance(backend, StubBackend) else "unknown"
        )

        self.precision = getattr(
            backend,
            "precision",
            "none" if isinstance(backend, StubBackend) else "unknown"
        )

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.0
    ) -> LLMResponse:

        validate_generation_params(
            prompt,
            max_new_tokens,
            temperature
        )

        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        result = self.client.generate(
            messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature
        )

        return LLMResponse(
            text=result["text"],
            input_tokens=result["tokens_in"],
            output_tokens=result["tokens_out"],
            latency_ms=round(result["latency_s"] * 1000),
            model=self.model,
            precision=self.precision
        )
