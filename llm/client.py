
# le point d'entrée utilisé par les autres parties du projet.
# classe LLMClient, qui sert de façade ou d'intermédiaire entre le reste de l'application et les différents backends

class LLMClient:
    """Client unique pour communiquer avec différents modèles."""

    def __init__(self, backend):
        self.backend = backend

    def generate(self, messages: list[dict]) -> dict:
        if not isinstance(messages, list):
            raise TypeError("messages doit être une liste")

        if not messages:
            raise ValueError("La liste messages ne doit pas être vide")

        return self.backend.generate(messages)
