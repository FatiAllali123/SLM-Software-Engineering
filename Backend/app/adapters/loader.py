"""Chargement d'un module facultatif (celui de B ou de D)."""
import importlib


def load_optional(module_name: str):
    """Renvoie le module, ou None s'il n'existe pas encore.

    Si le module existe mais plante à cause d'autre chose (une bibliothèque
    manquante, une erreur dans son code), l'erreur est relancée : on ne la cache pas.
    """
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        parts = module_name.split(".")
        own_names = {".".join(parts[:i]) for i in range(1, len(parts) + 1)}
        if exc.name in own_names:
            return None
        raise
