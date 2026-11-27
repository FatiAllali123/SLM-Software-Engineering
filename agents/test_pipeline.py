import pytest
from .pipeline import run_pipeline, AgentInvalidInputError
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
    # Le graphe fait 4 appels LLM (analyse, tests, documentation, revue)
    assert res["metrics"]["llm_calls"] == 4
    assert len(res["trace"]) == 4
    assert res["trace"][0]["agent"] == "code_analysis"


def test_run_pipeline_invalid_input_raises_exception():
    """Vérifie que le pipeline lève bien AgentInvalidInputError pour un code invalide."""
    llm = FakeLLM()
    with pytest.raises(AgentInvalidInputError) as exc_info:
        run_pipeline(
            task="analyze",
            code="def broken(:",
            language="python",
            mode="single_agent",
            llm=llm
        )
    assert "Erreur de syntaxe" in str(exc_info.value)


def test_tool_not_allowed():
    """Vérifie que l'exception ToolNotAllowedError est bien levée si on retire un outil de la liste blanche."""
    from .exceptions import ToolNotAllowedError
    from . import pipeline as pipeline_module

    llm = FakeLLM()

    # On sauvegarde la vraie liste et on la vide temporairement pour simuler un outil interdit
    original_allowed = pipeline_module.ALLOWED_TOOLS
    pipeline_module.ALLOWED_TOOLS = set()  # Plus aucun outil autorisé

    try:
        with pytest.raises(ToolNotAllowedError):
            run_pipeline(
                task="analyze",
                code="print('hello')",
                language="python",
                mode="single_agent",
                llm=llm
            )
    finally:
        # On restaure la liste pour ne pas impacter les autres tests
        pipeline_module.ALLOWED_TOOLS = original_allowed


def test_run_pipeline_filters_secrets():
    """Vérifie que le pipeline masque les secrets avant d'appeler les agents."""
    from .security import SecretFilter

    code_with_secret = '''
def connect():
    password = "mon_mot_de_passe_secret"
    api_key = "sk-1234567890abcdef1234567890"
    return True
'''
    sanitized, has_secret = SecretFilter.sanitize(code_with_secret)

    assert has_secret is True
    assert "mon_mot_de_passe_secret" not in sanitized
    assert "[SECRET_MASQUÉ]" in sanitized
    assert "sk-1234567890abcdef1234567890" not in sanitized


def test_format_result_for_backend_analyze():
    """Vérifie que le pipeline extrait bien les issues du texte."""
    from .pipeline import format_result_for_backend

    raw_result = str({"issues": [{"line": 5, "severity": "low", "category": "quality", "message": "Test"}], "summary": "Ok"})
    formatted = format_result_for_backend("analyze", raw_result)

    assert "issues" in formatted
    assert len(formatted["issues"]) == 1
    assert formatted["issues"][0]["line"] == 5
def test_agent_logger_writes_to_file():
    """Vérifie que le logger écrit bien dans le fichier JSONL."""
    from .logger import AgentLogger
    import os
    import json
    
    # On utilise un dossier temporaire pour ne pas polluer les vrais logs
    test_logger = AgentLogger(log_dir="logs_test")
    test_logger.log_step("test_agent", "test_step", {"info": "test"})
    
    assert os.path.exists("logs_test/agent_traces.jsonl")
    
    with open("logs_test/agent_traces.jsonl", "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) > 0
        last_line = json.loads(lines[-1])
        assert last_line["agent"] == "test_agent"
        assert last_line["step"] == "test_step"
    
    # Nettoyage
    os.remove("logs_test/agent_traces.jsonl")
    os.rmdir("logs_test")