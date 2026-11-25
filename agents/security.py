import re

class SecretFilter:
    """Filtre professionnel pour masquer les secrets avant l'envoi au LLM."""
    
    # Liste de motifs (Regex) pour détecter les secrets courants
    PATTERNS = [
        # Mots de passe (ex: password = "mon_super_mot_de_passe")
        (re.compile(r'(?i)(password|passwd|pwd)\s*=\s*["\']([^"\']+)["\']'), r'\1 = "[SECRET_MASQUÉ]"'),
        
        # Clés API (ex: api_key = "sk-1234567890abcdef")
        (re.compile(r'(?i)(api_key|apikey|secret_key|access_token)\s*=\s*["\']([^"\']+)["\']'), r'\1 = "[SECRET_MASQUÉ]"'),
        
        # Clés AWS (très spécifiques)
        (re.compile(r'(?i)(AKIA[0-9A-Z]{16})'), r'[SECRET_AWS_MASQUÉ]'),
        
        # Tokens GitHub (ex: ghp_1234567890abcdef)
        (re.compile(r'(ghp_[a-zA-Z0-9]{36})'), r'[SECRET_GITHUB_MASQUÉ]'),
        
        # Clés OpenAI (ex: sk-proj-1234567890)
        (re.compile(r'(sk-[a-zA-Z0-9]{20,})'), r'[SECRET_OPENAI_MASQUÉ]'),
        
        # Adresses email (pour éviter les fuites de données personnelles)
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), r'[EMAIL_MASQUÉ]')
    ]

    @classmethod
    def sanitize(cls, code: str) -> tuple[str, bool]:
        """
        Masque les secrets dans le code.
        Renvoie un tuple : (code_nettoyé, booléen_indiquant_si_un_secret_a_été_trouvé)
        """
        has_secret = False
        sanitized_code = code
        
        for pattern, replacement in cls.PATTERNS:
            if pattern.search(sanitized_code):
                has_secret = True
                sanitized_code = pattern.sub(replacement, sanitized_code)
                
        return sanitized_code, has_secret