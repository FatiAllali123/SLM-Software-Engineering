import os
import pytest
from .llm_client_stub import LLMClientStub
from .schemas import AgentRequest
from .analysis import run_analysis
from .graph import run_graph

def test_agent_response_format():
    """Vérifie que l'agent d'analyse respecte bien le format JSON demandé."""
    client = LLMClientStub()
    response = run_analysis("def hello(): pass", client)
    
    # Vérifications du contrat JSON
    assert response.agent == "code_analysis"
    assert response.status == "ok"
    assert response.tokens_in > 0
    assert response.tokens_out > 0
    assert response.latency_s > 0
    assert response.needs_approval is False

def test_graph_multi_agent():
    """Vérifie que le graphe multi-agent renvoie bien 3 réponses."""
    os.environ["MULTI_AGENT"] = "true"
    request = AgentRequest(code="def test(): pass", task_id="test1")
    results = run_graph(request)
    
    assert len(results) == 3
    assert results[0]["agent"] == "code_analysis"
    assert results[1]["agent"] == "test_generation"
    assert results[2]["agent"] == "code_review"

def test_graph_single_agent():
    """Vérifie que le mode single-agent fonctionne (pour Q3)."""
    os.environ["MULTI_AGENT"] = "false"
    request = AgentRequest(code="def test(): pass", task_id="test2")
    results = run_graph(request)
    
    assert len(results) == 3 # Il fait les 3 tâches, mais via un seul noeud