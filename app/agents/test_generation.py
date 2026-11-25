import ast
from .schemas import AgentResponse
from .llm_protocol import LLMClient

class PytestSkeletonGenerator(ast.NodeVisitor):
    """Génère un squelette de test pytest intelligent à partir du code source."""
    def __init__(self):
        self.test_code = "import pytest\n\n"
        self.function_names = []

    def visit_FunctionDef(self, node):
        self.function_names.append(node.name)
        
        # On récupère les arguments de la fonction (sans 'self' ni 'cls')
        args = [arg.arg for arg in node.args.args if arg.arg not in ('self', 'cls')]
        args_str = ", ".join(args)
        
        # On génère un squelette de test propre
        self.test_code += f"def test_{node.name}():\n"
        if args:
            # On met des valeurs par défaut pour que ça compile
            default_args = ", ".join(["0" for _ in args])
            self.test_code += f"    # TODO: remplacer les 0 par de vraies valeurs\n"
            self.test_code += f"    result = {node.name}({default_args})\n"
            self.test_code += f"    assert result is not None\n\n"
        else:
            self.test_code += f"    result = {node.name}()\n"
            self.test_code += f"    assert result is not None\n\n"
        
        self.generic_visit(node)

def run_test_generation(code: str, client: LLMClient) -> AgentResponse:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return AgentResponse(
            agent="test_generation", status="error", result="", 
            error_message=f"Erreur de syntaxe ligne {e.lineno} : {e.msg}"
        )

    # 1. On génère le squelette Python (qui compile à coup sûr)
    generator = PytestSkeletonGenerator()
    generator.visit(tree)

    if not generator.function_names:
        return AgentResponse(
            agent="test_generation", status="ok", 
            result="Aucune fonction trouvée. Impossible de générer des tests.",
            tokens_in=0, tokens_out=0, latency_s=0.1
        )

    # 2. On demande au LLM de compléter ce squelette (pas de générer depuis zéro)
    prompt = f"""
    Voici un squelette de tests pytest généré automatiquement pour ce code :
    {generator.test_code}
    
    Complète ce squelette en remplaçant les 'TODO' et les '0' par de vraies valeurs de test pour les fonctions {', '.join(generator.function_names)}.
    Renvoie UNIQUEMENT le code Python final, sans aucune explication textuelle.
    """
    
    response = client.generate(prompt)
    
    # 3. On renvoie le résultat final (idéalement, c'est le LLM qui a complété, mais le squelette est déjà valide)
    final_tests = response.text if response.text else generator.test_code

    return AgentResponse(
        agent="test_generation", status="ok",
        result=final_tests,
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )