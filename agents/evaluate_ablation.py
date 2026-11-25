import json
import os
import ast
from .pipeline import run_pipeline
from .llm_client_stub import LLMClientStub

def get_code_size(code: str, context_mode: str) -> int:
    """Calcule la taille du code qui sera envoyé au LLM selon le mode."""
    if context_mode == "reduced":
        try:
            tree = ast.parse(code)
            signatures = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    args = [a.arg for a in node.args.args if a.arg not in ('self', 'cls')]
                    signatures.append(f"def {node.name}({', '.join(args)}): ...")
            return len("\n".join(signatures))
        except:
            return len(code)
    return len(code)

def run_ablation():
    print("🚀 Démarrage de l'Ablation Study : Full Context vs Reduced Context...\n")
    
    dataset_path = os.path.join(os.path.dirname(__file__), "q3_dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    test_tasks = data["tasks"]
    llm = LLMClientStub()
    
    full_sizes, reduced_sizes = [], []

    for task in test_tasks:
        try:
            size_full = get_code_size(task["code"], "full")
            size_reduced = get_code_size(task["code"], "reduced")
            
            full_sizes.append(size_full)
            reduced_sizes.append(size_reduced)
            
            print(f"Tâche {task['id']} : Full = {size_full} car. | Reduced = {size_reduced} car.")
        except Exception as e:
            print(f"   ⚠️ Erreur sur {task['id']} : {e}")

    if full_sizes and reduced_sizes:
        avg_full = sum(full_sizes) / len(full_sizes)
        avg_reduced = sum(reduced_sizes) / len(reduced_sizes)
        print("\n" + "="*50)
        print("📊 RÉSUMÉ DE L'ABLATION (Taille du code envoyé)")
        print("="*50)
        print(f"Caractères moyens (Full)    : {avg_full:.1f}")
        print(f"Caractères moyens (Reduced) : {avg_reduced:.1f}")
        if avg_full > 0:
            print(f"Économie de caractères      : -{(1 - avg_reduced/avg_full) * 100:.1f} %")

if __name__ == "__main__":
    run_ablation()