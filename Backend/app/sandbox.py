"""Bac à sable d'exécution du code.

VERSION FICTIVE (étape 1B) : cette fonction N'EXÉCUTE RIEN. Exécuter du code
sans isolation serait dangereux. Le vrai bac à sable (conteneur Docker sans réseau,
10 s, 256 Mo...) remplacera le corps de run_code() à l'étape 4.
Le reste du backend n'aura pas besoin de changer.
"""
from .schemas import ExecuteResult


def run_code(code: str, timeout_s: int) -> ExecuteResult:
    return ExecuteResult(
        stdout="[exécution fictive : le code n'a pas été lancé]\n",
        stderr="",
        exit_code=0,
        timed_out=False,
        duration_ms=0,
    )
