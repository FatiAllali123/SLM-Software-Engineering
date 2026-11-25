"""Types communs du filtre de secrets."""
from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    """Un secret repéré : positions [start, end) dans le texte, couche et type."""
    start: int
    end: int
    layer: str   # format, url, context, fragment, encoding, entropy
    kind: str    # ex. openai_key, url_credentials, password_assignment...


@dataclass
class FilterResult:
    text: str                                   # texte avec les secrets masqués
    findings: list = field(default_factory=list)
    suspects: int = 0                           # chaînes "suspectes" NON masquées (entropie seule)

    @property
    def count(self) -> int:
        return len(self.findings)

    @property
    def by_layer(self) -> dict:
        return dict(Counter(f.layer for f in self.findings))
