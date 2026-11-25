"""NIVEAU 2 : détection par le CONTEXTE (noms de variables, fichiers .env, configuration,
chaînes de connexion, options de ligne de commande).

On ne regarde pas la forme de la valeur mais le nom qui la précède : PASSWORD, API_KEY...
Seule la VALEUR est masquée (le nom et les guillemets restent, pour que le code reste lisible).
"""
import re

from .literals import CONCAT, inner_spans
from .models import Finding
from .patterns import is_placeholder

# ---------- Analyse des noms de variables ----------
_PART_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")

# Mots qui rendent un nom sensible ("token" au singulier seulement : max_tokens n'est pas un secret)
STRONG_WORDS = {"password", "passwd", "pwd", "passphrase", "passcode", "secret", "apikey",
                "credential", "credentials", "creds", "token", "bearer"}
STRONG_PAIRS = {("api", "key"), ("private", "key"), ("access", "key"), ("secret", "key"),
                ("auth", "key"), ("encryption", "key"), ("signing", "key"), ("master", "key"),
                ("session", "key"), ("license", "key"), ("ssh", "key")}
# Dernier mot qui montre que ce n'est PAS la valeur secrète elle-même
EXCLUDED_LAST = {"type", "url", "uri", "name", "file", "path", "field", "header", "length", "size",
                 "count", "limit", "ttl", "expires", "expiry", "expiration", "endpoint", "id", "ids",
                 "label", "env", "var", "variable", "min", "max", "policy", "required", "regex",
                 "pattern", "hint", "placeholder", "text", "message", "error", "help", "title",
                 "description", "format", "prompt", "key_name"}
# Mots "faibles" : ils ne suffisent pas pour masquer, mais ils confirment un soupçon d'entropie
WEAK_WORDS = STRONG_WORDS | {"key", "auth", "authorization", "cred", "sign", "signature", "cert",
                             "certificate", "seed", "salt", "nonce", "session", "cookie", "otp",
                             "hmac", "jwt", "private"}
# Noms de paramètres d'URL sensibles en plus des mots forts
URL_EXTRA_WORDS = {"auth", "authorization", "signature", "sig", "jwt", "key", "sid", "pass", "pw"}


def name_parts(name: str) -> list:
    return [p.lower() for p in _PART_RE.findall(name)]


def _last_segment(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def is_sensitive_name(name: str, extra_words=frozenset()) -> bool:
    parts = name_parts(_last_segment(name))
    if not parts or parts[-1] in EXCLUDED_LAST:
        return False
    if any(p in STRONG_WORDS or p in extra_words for p in parts):
        return True
    return any((a, b) in STRONG_PAIRS for a, b in zip(parts, parts[1:]))


def has_weak_hint(name: str) -> bool:
    parts = name_parts(_last_segment(name))
    if not parts or parts[-1] in EXCLUDED_LAST:
        return False
    return any(p in WEAK_WORDS for p in parts)


# ---------- Fichiers de configuration ----------
_CONFIG_LINE = re.compile(r"^\s*(?:export\s+)?[\w.\-]+\s*[:=]\s*\S|^\s*\[[\w. \-]+\]\s*$|^\s*[\w.\-]+:\s*$")
_CODE_LINE = re.compile(r"^\s*(?:def|class|import|from|if|for|while|return|try|except|with|elif|else|print|async)\b")


def looks_like_config(text: str) -> bool:
    """Vrai si le texte ressemble à un .env / .ini / .yaml (lignes clé=valeur) plutôt qu'à du code."""
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith(("#", ";", "//"))]
    if len(lines) < 2 or any(_CODE_LINE.match(l) for l in lines):
        return False
    matching = sum(1 for l in lines if _CONFIG_LINE.match(l))
    return matching / len(lines) >= 0.7


# ---------- Expressions ----------
# NOM (= | : | := | =>) "valeur"   (annotation de type permise : password: str = "x")
_ASSIGN_QUOTED = re.compile(
    r"""(?<![\w.\-])["']?(?P<name>[A-Za-z_][\w.\-]*)["']?"""
    r"""(?:[ \t]*:[ \t]*[\w\[\], .|]+?)?[ \t]*(?:==|=>|:=|=|:)[ \t]*(?P<val>""" + CONCAT + ")"
)
# Ligne de type .env / ini / yaml : NOM=valeur  ou  nom: valeur (sans guillemets)
_ASSIGN_BARE = re.compile(
    r"""^[ \t]*(?P<export>export[ \t]+)?(?P<name>[A-Za-z_][\w.\-]*)[ \t]*[:=][ \t]*(?P<val>[^\s#;'"`=][^\s#;]*)""",
    re.M,
)
# Chaîne de connexion : Password=xxx;  pwd=xxx  password=xxx (libpq)
_CONN_PAIR = re.compile(r"""(?i)(?<![\w.\-])(?P<name>password|passwd|pwd)=(?P<val>[^;\s'"`&,)]+)""")
# Option de ligne de commande : --password xxx   --token=xxx
_CLI_FLAG = re.compile(
    r"""(?i)(?<![\w])--(?:password|passwd|token|api-key|apikey|secret|access-token)(?:=|[ \t]+)(?P<val>[^\s'"`;&|]+)"""
)
_EXPRESSION_CHARS = re.compile(r"[()\[\]{}$<>]")


def _bare_value_ok(val: str) -> bool:
    val = val.rstrip(",")
    return len(val) >= 3 and not is_placeholder(val) and not _EXPRESSION_CHARS.search(val)


def _has_digit_or_symbol(val: str) -> bool:
    return any(c.isdigit() or (not c.isalnum() and c != "_") for c in val)


def find(text: str) -> list:
    findings = []

    # 1) NOM = "valeur"  (code, JSON, YAML entre guillemets...)
    for m in _ASSIGN_QUOTED.finditer(text):
        if not is_sensitive_name(m.group("name")):
            continue
        for s, e in inner_spans(text, m.start("val"), m.end("val")):
            if e - s >= 3 and not is_placeholder(text[s:e]):
                findings.append(Finding(s, e, "context", "named_value"))

    # 2) NOM=valeur sans guillemets (.env, ini, yaml, export shell)
    config_mode = looks_like_config(text)
    for m in _ASSIGN_BARE.finditer(text):
        if not is_sensitive_name(m.group("name")):
            continue
        val = m.group("val").rstrip(",")
        if not _bare_value_ok(val):
            continue
        if m.group("export") or config_mode or (len(val) >= 6 and _has_digit_or_symbol(val)):
            findings.append(Finding(m.start("val"), m.start("val") + len(val), "context", "bare_value"))

    # 3) Chaînes de connexion : Password=...
    for m in _CONN_PAIR.finditer(text):
        val = m.group("val")
        if not _bare_value_ok(val):
            continue
        after_semicolon = m.start() > 0 and text[m.start() - 1] == ";"
        if after_semicolon or (len(val) >= 6 and _has_digit_or_symbol(val)):
            findings.append(Finding(m.start("val"), m.end("val"), "context", "connection_string"))

    # 4) Options de ligne de commande
    for m in _CLI_FLAG.finditer(text):
        if _bare_value_ok(m.group("val")):
            findings.append(Finding(m.start("val"), m.end("val"), "context", "cli_flag"))

    return findings
