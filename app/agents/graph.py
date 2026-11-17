import os
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from .llm_client_stub import LLMClientStub
from .analysis import run_analysis
from .test_generation import run_test_generation
from .review import run_review
from .schemas import AgentRequest, AgentResponse

# 1. Définition de l'état partagé entre les agents
class GraphState(TypedDict):
    code: str
    results: List[AgentResponse]

# 2. Lecture du flag d'environnement pour Q3 (Single vs Multi-agent)
MULTI_AGENT = os.getenv("MULTI_AGENT", "true").lower() == "true"

def build_graph(client: LLMClientStub):
    workflow = StateGraph(GraphState)
    
    if MULTI_AGENT:
        # Mode Multi-Agent (3 noeuds)
        workflow.add_node("analysis", lambda s: {"results": s.get("results", []) + [run_analysis(s["code"], client)]})
        workflow.add_node("tests", lambda s: {"results": s.get("results", []) + [run_test_generation(s["code"], client)]})
        workflow.add_node("review", lambda s: {"results": s.get("results", []) + [run_review(s["code"], client)]})
        
        workflow.set_entry_point("analysis")
        workflow.add_edge("analysis", "tests")
        workflow.add_edge("tests", "review")
        workflow.add_edge("review", END)
    else:
        # Mode Single-Agent (1 seul noeud qui fait tout d'un coup - pour Q3)
        def single_agent(s):
            res = [
                run_analysis(s["code"], client),
                run_test_generation(s["code"], client),
                run_review(s["code"], client)
            ]
            return {"results": res}
        
        workflow.add_node("single", single_agent)
        workflow.set_entry_point("single")
        workflow.add_edge("single", END)
        
    return workflow.compile()

# 3. Fonction d'entrée pour C (Backend)
def run_graph(request: AgentRequest) -> List[dict]:
    """C'est cette fonction que le backend FastAPI appellera."""
    client = LLMClientStub()
    app = build_graph(client)
    
    # Exécution du graphe
    initial_state = {"code": request.code, "results": []}
    final_state = app.invoke(initial_state)
    
    # On renvoie la liste des dictionnaires (format JSON) pour l'API
    return [res.model_dump() for res in final_state["results"]]