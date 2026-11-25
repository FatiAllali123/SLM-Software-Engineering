import json
import os
import time
from .pipeline import run_pipeline
from .llm_client_stub import LLMClientStub

def run_evaluation():
    print("🚀 Démarrage de l'évaluation Q3 (Single-Agent vs Multi-Agent)...\n")
    
    # 1. Charger le dataset depuis le fichier JSON
    dataset_path = os.path.join(os.path.dirname(__file__), "q3_dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    test_tasks = data["tasks"]
    llm = LLMClientStub()
    results = []

    # 2. On teste chaque code dans les deux modes
    for task in test_tasks:
        print(f"Traitement de {task['id']}...")
        
        try:
            # Mode Single-Agent
            start_single = time.time()
            res_single = run_pipeline(
                task="analyze", code=task["code"], language="python", mode="single_agent", llm=llm
            )
            time_single = time.time() - start_single
            
            # Mode Multi-Agent
            start_multi = time.time()
            res_multi = run_pipeline(
                task="analyze", code=task["code"], language="python", mode="multi_agent", llm=llm
            )
            time_multi = time.time() - start_multi

            results.append({
                "code": task["id"],
                "single_agent": {
                    "total_time_s": round(time_single, 3),
                    "input_tokens": res_single["metrics"]["input_tokens"],
                    "output_tokens": res_single["metrics"]["output_tokens"],
                    "llm_calls": res_single["metrics"]["llm_calls"]
                },
                "multi_agent": {
                    "total_time_s": round(time_multi, 3),
                    "input_tokens": res_multi["metrics"]["input_tokens"],
                    "output_tokens": res_multi["metrics"]["output_tokens"],
                    "llm_calls": res_multi["metrics"]["llm_calls"]
                }
            })
        except Exception as e:
            # Si un code plante (comme le task_9), on note l'erreur sans arrêter le script
            print(f"   ⚠️ Erreur sur {task['id']} : {e}")
            results.append({"code": task["id"], "error": str(e)})

    # 3. Affichage dans le terminal
    print("\n" + "="*80)
    print(f"{'Code testé':<20} | {'Mode':<15} | {'Temps (s)':<10} | {'Tokens In':<10} | {'Tokens Out':<10} | {'Appels LLM'}")
    print("-" * 80)
    
    for r in results:
        if "error" in r:
            print(f"{r['code']:<20} | ERREUR : {r['error']}")
            continue
            
        s = r["single_agent"]
        m = r["multi_agent"]
        print(f"{r['code']:<20} | {'Single-Agent':<15} | {s['total_time_s']:<10} | {s['input_tokens']:<10} | {s['output_tokens']:<10} | {s['llm_calls']}")
        print(f"{'':<20} | {'Multi-Agent':<15} | {m['total_time_s']:<10} | {m['input_tokens']:<10} | {m['output_tokens']:<10} | {m['llm_calls']}")
        print("-" * 80)

    # 4. Sauvegarde en JSON pour le rapport
    os.makedirs("results/q3", exist_ok=True)
    with open("results/q3/evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    
    print(f"\n✅ Résultats sauvegardés dans results/q3/evaluation_results.json")

if __name__ == "__main__":
    run_evaluation()