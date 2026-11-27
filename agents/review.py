import ast
from .schemas import AgentResponse
from .llm_protocol import LLMClient
from .prompts import REVIEW_PROMPT_TEMPLATE

def run_review(code: str, client: LLMClient) -> AgentResponse:
    try:
        ast.parse(code)
    except SyntaxError as e:
        return AgentResponse(
            agent="code_review", status="error", result="", 
            error_message=f"Erreur de syntaxe ligne {e.lineno} : {e.msg}"
        )

    prompt = REVIEW_PROMPT_TEMPLATE.format(code=code)
    
    response = client.generate(prompt)

    return AgentResponse(
        agent="code_review", status="ok",
        result=response.text,
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )