from .schemas import AgentResponse
from .llm_client_stub import LLMClientStub

def run_test_generation(code: str, client: LLMClientStub) -> AgentResponse:
    prompt = f"Génère des tests unitaires en pytest pour ce code :\n\n{code}"
    response = client.generate([{"role": "user", "content": prompt}])
    
    return AgentResponse(
        agent="test_generation",
        status="ok",
        result=response["text"],
        tokens_in=response["tokens_in"],
        tokens_out=response["tokens_out"],
        latency_s=response["latency_s"]
    )