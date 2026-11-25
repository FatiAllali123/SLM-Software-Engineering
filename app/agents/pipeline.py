import time
from typing import Dict, Any
from .analysis import run_analysis
from .test_generation import run_test_generation
from .review import run_review
from .graph import run_multi_agent 
from .llm_protocol import LLMClient

# Ajoute ceci au début du fichier, après les imports
class AgentInvalidInputError(Exception):
    """Erreur levée quand le code fourni est invalide (syntaxe)."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
        self.code = "INVALID_INPUT"

def format_result_for_backend(task: str, raw_result: str) -> Dict[str, Any]:
    if task == "analyze":
        return {"issues": [{"line": 1, "severity": "low", "category": "quality", "message": raw_result}], "summary": "Analyse terminée."}
    elif task == "generate_tests":
        return {"tests": raw_result, "test_count": raw_result.count("def test_"), "summary": "Tests générés."}
    elif task == "review":
        verdict = "approve" if "Aucun problème" in raw_result else "request_changes"
        return {"findings": [{"line": 1, "severity": "medium", "message": raw_result}], "verdict": verdict, "summary": "Revue terminée."}
    raise ValueError(f"Tâche inconnue : {task}")

def run_pipeline(task: str, code: str, language: str, mode: str, llm: LLMClient) -> Dict[str, Any]:
    start_time = time.time()
    trace = []
    
    if mode == "single_agent":
        if task == "analyze": agent_res = run_analysis(code, llm)
        elif task == "generate_tests": agent_res = run_test_generation(code, llm)
        elif task == "review": agent_res = run_review(code, llm)
        else: raise ValueError(f"Tâche inconnue : {task}")
        
        if agent_res.status == "error": 
            # On lève notre exception personnalisée
            raise AgentInvalidInputError(agent_res.error_message)
        
        trace.append({"agent": task, "step": task, "input_tokens": agent_res.tokens_in, "output_tokens": agent_res.tokens_out, "latency_ms": int(agent_res.latency_s * 1000)})
        result_data = format_result_for_backend(task, agent_res.result)
        total_in, total_out, llm_calls = agent_res.tokens_in, agent_res.tokens_out, 1

    elif mode == "multi_agent":
        # On appelle le vrai graphe LangGraph
        agent_responses = run_multi_agent(code, llm)
        
        # On récupère les résultats (on prend celui qui correspond à la tâche demandée)
        target_agent = "code_analysis" if task == "analyze" else ("test_generation" if task == "generate_tests" else "code_review")
        final_res = next((r for r in agent_responses if r.agent == target_agent), agent_responses[0])
        
        for r in agent_responses:
            trace.append({"agent": r.agent, "step": task, "input_tokens": r.tokens_in, "output_tokens": r.tokens_out, "latency_ms": int(r.latency_s * 1000)})
            
        result_data = format_result_for_backend(task, final_res.result)
        total_in = sum(r.tokens_in for r in agent_responses)
        total_out = sum(r.tokens_out for r in agent_responses)
        llm_calls = len(agent_responses)

    else:
        raise ValueError(f"Mode inconnu : {mode}")

    return {
        "result": result_data,
        "metrics": {"input_tokens": total_in, "output_tokens": total_out, "latency_ms": int((time.time() - start_time) * 1000), "llm_calls": llm_calls},
        "trace": trace
    }