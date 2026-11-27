class ToolNotAllowedError(Exception):
    """Erreur levée quand un agent tente d'utiliser un outil hors de la liste blanche."""
    def __init__(self, tool_name: str):
        super().__init__(f"L'outil '{tool_name}' n'est pas autorisé.")
        self.tool_name = tool_name
        self.code = "TOOL_NOT_ALLOWED"


class AgentInvalidInputError(Exception):
    """Erreur levée quand le code fourni est invalide (syntaxe)."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
        self.code = "INVALID_INPUT"


class LLMOutputParseError(Exception):
    """Erreur levée quand le LLM renvoie un texte qui n'est pas un JSON valide."""
    def __init__(self, raw_text: str):
        super().__init__(f"Le texte du LLM n'est pas un JSON valide : {raw_text[:50]}...")
        self.raw_text = raw_text
        self.code = "LLM_OUTPUT_PARSE_ERROR"