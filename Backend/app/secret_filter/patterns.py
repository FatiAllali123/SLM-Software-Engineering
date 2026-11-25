"""NIVEAU 1 : formats connus de secrets (expressions régulières).

Pour ajouter un format : une ligne dans _PATTERNS (nom, expression, numéro du groupe à masquer).
"""
import re

from .models import Finding

_NOT_WORD = r"(?<![A-Za-z0-9_])"

_PATTERNS = [
    # Clés privées (bloc complet ; si la fin manque, on masque jusqu'à la fin du texte)
    ("private_key", re.compile(
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"
        r"(?:[\s\S]*?-----END (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----|[\s\S]*\Z)"), 0),
    # OpenAI / Anthropic : sk-..., sk-proj-..., sk-ant-... (au moins un chiffre : évite les classes CSS "sk-...")
    ("openai_key", re.compile(_NOT_WORD + r"sk-(?=[A-Za-z0-9_\-]{0,80}\d)[A-Za-z0-9_\-]{20,}"), 0),
    # GitHub
    ("github_token", re.compile(_NOT_WORD + r"gh[pousr]_[A-Za-z0-9]{36,}"), 0),
    ("github_pat", re.compile(_NOT_WORD + r"github_pat_[A-Za-z0-9_]{22,}"), 0),
    # AWS (identifiant d'accès ; la clé secrète est repérée par le contexte)
    ("aws_access_key", re.compile(
        r"(?<![A-Z0-9])(?:AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|AROA)[A-Z0-9]{16}(?![A-Z0-9])"), 0),
    # Google, Slack, Stripe, Hugging Face, npm, SendGrid, Telegram
    ("google_api_key", re.compile(_NOT_WORD + r"AIza[0-9A-Za-z_\-]{35}"), 0),
    ("slack_token", re.compile(_NOT_WORD + r"xox[abprs]-[A-Za-z0-9\-]{10,}"), 0),
    ("stripe_key", re.compile(_NOT_WORD + r"[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"), 0),
    ("huggingface_token", re.compile(_NOT_WORD + r"hf_[A-Za-z0-9]{30,}"), 0),
    ("npm_token", re.compile(_NOT_WORD + r"npm_[A-Za-z0-9]{36}"), 0),
    ("sendgrid_key", re.compile(_NOT_WORD + r"SG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}"), 0),
    ("telegram_bot_token", re.compile(r"(?<![0-9])\d{8,10}:[A-Za-z0-9_\-]{35}(?![A-Za-z0-9_\-])"), 0),
    # JWT (trois blocs séparés par des points, les deux premiers commencent par eyJ)
    ("jwt", re.compile(_NOT_WORD + r"eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), 0),
    # En-têtes d'authentification : on masque le jeton, on garde le mot "Bearer"/"Basic"
    ("bearer_token", re.compile(r"(?i)\bBearer[ \t]+([A-Za-z0-9\-._~+/]{16,}=*)"), 1),
    ("basic_auth", re.compile(
        r"(?i)\bauthorization[\"']?[ \t]*[:=][ \t]*[\"']?Basic[ \t]+([A-Za-z0-9+/]{8,}={0,2})"), 1),
]


def find_known(text: str) -> list:
    findings = []
    for kind, regex, group in _PATTERNS:
        for m in regex.finditer(text):
            if m.end(group) > m.start(group):
                findings.append(Finding(m.start(group), m.end(group), "format", kind))
    return findings


# ---------- Valeurs qui ne sont PAS de vrais secrets (modèles, références) ----------
_PLACEHOLDER_WORDS = {
    "none", "null", "nil", "true", "false", "yes", "no", "required", "optional", "redacted",
    "secret", "password", "token", "string", "str", "todo", "tbd", "undefined", "empty",
    "default", "n/a", "na", "basic", "bearer", "digest", "oauth", "oauth2",
}
_PLACEHOLDER_RES = [
    re.compile(r"^<[^>]*>$"),                    # <password>
    re.compile(r"^\$\{?[A-Za-z_][\w:\-]*\}?$"),  # $VAR  ${VAR}
    re.compile(r"^\{\{.*\}\}$"),                 # {{ var }}
    re.compile(r"^%\(\w+\)s$|^%s$"),             # %(var)s
    re.compile(r"^(.)\1{2,}$"),                  # xxxx  ****  ....
    re.compile(r"(?i)^(your|my)[_\- ]"),         # your-api-key-here
    re.compile(r"(?i)[_\- ](here|goes[_\- ]here)$"),
    re.compile(r"(?i)placeholder|dummy|changeme|redacted|secret_masqu"),
]
_FORMAT_FIELD = re.compile(r"\{[^{}]*\}")      # f"{token}" : référence, pas une valeur


def is_placeholder(value: str) -> bool:
    v = value.strip()
    if not v or v.lower() in _PLACEHOLDER_WORDS:
        return True
    if _FORMAT_FIELD.search(v):
        return True
    return any(r.search(v) for r in _PLACEHOLDER_RES)
