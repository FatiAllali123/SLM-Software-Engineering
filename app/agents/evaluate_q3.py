import json
import os
import time
import statistics
from .pipeline import run_pipeline
from .llm_client_stub import LLMClientStub

def run_evaluation():
    print("🚀 Démarrage de l'évaluation Q3 (Single-Agent vs Multi-Agent)...\n")
    
    dataset_path = os.path.join(os.path.dirname(__file__), "q3_dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    test_tasks = data["tasks"]
    llm = LLMClientStub()
    results = []

    # Listes pour stocker les métriques de chaque mode (pour les moyennes)
    single_times, single_in, single_out = [], [], []
    multi_times, multi_in, multi_out = [], [], []

    for task in test_tasks:
        try:
            # Mode Single-Agent
            start_single = time.time()
            res_single = run_pipeline(task="analyze", code=task["code"], language="python", mode="single_agent", llm=llm)
            time_single = time.time() - start_single
            
            # Mode Multi-Agent
            start_multi = time.time()
            res_multi = run_pipeline(task="analyze", code=task["code"], language="python", mode="multi_agent", llm=llm)
            time_multi = time.time() - start_multi

            # Remplissage des résultats détaillés
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

            # Remplissage des listes pour les statistiques
            single_times.append(time_single)
            single_in.append(res_single["metrics"]["input_tokens"])
            single_out.append(res_single["metrics"]["output_tokens"])
            
            multi_times.append(time_multi)
            multi_in.append(res_multi["metrics"]["input_tokens"])
            multi_out.append(res_multi["metrics"]["output_tokens"])

        except Exception as e:
            print(f"   ⚠️ Erreur sur {task['id']} : {e}")
            results.append({"code": task["id"], "error": str(e)})

    # --- AFFICHAGE DU TABLEAU DÉTAILLÉ ---
    print("\n" + "="*95)
    print(f"{'Code testé':<22} | {'Mode':<15} | {'Temps (s)':<10} | {'Tokens In':<10} | {'Tokens Out':<10} | {'Appels LLM'}")
    print("-" * 95)
    
    for r in results:
        if "error" in r:
            print(f"{r['code']:<22} | ERREUR : {r['error']}")
            continue
        s = r["single_agent"]
        m = r["multi_agent"]
        print(f"{r['code']:<22} | {'Single-Agent':<15} | {s['total_time_s']:<10} | {s['input_tokens']:<10} | {s['output_tokens']:<10} | {s['llm_calls']}")
        print(f"{'':<22} | {'Multi-Agent':<15} | {m['total_time_s']:<10} | {m['input_tokens']:<10} | {m['output_tokens']:<10} | {m['llm_calls']}")
        print("-" * 95)

    # --- STATISTIQUES POUR LE RAPPORT (Question de recherche Q3) ---
    print("\n" + "="*60)
    print("📊 RÉSUMÉ STATISTIQUE POUR LE RAPPORT (Q3)")
    print("="*60)
    
    # 1. Moyennes des temps
    avg_time_single = statistics.mean(single_times) if single_times else 0
    avg_time_multi = statistics.mean(multi_times) if multi_times else 0
    
    # 2. Moyennes des tokens
    avg_in_single = statistics.mean(single_in) if single_in else 0
    avg_in_multi = statistics.mean(multi_in) if multi_in else 0
    
    print(f"⏱️  Temps moyen par tâche :")
    print(f"   - Single-Agent : {avg_time_single:.4f} s")
    print(f"   - Multi-Agent  : {avg_time_multi:.4f} s")
    print(f"   - Surcoût      : +{(avg_time_multi / avg_time_single - 1) * 100:.1f} % pour le Multi-Agent")
    
    print(f"\n🪙 Tokens d'entrée moyens par tâche :")
    print(f"   - Single-Agent : {avg_in_single:.1f} tokens")
    print(f"   - Multi-Agent  : {avg_in_multi:.1f} tokens")
    print(f"   - Surcoût      : +{(avg_in_multi / avg_in_single - 1) * 100:.1f} % pour le Multi-Agent")
    
    # 3. Écart-type (stabilité)
    if len(single_times) > 1:
        print(f"\n📈 Écart-type (stabilité) :")
        print(f"   - Single-Agent : {statistics.stdev(single_times):.4f} s")
        print(f"   - Multi-Agent  : {statistics.stdev(multi_times):.4f} s")

    print("\n💡 Note pour le rapport :")
    print("   Ces chiffres sont générés avec le LLMClientStub.")
    print("   Les métriques réelles (avec Qwen) seront obtenues après l'intégration de Salma.")

    # --- SAUVEGARDE JSON ---
    os.makedirs("results/q3", exist_ok=True)
    with open("results/q3/evaluation_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "raw_results": results,
            "statistics": {
                "single_agent": {"avg_time_s": avg_time_single, "avg_input_tokens": avg_in_single},
                "multi_agent": {"avg_time_s": avg_time_multi, "avg_input_tokens": avg_in_multi}
            }
        }, f, indent=4, ensure_ascii=False)
    
    print(f"\n✅ Résultats détaillés et statistiques sauvegardés dans results/q3/evaluation_results.json")

if __name__ == "__main__":
    run_evaluation()