import ast
from .schemas import AgentResponse
from .llm_protocol import LLMClient
from .prompts import DOCUMENTATION_PROMPT_TEMPLATE

def run_documentation(code: str, client: LLMClient) -> AgentResponse:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return AgentResponse(
            agent="documentation", status="error", result="", 
            error_message=f"Erreur de syntaxe ligne {e.lineno} : {e.msg}"
        )

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

    prompt = DOCUMENTATION_PROMPT_TEMPLATE.format(
        functions_without_docstring=", ".join(functions_without_docstring),
        code=code
    )
    
    response = client.generate(prompt)
    
    return AgentResponse(
        agent="documentation", status="ok",
        result=response.text,
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )