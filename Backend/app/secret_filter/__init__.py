"""Filtre de secrets à trois niveaux (voir docs : section sécurité).

    from Backend.app.secret_filter import mask_secrets, mask_json

Niveau 1 : formats connus (patterns.py, urls.py)
Niveau 2 : contexte (context.py)
Niveau 3 : complémentaire (fragments.py, encodings.py, entropy.py)
Le tout est assemblé par engine.py. Les seuils sont dans config.py.
"""
from typing import Any

from ..config import get_settings
from .engine import MASK, mask_text
from .models import FilterResult, Finding

__all__ = ["mask_secrets", "mask_json", "MASK", "FilterResult", "Finding"]


def mask_secrets(text: str, settings=None) -> FilterResult:
    """Masque les secrets d'un texte par [SECRET_MASQUÉ]. Ne refuse jamais le texte."""
    return mask_text(text, settings or get_settings())


def mask_json(value: Any, settings=None, _depth: int = 0) -> tuple:
    """Masque les secrets dans toutes les chaînes d'une structure JSON. Renvoie (nouvelle valeur, nombre masqué)."""
    settings = settings or get_settings()
    if _depth > 20:
        return value, 0
    if isinstance(value, str):
        result = mask_text(value, settings)
        return result.text, result.count
    if isinstance(value, dict):
        out, total = {}, 0
        for k, v in value.items():
            out[k], n = mask_json(v, settings, _depth + 1)
            total += n
        return out, total
    if isinstance(value, (list, tuple)):
        items, total = [], 0
        for v in value:
            nv, n = mask_json(v, settings, _depth + 1)
            items.append(nv)
            total += n
        return items, total
    return value, 0
