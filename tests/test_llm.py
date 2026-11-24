
import pytest
import subprocess
import sys

from llm import LLMClient


class FakeBackend:
    """Backend fictif pour tester LLMClient sans charger un modèle."""

    def __init__(self):
        self.called = False

    def generate(self, messages):
        self.called = True

        return {
            "text": "Réponse de test",
            "tokens_in": 10,
            "tokens_out": 20,
            "latency_s": 0.5
        }


def test_client_initialization():
    backend = FakeBackend()
    client = LLMClient(backend)

    assert client.backend is backend


def test_generate_success():
    backend = FakeBackend()
    client = LLMClient(backend)

    messages = [
        {
            "role": "user",
            "content": "Explique une boucle for."
        }
    ]

    result = client.generate(messages)

    assert backend.called is True
    assert result["text"] == "Réponse de test"
    assert result["tokens_in"] == 10
    assert result["tokens_out"] == 20
    assert result["latency_s"] == 0.5


def test_generate_invalid_type():
    client = LLMClient(FakeBackend())

    with pytest.raises(TypeError):
        client.generate("Bonjour")


def test_generate_empty_messages():
    client = LLMClient(FakeBackend())

    with pytest.raises(ValueError):
        client.generate([])


def test_invalid_precision():
    """Vérifie qu'une précision non supportée déclenche une erreur."""

    from llm.backends.qwen_base import QwenBaseBackend

    with pytest.raises(ValueError):
        QwenBaseBackend(precision="fp32")


def test_light_imports():
    """Vérifie que les imports légers ne chargent pas torch et transformers."""

    code = """
import sys
from llm import LLMClient
from llm.backends import StubBackend

assert "torch" not in sys.modules
assert "transformers" not in sys.modules
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, result.stderr
