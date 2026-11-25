import ast
from typing import List, Dict, Any
from .schemas import AgentResponse
from .llm_protocol import LLMClient

class AdvancedCodeVisitor(ast.NodeVisitor):
    """Un visiteur AST professionnel pour extraire des métriques de qualité."""
    def __init__(self):
        self.issues = []
        self.functions = []
        
    def visit_FunctionDef(self, node):
        # 1. Extraire la signature
        args = [a.arg for a in node.args.args]
        self.functions.append({"name": node.name, "args": args, "lineno": node.lineno})
        
        # 2. Vérifier la docstring
        if not ast.get_docstring(node):
            self.issues.append({
                "line": node.lineno,
                "severity": "low",
                "category": "quality",
                "message": f"La fonction '{node.name}' n'a pas de docstring."
            })
            
        # 3. Vérifier la longueur de la fonction (ex: plus de 30 lignes = complexe)
        if hasattr(node, 'end_lineno') and node.end_lineno:
            length = node.end_lineno - node.lineno
            if length > 30:
                self.issues.append({
                    "line": node.lineno,
                    "severity": "medium",
                    "category": "quality",
                    "message": f"La fonction '{node.name}' fait {length} lignes (trop longue, envisagez de la diviser)."
                })
        
        self.generic_visit(node)

    def visit_Call(self, node):
        # Vérifier l'usage de print()
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

    # 1. Analyse statique avancée
    visitor = AdvancedCodeVisitor()
    visitor.visit(tree)
    
    # 2. Préparer le contexte pour le LLM (le prompt lui donne les faits vérifiés)
    functions_summary = ", ".join([f"{f['name']}({', '.join(f['args'])})" for f in visitor.functions])
    prompt = f"""
    Voici une analyse statique du code Python :
    - Fonctions trouvées : {functions_summary if functions_summary else 'Aucune'}
    - Problèmes détectés par l'analyseur : {len(visitor.issues)}
    
    Fais une brève analyse sémantique de ce code pour compléter cette analyse.
    """
    
    # 3. Appel au LLM (qui renverra le texte final)
    response = client.generate(prompt)
    
    # 4. Formater le résultat final pour Fati (le contrat demande une liste d'issues et un summary)
    # On combine les problèmes trouvés par l'AST et le texte du LLM
    summary = response.text if response.text else "Analyse terminée."
    if not visitor.issues:
        summary = "Aucun problème majeur détecté. " + summary

    # On construit le dictionnaire final
    result_dict = {
        "issues": visitor.issues,
        "summary": summary
    }

    return AgentResponse(
        agent="code_analysis", status="ok",
        result=str(result_dict), # On sérialise le dictionnaire en string
        tokens_in=response.input_tokens, tokens_out=response.output_tokens,
        latency_s=response.latency_ms / 1000.0
    )