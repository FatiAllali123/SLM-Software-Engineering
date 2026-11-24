"""Quelle "task" du contrat correspond à quelle porte (utilisé par main.py et le journal d'audit)."""

TASK_BY_PATH = {
    "/analyze": "analyze",
    "/generate-tests": "generate_tests",
    "/review": "review",
    "/execute": "execute",
}
