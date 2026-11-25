import pytest
from .pipeline import run_pipeline
from .llm_protocol import LLMResponse

class FakeLLM:
    def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.0) -> LLMResponse:
        assert isinstance(prompt, str), "Le prompt doit être une chaîne de caractères !"
        return LLMResponse(
            text="Fake response", input_tokens=10, output_tokens=5, 
            latency_ms=100, model="fake", precision="none"
        )

def test_run_pipeline_analyze_single():
    llm = FakeLLM()
    res = run_pipeline(task="analyze", code="def foo(): pass", language="python", mode="single_agent", llm=llm)
    
    assert "result" in res
    assert "metrics" in res
    assert "trace" in res
    assert res["result"]["issues"] is not None
    assert res["metrics"]["llm_calls"] == 1
    assert len(res["trace"]) == 1

def test_run_pipeline_multi_agent():
    llm = FakeLLM()
    res = run_pipeline(task="analyze", code="def foo(): pass", language="python", mode="multi_agent", llm=llm)
    
    # Le graphe fait 3 appels LLM (analyse, tests, revue)
    assert res["metrics"]["llm_calls"] == 3
    assert len(res["trace"]) == 3
    assert res["trace"][0]["agent"] == "code_analysis"