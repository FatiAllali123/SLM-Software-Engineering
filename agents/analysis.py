import ast
import json
from typing import List, Dict, Any
from .schemas import AgentResponse
from .llm_protocol import LLMClient
from .prompts import ANALYSIS_PROMPT_TEMPLATE, RETRY_ANALYSIS_PROMPT_TEMPLATE

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

def _is_valid_json(text: str) -> bool:
    """Vérifie si le texte est un JSON valide."""
    try:
        data = json.loads(text)
        return isinstance(data, dict) and "issues" in data and "summary" in data
    except (json.JSONDecodeError, TypeError):
        return False

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
    
    # Premier appel
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        functions_summary=functions_summary if functions_summary else 'Aucune',
        issues_count=len(visitor.issues)
    )
    response = client.generate(prompt)
    llm_output = response.text.strip()
    
    # Logique de Retry
    if not _is_valid_json(llm_output):
        # Deuxième tentative avec un prompt plus strict
        retry_prompt = RETRY_ANALYSIS_PROMPT_TEMPLATE.format(code=code)
        response_retry = client.generate(retry_prompt)
        llm_output = response_retry.text.strip()
        
        # On additionne les tokens des deux appels
        total_tokens_in = response.input_tokens + response_retry.input_tokens
        total_tokens_out = response.output_tokens + response_retry.output_tokens
        total_latency = response.latency_ms + response_retry.latency_ms
    else:
        total_tokens_in = response.input_tokens
        total_tokens_out = response.output_tokens
        total_latency = response.latency_ms

    # Si le retry a marché, on renvoie le JSON. Sinon, on garde le fallback sécurisé (ast).
    if _is_valid_json(llm_output):
        final_result = llm_output
    else:
        # Fallback : on combine les issues de l'AST avec un résumé générique
        summary = "Analyse terminée (le LLM n'a pas fourni de JSON valide après retry)."
        result_dict = {
            "issues": visitor.issues,
            "summary": summary
        }
        final_result = str(result_dict)

    return AgentResponse(
        agent="code_analysis", status="ok",
        result=final_result,
        tokens_in=total_tokens_in, tokens_out=total_tokens_out,
        latency_s=total_latency / 1000.0
    )