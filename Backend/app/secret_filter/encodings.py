"""NIVEAU 3b : encodages courants (Base64 et URL encoding).

On décode la chaîne, on relance l'analyse sur le contenu décodé, et si un secret y apparaît
on masque la chaîne d'origine en entier. Profondeur limitée (réglage max_decode_depth).
"""
import base64
import re
from urllib.parse import unquote

from .models import Finding

_URL_ENCODED = re.compile(
    r"(?<![A-Za-z0-9_.~%+:/@\-])[A-Za-z0-9_.~%+:/@\-]*%[0-9A-Fa-f]{2}[A-Za-z0-9_.~%+:/@\-]*"
)
_BASE64 = re.compile(r"(?<![A-Za-z0-9+/_\-=])[A-Za-z0-9+/_\-]{16,}={0,2}(?![A-Za-z0-9+/_\-=])")


def _printable(text: str) -> bool:
    if len(text) < 8:
        return False
    ok = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
    return ok / len(text) >= 0.95


def decode_base64(token: str):
    s = token.rstrip("=")
    if len(s) % 4 == 1:
        return None
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        text = base64.b64decode(s, validate=True).decode("utf-8")
    except Exception:
        return None
    return text if _printable(text) else None


def find(text: str, settings, depth: int, scan, taken: list) -> list:
    """scan(texte_décodé) renvoie la liste des secrets trouvés dans le texte décodé."""
    if depth >= settings.max_decode_depth:
        return []
    findings = []
    for regex, kind, decoder in ((_URL_ENCODED, "url_encoded", unquote), (_BASE64, "base64", decode_base64)):
        for m in regex.finditer(text):
            if any(f.start < m.end() and m.start() < f.end for f in taken + findings):
                continue
            decoded = decoder(m.group())
            if decoded and decoded != m.group() and scan(decoded):
                findings.append(Finding(m.start(), m.end(), "encoding", kind))
    return findings
