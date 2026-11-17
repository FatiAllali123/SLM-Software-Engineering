import os
import pytest
from .llm_client_stub import LLMClientStub
from .schemas import AgentRequest
from .analysis import run_analysis
from .graph import run_graph
from .test_generation import run_test_generation
from .review import run_review

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


def test_analysis_real_code():
    """
    Vérifie que l'agent d'analyse extrait vraiment les fonctions.
    """
    client = LLMClientStub()
    code = """
def addition(a, b):
    return a + b

def salutation(nom):
    print("Bonjour " + nom)
"""
    response = run_analysis(code, client)
    
    assert response.status == "ok"
    assert "2 fonction(s)" in response.result
    assert "addition" in response.result
    assert "salutation" in response.result

def test_analysis_invalid_code():
    """Vérifie que l'agent gère bien les erreurs de syntaxe."""
    client = LLMClientStub()
    code = "def ma_fonction( :" # Code invalide volontaire
    response = run_analysis(code, client)
    
    assert response.status == "error"
    assert "Erreur de syntaxe" in response.error_message

def test_generation_real_code():
    """Vérifie que l'agent génère un squelette pytest valide."""
    client = LLMClientStub()
    code = """
def addition(a, b):
    return a + b
"""
    response = run_test_generation(code, client)
    
    assert response.status == "ok"
    assert "def test_addition():" in response.result
    assert "import pytest" in response.result

def test_generation_invalid_code():
    """Vérifie la gestion d'erreur si le code est invalide."""
    client = LLMClientStub()
    response = run_test_generation("def broken(:", client)
    
    assert response.status == "error"
    assert "erreur de syntaxe" in response.error_message
def test_review_finds_issues():
    """Vérifie que l'agent de revue détecte bien les mauvaises pratiques."""
    client = LLMClientStub()
    # Ce code a un print, une fonction sans docstring, et un except nu
    code = """
def bad_function():
    print("hello")
    try:
        pass
    except:
        pass
"""
    response = run_review(code, client)
    
    assert response.status == "ok"
    assert "print()" in response.result
    assert "n'a pas de docstring" in response.result
    assert "except:" in response.result

def test_review_clean_code():
    """Vérifie que l'agent ne trouve rien dans un code propre."""
    client = LLMClientStub()
    code = '''
def good_function():
    """Ceci est une bonne docstring."""
    return 42
'''
    response = run_review(code, client)
    
    assert response.status == "ok"
    assert "Aucun problème majeur" in response.result