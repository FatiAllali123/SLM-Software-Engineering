"""NIVEAU 3a : entropie. L'entropie ne masque JAMAIS à elle seule.

Une chaîne qui "a l'air aléatoire" devient seulement SUSPECTE. Elle n'est masquée que si
un second indice la confirme : elle est la valeur d'un nom "faible" (key, auth, session,
signature, salt...) juste avant elle. Sinon elle est comptée comme suspecte (journal d'audit)
mais laissée intacte : un hash, un identifiant ou un nom de fichier ne sont pas abîmés.
"""
import math
import re
from collections import Counter

from .context import has_weak_hint
from .models import Finding
from .patterns import is_placeholder

_NAME_BEFORE = re.compile(
    r"""(?:^|[\s,;(\[{&?#"'])["']?(?P<name>[A-Za-z_][\w\-.]*)["']?[ \t]*(?:==|=>|:=|=|:)[ \t]*["']?$"""
)


def shannon(s: str) -> float:
    """Entropie de Shannon en bits par caractère."""
    if not s:
        return 0.0
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values())


def _classes(s: str) -> int:
    return sum([any(c.islower() for c in s), any(c.isupper() for c in s),
                any(c.isdigit() for c in s), any(not c.isalnum() for c in s)])


def _looks_random(token: str, threshold: float) -> bool:
    return (any(c.isdigit() for c in token) and any(c.isalpha() for c in token)
            and _classes(token) >= 3 and shannon(token) >= threshold
            and not is_placeholder(token))


def _name_before(text: str, start: int):
    line_part = text[max(0, start - 100):start].rsplit("\n", 1)[-1]
    m = _NAME_BEFORE.search(line_part)
    return m.group("name") if m else None


def find(text: str, settings, taken: list) -> tuple:
    """Renvoie (secrets confirmés, nombre de suspects non masqués)."""
    candidate = re.compile(
        r"(?<![A-Za-z0-9+/_\-=])[A-Za-z0-9+/_\-=]{%d,}(?![A-Za-z0-9+/_\-=])" % settings.entropy_min_length
    )
    findings, suspects = [], 0
    for m in candidate.finditer(text):
        if any(f.start < m.end() and m.start() < f.end for f in taken):
            continue   # déjà repéré par une autre couche
        token = m.group()
        if not _looks_random(token, settings.entropy_threshold):
            continue
        name = _name_before(text, m.start())
        if name and has_weak_hint(name):
            findings.append(Finding(m.start(), m.end(), "entropy", "entropy_with_context"))
        else:
            suspects += 1
    return findings, suspects
