# Le Stub est un faux backend. Il permet de tester l'architecture sans télécharger Qwen et sans utiliser de GPU.
# les nombres de tokens du Stub sont des estimations basées sur les mots. Les vrais backends utiliseront leur tokenizer.
# Le StubBackend est donc un simulateur de LLM

import time
from llm.backends.base import BaseBackend


class StubBackend(BaseBackend):

    def generate(self, messages: list[dict]) -> dict:
        start = time.perf_counter()

        # Récupérer le dernier message utilisateur
        user_message = ""

        for message in messages:
            if message.get("role") == "user":
                user_message = message.get("content", "")

        # Réponse simulée
        response = (
            f"[STUB] Réponse simulée pour : {user_message}"
        )

        latency = time.perf_counter() - start

        # Estimation approximative, pas un comptage réel de tokens
        tokens_in = sum(
            len(str(message.get("content", "")).split())
            for message in messages
        )
        tokens_out = len(response.split())

        return {
            "text": response,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_s": latency
        }
