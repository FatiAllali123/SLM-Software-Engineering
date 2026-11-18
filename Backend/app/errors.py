"""Codes d'erreur du backend (docs/api_contract.md, section 6)."""

# code d'erreur -> statut HTTP
ERROR_HTTP_STATUS = {
    "INVALID_INPUT": 400,
    "UNSUPPORTED_LANGUAGE": 400,
    "CODE_TOO_LARGE": 413,
    "TOOL_NOT_ALLOWED": 403,
    "SANDBOX_ERROR": 500,
    "MODEL_ERROR": 502,
    "INTERNAL_ERROR": 500,
}


class AppError(Exception):
    """Erreur prévue par le contrat. Les routes la lèvent, main.py la transforme en JSON."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    @property
    def http_status(self) -> int:
        return ERROR_HTTP_STATUS.get(self.code, 500)

    @property
    def status(self) -> str:
        # Un outil interdit est "blocked", les autres erreurs sont "error"
        return "blocked" if self.code == "TOOL_NOT_ALLOWED" else "error"
