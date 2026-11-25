"""NIVEAU 3c : secrets fragmentés (cas simples).

1. Littéraux collés :  "sk-" + "abc..."   ou   ("sk-" "abc...")
2. Variables assemblées :  part1 = "sk-ab"  ;  part2 = "cd..."  ;  key = part1 + part2

On recolle les morceaux, on analyse le résultat, et si c'est un secret on masque CHAQUE morceau
(les guillemets restent : le code reste valide). Limites assumées : pas de f-strings, de
join(), de boucles ni de fragments répartis dans plusieurs fonctions.
"""
import re

from .context import is_sensitive_name
from .literals import CONCAT, LITERAL, inner_spans
from .models import Finding
from .patterns import is_placeholder

_CONCAT_RE = re.compile(CONCAT)
_ASSIGN_LINE = re.compile(
    r"^[ \t]*(?:self\.)?(?P<name>[A-Za-z_]\w*)[ \t]*=(?!=)[ \t]*(?P<rhs>[^\n]+?)[ \t]*$", re.M
)
_OPERAND = re.compile(LITERAL + r"|[A-Za-z_]\w*")


def _parse_operands(rhs: str):
    """Découpe 'a + "x" + b' en opérandes ; None si l'expression contient autre chose."""
    ops, pos = [], 0
    for m in _OPERAND.finditer(rhs):
        gap = rhs[pos:m.start()]
        if (not ops and gap) or (ops and gap.strip() != "+"):
            return None
        ops.append(m)
        pos = m.end()
    return ops if ops and not rhs[pos:] else None


def find(text: str, scan) -> list:
    """scan(texte) renvoie la liste des secrets trouvés dans ce texte."""
    findings, seen = [], set()

    def flag(spans, kind):
        for s, e in spans:
            if e > s and (s, e) not in seen:
                seen.add((s, e))
                findings.append(Finding(s, e, "fragment", kind))

    # 1) littéraux collés
    for m in _CONCAT_RE.finditer(text):
        spans = inner_spans(text, m.start(), m.end())
        if len(spans) >= 2 and scan("".join(text[s:e] for s, e in spans)):
            flag(spans, "concatenation")

    # 2) variables assemblées, ligne par ligne
    known = {}   # nom -> (valeur, [positions des morceaux])
    for m in _ASSIGN_LINE.finditer(text):
        ops = _parse_operands(m.group("rhs"))
        if ops is None:
            continue
        value, spans, ok = "", [], True
        for op in ops:
            raw = op.group()
            if raw[0] in "\"'" or (len(raw) > 1 and raw[1] in "\"'") or (len(raw) > 2 and raw[2] in "\"'"):
                base = m.start("rhs") + op.start()
                (s, e), = inner_spans(text, base, base + len(raw))[:1] or [(base, base)]
                value += text[s:e]
                spans.append((s, e))
            elif raw in known:
                value += known[raw][0]
                spans += known[raw][1]
            else:
                ok = False
                break
        if not ok:
            continue
        known[m.group("name")] = (value, spans)
        if len(ops) >= 2 and (scan(value) or (is_sensitive_name(m.group("name"))
                                             and len(value) >= 8 and not is_placeholder(value))):
            flag(spans, "assembled")
    return findings
