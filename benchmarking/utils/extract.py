"""Extraction du code depuis la reponse d'un modele. COMMUN aux 4 membres."""
import re


def extract_code(text: str) -> str:
    """Retourne le contenu du premier bloc ```python ... ```.
    Si aucun bloc n'existe, retourne le texte tel quel."""
    blocks = re.findall(r"```[a-zA-Z0-9_+-]*[ \t]*\n(.*?)```", text, re.DOTALL)
    if blocks:
        return blocks[0]
    # bloc ouvert mais jamais ferme (reponse coupee par max_new_tokens)
    m = re.search(r"```[a-zA-Z0-9_+-]*[ \t]*\n(.*)", text, re.DOTALL)
    return m.group(1) if m else text
