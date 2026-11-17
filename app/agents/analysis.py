import ast
from .schemas import AgentResponse
from .llm_client_stub import LLMClientStub

def run_analysis(code: str, client: LLMClientStub) -> AgentResponse:
    # 1. On utilise ast pour analyser le code Python
    try:
        tree = ast.parse(code)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        
        if functions:
            resultat = f"Analyse statique : {len(functions)} fonction(s) trouvée(s) -> {', '.join(functions)}."
        else:
            resultat = "Analyse statique : aucune fonction trouvée dans ce code."
            
    except SyntaxError as e:
        # Si le code n'est pas du Python valide, on renvoie une erreur propre
        return AgentResponse(
            agent="code_analysis",
            status="error",
            result="",
            error_message=f"Erreur de syntaxe : {str(e)}"
        )

    # 2. On simule l'appel au modèle pour le format (tokens, latence)
    # Plus tard, on pourra demander au LLM de faire une analyse sémantique
    prompt = f"Voici les fonctions extraites : {resultat}. Que peux-tu dire de ce code ?"
    response = client.generate([{"role": "user", "content": prompt}])
    
    # 3. On renvoie le résultat formaté
    return AgentResponse(
        agent="code_analysis",
        status="ok",
        result=resultat, # On renvoie l'analyse de 'ast' (vraie analyse)
        tokens_in=response["tokens_in"],
        tokens_out=response["tokens_out"],
        latency_s=response["latency_s"]
    )