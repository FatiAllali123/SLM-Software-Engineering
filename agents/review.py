import ast
from .schemas import AgentResponse
from .llm_protocol import LLMClient

def run_review(code: str, client: LLMClient) -> AgentResponse:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return AgentResponse(agent="code_review", status="error", result="", error_message=f"Erreur de syntaxe : {str(e)}")

    prompt = f"Fais une revue de ce code Python :\n{code}"
    response = client.generate(prompt)

    return AgentResponse(
        agent="code_review", status="ok",
        result=response.text, # On renvoie la revue du modèle
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )