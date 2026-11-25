"""Assemble les trois niveaux : formats -> contexte -> complémentaire (fragments, encodages, entropie)."""
from . import context, encodings, entropy, fragments, patterns, urls
from .models import FilterResult, Finding

MASK = "[SECRET_MASQUÉ]"   # valeur fixée par le contrat d'API (section 6)


def merge(findings: list) -> list:
    """Fusionne les zones qui se chevauchent (un même secret vu par deux couches = un seul masquage)."""
    merged = []
    for f in sorted(findings, key=lambda f: (f.start, -f.end)):
        if merged and f.start < merged[-1].end:
            last = merged[-1]
            if f.end > last.end:
                merged[-1] = Finding(last.start, f.end, last.layer, last.kind)
        else:
            merged.append(f)
    return merged


def scan(text: str, settings, depth: int = 0, with_entropy: bool = True, with_fragments: bool = True):
    """Renvoie (liste de secrets trouvés, nombre de suspects non masqués)."""
    def inner(decoded: str) -> list:
        return scan(decoded, settings, depth + 1, with_entropy=False, with_fragments=False)[0]

    findings = patterns.find_known(text)               # niveau 1
    findings += urls.find(text)                        # niveau 1 (URL)
    findings += context.find(text)                     # niveau 2
    if with_fragments:                                 # niveau 3
        findings += fragments.find(text, inner)
    findings += encodings.find(text, settings, depth, inner, findings)
    suspects = 0
    if with_entropy:
        confirmed, suspects = entropy.find(text, settings, findings)
        findings += confirmed
    return merge(findings), suspects


def mask_text(text: str, settings) -> FilterResult:
    if not text:
        return FilterResult(text=text)
    findings, suspects = scan(text, settings)
    parts, pos = [], 0
    for f in findings:
        parts += [text[pos:f.start], MASK]
        pos = f.end
    parts.append(text[pos:])
    return FilterResult(text="".join(parts), findings=findings, suspects=suspects)
