from .schemas import AgentResponse
from .llm_client_stub import LLMClientStub

def run_review(code: str, client: LLMClientStub) -> AgentResponse:
    prompt = f"Fais une revue de code pour ce fichier :\n\n{code}"
    response = client.generate([{"role": "user", "content": prompt}])
    
    return AgentResponse(
        agent="code_review",
        status="ok",
        result=response["text"],
        tokens_in=response["tokens_in"],
        tokens_out=response["tokens_out"],
        latency_s=response["latency_s"]
    )