from dataclasses import dataclass
from typing import Protocol

# Section 9 du contrat de Fati
@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str
    precision: str

class LLMClient(Protocol):
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        temperature: float = 0.0,
    ) -> LLMResponse:
        ...