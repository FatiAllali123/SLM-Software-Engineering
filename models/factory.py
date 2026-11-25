# création et sélection du client.
# cette Factory centralise la sélection des backends

from .llm_client import StubLLMClient, RealLLMClient


def get_llm_client(backend_type="stub", **backend_kwargs):
    """
    Crée le client LLM selon le backend choisi.

    Paramètres
    ----------
    backend_type : str
        Type de backend :
        - stub
        - qwen_base
        - qwen_nf4
        - qwen_lora

    backend_kwargs :
        Paramètres transmis au constructeur du backend.

    Retour
    ------
    StubLLMClient ou RealLLMClient
    """

    # Mode Stub : aucune charge de modèle
    if backend_type == "stub":
        if backend_kwargs:
            raise ValueError(
                "Le backend stub n'accepte pas de paramètres supplémentaires."
            )

        return StubLLMClient()

    # Importations différées pour conserver les imports légers
    if backend_type == "qwen_base":
        from llm.backends.qwen_base import QwenBaseBackend

        backend = QwenBaseBackend(**backend_kwargs)

    elif backend_type == "qwen_nf4":
        from llm.backends.qwen_nf4 import QwenNF4Backend

        backend = QwenNF4Backend(**backend_kwargs)

    elif backend_type == "qwen_lora":
        from llm.backends.qwen_lora import QwenLoRABackend

        backend = QwenLoRABackend(**backend_kwargs)

    else:
        raise ValueError(
            f"Backend inconnu : {backend_type}. "
            "Choix disponibles : stub, qwen_base, qwen_nf4, qwen_lora."
        )

    return RealLLMClient(backend)
