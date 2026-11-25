import re

class PromptInjectionError(Exception):
    """Erreur levée quand une tentative d'injection de prompt est détectée."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
        self.code = "PROMPT_INJECTION_DETECTED"


class InjectionFilter:
    """Détecte les tentatives d'injection de prompt dans le code utilisateur."""
    
    # Patterns d'injection classiques (en anglais et en français)
    PATTERNS = [
        # 1. Tentatives d'ignorer les instructions
        re.compile(r'(?i)ignore\s+(all\s+)?(the\s+)?(previous|above|prior)\s+instructions'),
        re.compile(r'(?i)ignore\s+(les\s+)?instructions\s+(précédentes|ci-dessus)'),
        re.compile(r'(?i)oublie\s+(toutes\s+)?(les\s+)?instructions'),
        
        # 2. Tentatives de faire changer de rôle
        re.compile(r'(?i)(you\s+are\s+now|tu\s+es\s+maintenant|agis\s+comme)\s+(un|a|an|le)?\s*(admin|administrateur|root|system|système|hacker|pirate)'),
        
        # 3. Tentatives de révéler les instructions système
        re.compile(r'(?i)(reveal|affiche|montre|dis-moi)\s+(tes|your)\s+(instructions|prompts|règles|rules)'),
        
        # 4. Tentatives d'exécution de commandes (RCE classique en prompt injection)
        re.compile(r'(?i)(execute|exécute|run)\s+(the\s+)?(command|commande)\s*:?\s*(rm|sudo|curl|wget|bash|sh)'),
        
        # 5. Tentatives de "jailbreak"
        re.compile(r'(?i)(DAN|jailbreak|developer\s+mode|mode\s+développeur|bypass\s+restrictions)')
    ]

    @classmethod
    def scan(cls, code: str) -> None:
        """
        Analyse le code pour détecter les injections de prompt.
        Lève une PromptInjectionError si une tentative est détectée.
        """
        for pattern in cls.PATTERNS:
            if pattern.search(code):
                raise PromptInjectionError(
                    f"Tentative d'injection de prompt détectée. Motif interdit : {pattern.pattern[:50]}..."
                )