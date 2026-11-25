
from llm.backends import StubBackend


def test_stub_initialization():
    """Vérifie l'initialisation du backend."""

    backend = StubBackend()

    assert backend is not None


def test_stub_generate():
    """Vérifie la génération d'une réponse."""

    backend = StubBackend()

    messages = [
        {
            "role": "user",
            "content": "Explique une boucle for en Python."
        }
    ]

    result = backend.generate(messages)

    assert isinstance(result, dict)
    assert isinstance(result["text"], str)
    assert "[STUB]" in result["text"]
    assert result["tokens_in"] > 0
    assert result["tokens_out"] > 0
    assert result["latency_s"] >= 0


def test_stub_uses_last_user_message():
    """Vérifie que le backend utilise le dernier message utilisateur."""

    backend = StubBackend()

    messages = [
        {"role": "user", "content": "Premier message"},
        {"role": "assistant", "content": "Réponse précédente"},
        {"role": "user", "content": "Dernier message"}
    ]

    result = backend.generate(messages)

    assert "Dernier message" in result["text"]
