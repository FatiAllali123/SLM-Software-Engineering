import time
from .llm_protocol import LLMResponse

class LLMClientStub:
    def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.0) -> LLMResponse:
        """Simule un appel LLM en acceptant une simple chaîne de caractères."""
        start_time = time.time()
        time.sleep(0.1)
        
        # Le prompt est maintenant une chaîne, pas une liste
        response_text = f"Réponse simulée pour : {prompt[:30]}..."
        latency = time.time() - start_time
        
        return LLMResponse(
            text=response_text,
            input_tokens=len(prompt.split()),
            output_tokens=len(response_text.split()),
            latency_ms=int(latency * 1000),
            model="stub",
            precision="none"
        )