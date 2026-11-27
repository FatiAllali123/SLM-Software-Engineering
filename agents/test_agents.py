import pytest
from .llm_client_stub import LLMClientStub
from .schemas import AgentRequest
from .analysis import run_analysis
from .test_generation import run_test_generation, PytestSkeletonGenerator
from .review import run_review
from .graph import run_multi_agent
from .pipeline import run_pipeline
import ast

def test_agent_response_format():
    """Vérifie que l'agent d'analyse respecte bien le format JSON demandé."""
    client = LLMClientStub()
    response = run_analysis("def hello(): pass", client)
    
    assert response.agent == "code_analysis"
    assert response.status == "ok"
    assert response.tokens_in > 0
    assert response.tokens_out > 0
    assert response.latency_s > 0
    assert response.needs_approval is False

def test_graph_multi_agent():
    """Vérifie que le graphe multi-agent renvoie bien 4 réponses (analyse, tests, doc, revue)."""
    client = LLMClientStub()
    results = run_multi_agent("def test(): pass", client)
    
    assert len(results) == 4  # <-- 4 maintenant
    assert results[0].agent == "code_analysis"
    assert results[1].agent == "test_generation"
    assert results[2].agent == "documentation" # <-- Nouveau
    assert results[3].agent == "code_review"

def test_graph_single_agent():
    """Vérifie que le mode single-agent fonctionne (pour Q3)."""
    client = LLMClientStub()
    res = run_pipeline(task="analyze", code="def test(): pass", language="python", mode="single_agent", llm=client)
    
    assert len(res["trace"]) == 1
    assert res["metrics"]["llm_calls"] == 1

def test_analysis_real_code():
    """Vérifie que l'agent d'analyse extrait vraiment les fonctions."""
    client = LLMClientStub()
    code = """
def addition(a, b):
    return a + b

def salutation(nom):
    print("Bonjour " + nom)
"""
    response = run_analysis(code, client)
    
    assert response.status == "ok"
    assert len(response.result) > 0

def test_analysis_invalid_code():
    """Vérifie que l'agent gère bien les erreurs de syntaxe."""
    client = LLMClientStub()
    code = "def ma_fonction( :" # Code invalide volontaire
    response = run_analysis(code, client)
    
    assert response.status == "error"
    assert "Erreur de syntaxe" in response.error_message

def test_generation_real_code():
    """Vérifie que le générateur de squelette crée les bons noms de fonctions."""
    code = """
def addition(a, b):
    return a + b

def salutation(nom):
    print("Bonjour " + nom)
"""
    tree = ast.parse(code)
    generator = PytestSkeletonGenerator()
    generator.visit(tree)
    
    assert "def test_addition():" in generator.test_code
    assert "def test_salutation():" in generator.test_code
    assert "import pytest" in generator.test_code

def test_generation_real_code_with_stub():
    """Vérifie que l'agent renvoie le squelette sûr quand le stub génère du faux texte."""
    client = LLMClientStub()
    code = "def addition(a, b):\n    return a + b"
    response = run_test_generation(code, client)
    
    assert response.status == "ok"
    # Le stub renvoie du texte invalide, donc l'agent garde le squelette sûr (qui contient 'import pytest')
    assert "import pytest" in response.result
    assert "def test_addition():" in response.result
    assert "Réponse simulée" not in response.result # Le texte du stub a été rejeté
def test_generation_invalid_code():
    """Vérifie la gestion d'erreur si le code est invalide."""
    client = LLMClientStub()
    response = run_test_generation("def broken(:", client)
    
    assert response.status == "error"
    assert "Erreur de syntaxe" in response.error_message

def test_review_finds_issues():
    """Vérifie que l'agent de revue renvoie bien un résultat pour un code avec des problèmes."""
    client = LLMClientStub()
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
    assert len(response.result) > 0
    assert response.tokens_in > 0

def test_review_clean_code():
    """Vérifie que l'agent de revue renvoie un résultat pour un code propre."""
    client = LLMClientStub()
    code = '''
def good_function():
    """Ceci est une bonne docstring."""
    return 42
'''
    response = run_review(code, client)
    
    assert response.status == "ok"
    assert len(response.result) > 0
def test_generation_validates_llm_output():
    """Vérifie que l'agent rejette le code LLM invalide et garde le squelette sûr."""
    from .llm_protocol import LLMResponse
    
    class BadLLM:
        """Un faux LLM qui génère du code invalide (il manque une parenthèse)."""
        def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.0) -> LLMResponse:
            return LLMResponse(
                text="def test_addition(:\n    assert True", # Invalide !
                input_tokens=10, output_tokens=5, latency_ms=100, model="bad", precision="none"
            )
    
    code = "def addition(a, b):\n    return a + b"
    response = run_test_generation(code, BadLLM())
    
    # L'agent ne doit pas planter, et doit renvoyer le squelette sûr (qui contient 'import pytest')
    assert response.status == "ok"
    assert "import pytest" in response.result # C'est le squelette de secours
    assert "def test_addition(:" not in response.result # Le code invalide a été rejeté

def test_analysis_retry_on_invalid_json():
    """Vérifie que l'agent d'analyse fait un retry si le premier LLM renvoie du texte invalide."""
    from .llm_protocol import LLMResponse
    
    class RetryLLM:
        """Un faux LLM qui renvoie d'abord du texte invalide, puis un JSON valide."""
        def __init__(self):
            self.calls = 0
            
        def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.0) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(text="Voici mon analyse : le code est correct.", input_tokens=10, output_tokens=10, latency_ms=100, model="fake", precision="none")
            else:
                return LLMResponse(text='{"issues": [], "summary": "Analyse par retry réussie."}', input_tokens=15, output_tokens=15, latency_ms=150, model="fake", precision="none")
    
    client = RetryLLM()
    response = run_analysis("def foo(): pass", client)
    
    # On vérifie que 2 appels ont été faits (le premier + le retry)
    assert client.calls == 2
    # On vérifie que le résultat est bien le JSON valide
    assert "Analyse par retry réussie" in response.result
    # On vérifie que les tokens sont bien la somme des deux appels
    assert response.tokens_in == 25