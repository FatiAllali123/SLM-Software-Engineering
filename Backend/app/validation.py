"""Vérifications faites à l'entrée, avant tout traitement.

Règle de sécurité : les messages d'erreur sont fixes. Ils ne répètent JAMAIS
ce que l'utilisateur a envoyé (le code pourrait contenir un secret).
"""
from .config import Settings
from .errors import AppError


def validate_code(code: str, language: str, settings: Settings) -> None:
    """Lève une AppError si le langage, la taille ou le contenu du code est refusé."""
    if language not in settings.supported_languages:
        raise AppError("UNSUPPORTED_LANGUAGE", "Seul le langage python est accepté.")
    if not code.strip():
        raise AppError("INVALID_INPUT", "Le code ne doit pas être vide.")
    try:
        size = len(code.encode("utf-8"))
    except UnicodeEncodeError:
        # Caractère Unicode invalide (ex. surrogate isolé) : on refuse proprement
        raise AppError("INVALID_INPUT", "Le code contient des caractères invalides.")
    if size > settings.max_code_bytes:
        limit_kb = settings.max_code_bytes // 1024
        raise AppError("CODE_TOO_LARGE", f"Le code dépasse {limit_kb} Ko.")


def validate_timeout(timeout_s, settings: Settings) -> int:
    """Renvoie le temps d'exécution à utiliser (défaut = maximum) ou lève une AppError."""
    if timeout_s is None:
        return settings.max_exec_seconds
    if timeout_s > settings.max_exec_seconds:
        raise AppError(
            "INVALID_INPUT",
            f"timeout_s dépasse le maximum de {settings.max_exec_seconds} secondes.",
        )
    return timeout_s
