import ast
from .schemas import AgentResponse
from .llm_protocol import LLMClient
from .prompts import TEST_GENERATION_PROMPT_TEMPLATE

class PytestSkeletonGenerator(ast.NodeVisitor):
    """Génère un squelette de test pytest intelligent à partir du code source."""
    def __init__(self):
        self.test_code = "import pytest\n\n"
        self.function_names = []

    def visit_FunctionDef(self, node):
        self.function_names.append(node.name)
        args = [arg.arg for arg in node.args.args if arg.arg not in ('self', 'cls')]
        
        self.test_code += f"def test_{node.name}():\n"
        if args:
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

    generator = PytestSkeletonGenerator()
    generator.visit(tree)

    if not generator.function_names:
        return AgentResponse(
            agent="test_generation", status="ok", 
            result="Aucune fonction trouvée. Impossible de générer des tests.",
            tokens_in=0, tokens_out=0, latency_s=0.1
        )

    prompt = TEST_GENERATION_PROMPT_TEMPLATE.format(
        skeleton=generator.test_code,
        function_names=", ".join(generator.function_names)
    )
    
    response = client.generate(prompt)
    llm_code = response.text if response.text else ""
    
    final_tests = generator.test_code
    
    if llm_code:
        clean_llm_code = llm_code.replace("```python", "").replace("```", "").strip()
        try:
            ast.parse(clean_llm_code)
            final_tests = clean_llm_code
        except SyntaxError:
            pass

    return AgentResponse(
        agent="test_generation", status="ok",
        result=final_tests,
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )