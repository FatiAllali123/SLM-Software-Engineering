import ast
from .schemas import AgentResponse
from .llm_client_stub import LLMClientStub

def run_review(code: str, client: LLMClientStub) -> AgentResponse:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return AgentResponse(
            agent="code_review",
            status="error",
            result="",
            error_message=f"Impossible de faire la revue : erreur de syntaxe ({str(e)})."
        )

    issues = []

    # 1. Chercher les 'print()' (non recommandé en prod)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'print':
                issues.append("Utilisation de 'print()' détectée. Envisagez un module de logging.")

    # 2. Chercher les fonctions sans docstring
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if not ast.get_docstring(node):
                issues.append(f"La fonction '{node.name}' n'a pas de docstring.")

    # 3. Chercher les 'except:' nus (bare except)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                issues.append("Utilisation d'un 'except:' nu détectée. Précisez l'exception (ex: except ValueError:).")

    # On formate le résultat
    if not issues:
        review_result = "Code Review : Aucun problème majeur détecté (selon les règles de base)."
    else:
        review_result = "Code Review : Problèmes détectés :\n"
        for i, issue in enumerate(issues, 1):
            review_result += f"{i}. {issue}\n"

    # On simule l'appel IA pour les métriques (tokens, latence)
    prompt = f"Fais une revue de code. Problèmes trouvés : {len(issues)}"
    response = client.generate([{"role": "user", "content": prompt}])

    return AgentResponse(
        agent="code_review",
        status="ok",
        result=review_result.strip(),
        tokens_in=response["tokens_in"],
        tokens_out=response["tokens_out"],
        latency_s=response["latency_s"]
    )