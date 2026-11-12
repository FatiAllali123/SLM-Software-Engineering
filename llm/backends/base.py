# cette classe définit l'interface commune pour tous les backends LLM. 
# Chaque backend doit implémenter la méthode `generate`,
#  qui prend une liste de messages et retourne un dictionnaire contenant le texte généré, 
# le nombre de tokens d'entrée et de sortie, ainsi que la latence en secondes.

# --> Cette classe définit le contrat que tous les backends doivent respecter.

from abc import ABC, abstractmethod


class BaseBackend(ABC):
    """Interface commune pour tous les backends LLM."""

    @abstractmethod
    def generate(self, messages: list[dict]) -> dict:
        """
        Génère une réponse à partir d'une liste de messages.

        Retourne :
        {
            "text": str,
            "tokens_in": int,
            "tokens_out": int,
            "latency_s": float
        }
        """
        pass
