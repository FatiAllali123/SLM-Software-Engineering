import ast
from .schemas import AgentResponse
from .llm_protocol import LLMClient

def run_analysis(code: str, client: LLMClient) -> AgentResponse:
    try:
        tree = ast.parse(code)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        resultat = f"Analyse statique : {len(functions)} fonction(s) trouvée(s) -> {', '.join(functions)}." if functions else "Aucune fonction trouvée."
    except SyntaxError as e:
        return AgentResponse(agent="code_analysis", status="error", result="", error_message=f"Erreur de syntaxe : {str(e)}")

    prompt = f"Voici les fonctions extraites : {resultat}. Fais une analyse sémantique de ce code."
    response = client.generate(prompt)
    
    return AgentResponse(
        agent="code_analysis", status="ok",
        result=f"{resultat}\nAnalyse du modèle : {response.text}", # On combine ast + texte du modèle
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )