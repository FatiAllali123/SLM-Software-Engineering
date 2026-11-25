"""Secrets dans les URL : identifiants (user:motdepasse@hote), paramètres de requête
(?api_key=...), fragments (#access_token=...) et chemins identifiables (/token/<valeur>)."""
import re
from urllib.parse import unquote

from .context import URL_EXTRA_WORDS, is_sensitive_name
from .models import Finding
from .patterns import is_placeholder

_URL = re.compile(r"""(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]{1,20}://[^\s'"<>`)\]]+""")
_PIECE = re.compile(r"[^&;]+")

# Mots-clés de chemin : /token/<valeur>, /apikey/<valeur>...
_PATH_KEYWORDS = {"token", "tokens", "apikey", "api-key", "api_key", "secret", "secrets", "password",
                  "passwd", "key", "access_token", "access-token", "auth", "bearer"}
_TOKEN_LIKE = re.compile(r"^[A-Za-z0-9._~\-]{16,}$")
_MIN_LEN_EXACT = {"key": 12, "sig": 8}   # noms ambigus : valeur assez longue exigée


def _param_is_secret(key: str, value: str) -> bool:
    k = unquote(key).strip().lower().strip("[]")
    if not value or is_placeholder(unquote(value)):
        return False
    if k in _MIN_LEN_EXACT:
        return len(value) >= _MIN_LEN_EXACT[k]
    return is_sensitive_name(k, extra_words=URL_EXTRA_WORDS) and len(value) >= 3


def _scan_pairs(section: str, offset: int, findings: list) -> None:
    for piece in _PIECE.finditer(section):
        key, sep, value = piece.group().partition("=")
        if sep and _param_is_secret(key, value):
            start = offset + piece.start() + len(key) + 1
            findings.append(Finding(start, start + len(value), "url", "url_parameter"))


def find(text: str) -> list:
    findings = []
    for m in _URL.finditer(text):
        url = m.group().rstrip(".,;:!?")
        base = m.start()
        auth_start = url.index("://") + 3
        ends = [i for i in (url.find("/", auth_start), url.find("?", auth_start), url.find("#", auth_start)) if i != -1]
        auth_end = min(ends) if ends else len(url)

        # 1) identifiants intégrés : scheme://utilisateur:MOTDEPASSE@hote
        authority = url[auth_start:auth_end]
        if "@" in authority:
            userinfo = authority.rpartition("@")[0]
            user, colon, password = userinfo.partition(":")
            if colon and password and not is_placeholder(password):
                start = base + auth_start + len(user) + 1
                findings.append(Finding(start, start + len(password), "url", "url_credentials"))

        q = url.find("?", auth_end)
        h = url.find("#", auth_end)
        path_end = min(i for i in (q, h, len(url)) if i != -1)

        # 2) paramètres de requête
        if q != -1:
            q_end = h if h > q else len(url)
            _scan_pairs(url[q + 1:q_end], base + q + 1, findings)
        # 3) fragment : #access_token=...&token_type=bearer
        if h != -1 and "=" in url[h + 1:]:
            _scan_pairs(url[h + 1:], base + h + 1, findings)

        # 4) chemin identifiable : /token/<valeur longue>
        pos = auth_end
        segments = []
        for seg in url[auth_end:path_end].split("/"):
            segments.append((pos, seg))
            pos += len(seg) + 1
        for (_, kw), (vpos, val) in zip(segments, segments[1:]):
            if (unquote(kw).lower() in _PATH_KEYWORDS and _TOKEN_LIKE.match(val)
                    and any(c.isdigit() for c in val) and any(c.isalpha() for c in val)
                    and not is_placeholder(val)):
                findings.append(Finding(base + vpos, base + vpos + len(val), "url", "url_path"))
    return findings
