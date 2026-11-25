import os
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from .llm_protocol import LLMClient
from .analysis import run_analysis
from .test_generation import run_test_generation
from .documentation import run_documentation  # <-- NOUVEL IMPORT
from .review import run_review
from .schemas import AgentResponse

class GraphState(TypedDict):
    code: str
    results: List[AgentResponse]

def build_graph(client: LLMClient):
    workflow = StateGraph(GraphState)
    
    # Fonctions pour ajouter au fur et à mesure
    def node_analysis(state):
        res = run_analysis(state["code"], client)
        return {"results": state.get("results", []) + [res]}

    def node_tests(state):
        res = run_test_generation(state["code"], client)
        return {"results": state.get("results", []) + [res]}

    def node_documentation(state):
        res = run_documentation(state["code"], client)
        return {"results": state.get("results", []) + [res]}

    def node_review(state):
        res = run_review(state["code"], client)
        return {"results": state.get("results", []) + [res]}

    workflow.add_node("analysis", node_analysis)
    workflow.add_node("tests", node_tests)
    workflow.add_node("documentation", node_documentation)
    workflow.add_node("review", node_review)
    
    workflow.set_entry_point("analysis")
    workflow.add_edge("analysis", "tests")
    workflow.add_edge("tests", "documentation")
    workflow.add_edge("documentation", "review")
    workflow.add_edge("review", END)
    
    return workflow.compile()

def run_multi_agent(code: str, client: LLMClient) -> List[AgentResponse]:
    app = build_graph(client)
    final_state = app.invoke({"code": code, "results": []})
    return final_state["results"]