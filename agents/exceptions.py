class ToolNotAllowedError(Exception):
    """Erreur levée quand un agent tente d'utiliser un outil hors de la liste blanche."""
    def __init__(self, tool_name: str):
        super().__init__(f"L'outil '{tool_name}' n'est pas autorisé.")
        self.tool_name = tool_name
        self.code = "TOOL_NOT_ALLOWED"