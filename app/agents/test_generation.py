import ast
from .schemas import AgentResponse
from .llm_protocol import LLMClient

def run_test_generation(code: str, client: LLMClient) -> AgentResponse:
    try:
        tree = ast.parse(code)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    except SyntaxError:
        return AgentResponse(agent="test_generation", status="error", result="", error_message="Erreur de syntaxe.")

    if not functions:
        return AgentResponse(agent="test_generation", status="ok", result="Aucune fonction à tester.", tokens_in=0, tokens_out=0, latency_s=0.1)

    prompt = f"Génère les tests unitaires pour ces fonctions : {', '.join(functions)}. Voici le code :\n{code}"
    response = client.generate(prompt)

    return AgentResponse(
        agent="test_generation", status="ok",
        result=response.text, # On renvoie ce que le modèle a généré
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )