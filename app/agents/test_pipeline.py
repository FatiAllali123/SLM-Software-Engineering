import pytest
from .llm_protocol import LLMResponse
from .pipeline import run_pipeline, AgentInvalidInputError

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

def test_run_pipeline_invalid_input_raises_exception():
    """Vérifie que le pipeline lève bien AgentInvalidInputError pour un code invalide."""
    llm = FakeLLM()
    
    # On vérifie que l'appel lève bien l'exception attendue
    with pytest.raises(AgentInvalidInputError) as exc_info:
        run_pipeline(
            task="analyze", 
            code="def broken(:",  # Code invalide
            language="python", 
            mode="single_agent", 
            llm=llm
        )
    
    # On vérifie que le message d'erreur est correct
    assert "Erreur de syntaxe" in str(exc_info.value)

def test_format_result_for_backend_analyze():
    """Vérifie que le pipeline extrait bien les issues du texte."""
    from .pipeline import format_result_for_backend
    
    # On simule ce que renvoie l'agent d'analyse
    raw_result = str({"issues": [{"line": 5, "severity": "low", "category": "quality", "message": "Test"}], "summary": "Ok"})
    formatted = format_result_for_backend("analyze", raw_result)
    
    assert "issues" in formatted
    assert len(formatted["issues"]) == 1
    assert formatted["issues"][0]["line"] == 5