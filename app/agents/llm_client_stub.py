import time
from .llm_protocol import LLMResponse

class LLMClientStub:
    def generate(self, messages: list, max_new_tokens: int = 512, temperature: float = 0.0) -> LLMResponse:
        """Simule un appel LLM et renvoie un objet LLMResponse conforme au contrat."""
        start_time = time.time()
        time.sleep(0.1) # Petit délai pour simuler
        
        prompt = messages[-1]["content"] if isinstance(messages, list) else str(messages)
        response_text = f"Stub analysis for: {prompt[:30]}..."
        
        latency = time.time() - start_time
        
        return LLMResponse(
            text=response_text,
            input_tokens=len(prompt.split()),
            output_tokens=len(response_text.split()),
            latency_ms=int(latency * 1000),
            model="stub",
            precision="none"
        )