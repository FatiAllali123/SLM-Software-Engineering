import ast
from typing import List, Dict, Any
from .schemas import AgentResponse
from .llm_protocol import LLMClient
from .prompts import ANALYSIS_PROMPT_TEMPLATE, PROMPT_VERSION

class AdvancedCodeVisitor(ast.NodeVisitor):
    """Un visiteur AST professionnel pour extraire des métriques de qualité."""
    def __init__(self):
        self.issues = []
        self.functions = []
        
    def visit_FunctionDef(self, node):
        args = [a.arg for a in node.args.args]
        self.functions.append({"name": node.name, "args": args, "lineno": node.lineno})
        
        if not ast.get_docstring(node):
            self.issues.append({
                "line": node.lineno,
                "severity": "low",
                "category": "quality",
                "message": f"La fonction '{node.name}' n'a pas de docstring."
            })
            
        if hasattr(node, 'end_lineno') and node.end_lineno:
            length = node.end_lineno - node.lineno
            if length > 30:
                self.issues.append({
                    "line": node.lineno,
                    "severity": "medium",
                    "category": "quality",
                    "message": f"La fonction '{node.name}' fait {length} lignes (trop longue)."
                })
        
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            self.issues.append({
                "line": node.lineno,
                "severity": "low",
                "category": "style",
                "message": "Utilisation de 'print()' détectée. Préférez un module de logging."
            })
        self.generic_visit(node)

def run_analysis(code: str, client: LLMClient) -> AgentResponse:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return AgentResponse(
            agent="code_analysis", status="error", result="", 
            error_message=f"Erreur de syntaxe ligne {e.lineno} : {e.msg}"
        )

    visitor = AdvancedCodeVisitor()
    visitor.visit(tree)
    
    functions_summary = ", ".join([f"{f['name']}({', '.join(f['args'])})" for f in visitor.functions])
    
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        functions_summary=functions_summary if functions_summary else 'Aucune',
        issues_count=len(visitor.issues)
    )
    
    response = client.generate(prompt)
    
    summary = response.text if response.text else "Analyse terminée."
    if not visitor.issues:
        summary = "Aucun problème majeur détecté. " + summary

    result_dict = {
        "issues": visitor.issues,
        "summary": summary
    }

    return AgentResponse(
        agent="code_analysis", status="ok",
        result=str(result_dict),
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )