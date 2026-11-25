import ast
from .schemas import AgentResponse
from .llm_protocol import LLMClient

def run_documentation(code: str, client: LLMClient) -> AgentResponse:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return AgentResponse(
            agent="documentation", status="error", result="", 
            error_message=f"Erreur de syntaxe ligne {e.lineno} : {e.msg}"
        )

    # 1. On extrait les fonctions qui n'ont pas de docstring
    functions_without_docstring = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if not ast.get_docstring(node):
                functions_without_docstring.append(node.name)

    if not functions_without_docstring:
        return AgentResponse(
            agent="documentation", status="ok", 
            result="Toutes les fonctions ont déjà une docstring. Rien à générer.",
            tokens_in=0, tokens_out=0, latency_s=0.1
        )

    # 2. On demande au LLM de générer la documentation
    prompt = f"""
    Voici un code Python. Les fonctions suivantes n'ont pas de docstring : {', '.join(functions_without_docstring)}.
    Génère une docstring pertinente pour chacune de ces fonctions, au format Google Style (Args, Returns).
    Voici le code :
    {code}
    """
    
    response = client.generate(prompt)
    
    return AgentResponse(
        agent="documentation", status="ok",
        result=response.text,  # La doc générée par le LLM
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )