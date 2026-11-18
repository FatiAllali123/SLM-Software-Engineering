import time
from typing import Dict, Any, List
from .schemas import AgentRequest
from .analysis import run_analysis
from .test_generation import run_test_generation
from .review import run_review
from .llm_protocol import LLMClient

def format_result_for_backend(task: str, raw_result: str) -> Dict[str, Any]:
    """Transforme la sortie texte de l'agent au format JSON demandé par Fati."""
    if task == "analyze":
        # On simule un format d'issues basé sur le texte (pour l'exemple)
        return {
            "issues": [{"line": 1, "severity": "low", "category": "quality", "message": raw_result}],
            "summary": "Analyse terminée."
        }
    elif task == "generate_tests":
        return {
            "tests": raw_result,
            "test_count": raw_result.count("def test_"),
            "summary": "Tests générés."
        }
    elif task == "review":
        return {
            "findings": [{"line": 1, "severity": "medium", "message": raw_result}],
            "verdict": "request_changes",
            "summary": "Revue terminée."
        }
    else:
        raise ValueError(f"Tâche inconnue : {task}")

def run_pipeline(
    task: str,          # "analyze", "generate_tests" ou "review"
    code: str,
    language: str,      # "python"
    mode: str,          # "single_agent" ou "multi_agent"
    llm: LLMClient
) -> Dict[str, Any]:
    
    start_time = time.time()
    trace = []
    
    # 1. Mode Single-Agent : On appelle directement le bon agent selon la tâche
    if mode == "single_agent":
        if task == "analyze":
            agent_res = run_analysis(code, llm)
            agent_name = "analysis"
        elif task == "generate_tests":
            agent_res = run_test_generation(code, llm)
            agent_name = "test_generation"
        elif task == "review":
            agent_res = run_review(code, llm)
            agent_name = "review"
        else:
            raise ValueError(f"Tâche inconnue : {task}")
            
        if agent_res.status == "error":
            raise RuntimeError(f"Erreur de l'agent : {agent_res.error_message}")
            
        trace.append({
            "agent": agent_name,
            "step": task,
            "input_tokens": agent_res.tokens_in,
            "output_tokens": agent_res.tokens_out,
            "latency_ms": int(agent_res.latency_s * 1000)
        })
        
        result_data = format_result_for_backend(task, agent_res.result)
        total_in = agent_res.tokens_in
        total_out = agent_res.tokens_out
        llm_calls = 1

    # 2. Mode Multi-Agent : On utilise le graphe complet (LangGraph)
    elif mode == "multi_agent":
        # NOTE : Pour l'instant, on lance les 3 agents à la suite pour simuler le multi-agent.
        # Plus tard, on branchera le vrai graphe LangGraph ici.
        analysis_res = run_analysis(code, llm)
        tests_res = run_test_generation(code, llm)
        review_res = run_review(code, llm)
        
        if any(r.status == "error" for r in [analysis_res, tests_res, review_res]):
            raise RuntimeError("Erreur dans le graphe multi-agent.")
            
        trace = [
            {"agent": "analysis", "step": "analyze", "input_tokens": analysis_res.tokens_in, "output_tokens": analysis_res.tokens_out, "latency_ms": int(analysis_res.latency_s * 1000)},
            {"agent": "test_generation", "step": "generate", "input_tokens": tests_res.tokens_in, "output_tokens": tests_res.tokens_out, "latency_ms": int(tests_res.latency_s * 1000)},
            {"agent": "review", "step": "review", "input_tokens": review_res.tokens_in, "output_tokens": review_res.tokens_out, "latency_ms": int(review_res.latency_s * 1000)}
        ]
        
        total_in = sum(t["input_tokens"] for t in trace)
        total_out = sum(t["output_tokens"] for t in trace)
        llm_calls = 3
        
        # Le multi-agent combine les résultats (simplification pour l'exemple)
        combined_result = f"Analyse: {analysis_res.result}\nTests: {tests_res.result}\nRevue: {review_res.result}"
        result_data = format_result_for_backend(task, combined_result)

    else:
        raise ValueError(f"Mode inconnu : {mode}")

    end_time = time.time()
    
    # 3. On renvoie exactement le format attendu par Fati (section 10)
    return {
        "result": result_data,
        "metrics": {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "latency_ms": int((end_time - start_time) * 1000),
            "llm_calls": llm_calls
        },
        "trace": trace
    }