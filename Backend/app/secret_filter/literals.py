"""Repérage des chaînes de caractères entre guillemets (style Python / JavaScript)."""
import re

_QUOTED = r'"(?:\\.|[^"\\\n])*"' + "|" + r"'(?:\\.|[^'\\\n])*'"
LITERAL = r"[rRbBuUfF]{0,2}(?:" + _QUOTED + ")"

# Un ou plusieurs littéraux collés : "a" + "b", ou "a" "b" (concaténation implicite)
CONCAT = (
    r"(?<!\w)" + LITERAL
    + r"(?:(?:[ \t]*\+[ \t]*|[ \t]*(?:\r?\n[ \t]*)?)" + LITERAL + ")*"
)

_LITERAL_RE = re.compile(LITERAL)


def inner_spans(text: str, start: int, end: int) -> list:
    """Positions (début, fin) du CONTENU de chaque littéral entre start et end (guillemets exclus)."""
    spans = []
    for m in _LITERAL_RE.finditer(text, start, end):
        s = m.start()
        while text[s] not in "\"'":
            s += 1
        spans.append((s + 1, m.end() - 1))
    return spans
