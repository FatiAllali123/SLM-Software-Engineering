import ast
from .schemas import AgentResponse
from .llm_client_stub import LLMClientStub

def run_test_generation(code: str, client: LLMClientStub) -> AgentResponse:
    try:
        tree = ast.parse(code)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    except SyntaxError:
        return AgentResponse(
            agent="test_generation",
            status="error",
            result="",
            error_message="Impossible de générer des tests : le code source contient une erreur de syntaxe."
        )

    if not functions:
        return AgentResponse(
            agent="test_generation",
            status="ok",
            result="Aucune fonction trouvée. Impossible de générer des tests.",
            tokens_in=0, tokens_out=0, latency_s=0.1
        )

    # On construit le squelette du fichier de test (format pytest)
    test_lines = ["import pytest"]
    # On ajoute un import factice pour l'exemple (dans un vrai projet, on importerait le module)
    test_lines.append("# from my_module import " + ", ".join(functions) + "\n")
    
    for func in functions:
        test_lines.append(f"def test_{func}():")
        test_lines.append(f"    # TODO: Écrire un test pour {func}")
        test_lines.append("    assert True\n")

    generated_code = "\n".join(test_lines)

    # On passe par le stub pour simuler les métriques (tokens, latence)
    prompt = f"Génère les tests pour : {', '.join(functions)}"
    response = client.generate([{"role": "user", "content": prompt}])

        
    return AgentResponse(
        agent="test_generation",
        status="ok",
        result=generated_code,
        tokens_in=response.input_tokens,       
        tokens_out=response.output_tokens,    
        latency_s=response.latency_ms / 1000.0 
    )