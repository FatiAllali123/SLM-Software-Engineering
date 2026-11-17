from .schemas import AgentResponse
from .llm_client_stub import LLMClientStub

def run_analysis(code: str, client: LLMClientStub) -> AgentResponse:
    prompt = f"Analyse ce code et liste ses composants :\n\n{code}"
    response = client.generate([{"role": "user", "content": prompt}])
    
    return AgentResponse(
        agent="code_analysis",
        status="ok",
        result=response["text"],
        tokens_in=response["tokens_in"],
        tokens_out=response["tokens_out"],
        latency_s=response["latency_s"]
    )