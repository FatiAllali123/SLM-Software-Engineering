"""
Fusionne les resultats des 4 modeles. COMMUN : a lancer UNE fois, par UNE personne,
quand les 8 fichiers results/ existent (et que les notes manuelles sont remplies).

Utilisation (depuis le dossier benchmarking/) :  python merge_results.py

Genere :
  comparatif_final.csv       tous les prompts maison des 4 modeles
  resume_final.csv           moyennes par modele (vitesse, memoire, tests auto, notes)
  comparatif_humaneval.csv   score HumanEval de chaque modele
  detail_humaneval.csv       resultat de chaque probleme HumanEval, tous modeles
"""
import json
from pathlib import Path
import pandas as pd

RESULTS = Path("results")
MODELS = {
    "Qwen2.5-Coder-1.5B": "qwen2.5-coder-1.5b-instruct",
    "Phi-4-mini": "phi-4-mini-instruct",
    "Gemma3-4B": "gemma-3-4b-it",
    "SmolLM3-3B": "smollm3-3b",
}


def prf1(labels):
    """Precision / rappel / F1 a partir des etiquettes TP, FP, FN, TN."""
    tp, fp, fn = (sum(l == k for l in labels) for k in ("TP", "FP", "FN"))
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else None
    return p, r, f


def merge_prompts():
    frames = []
    for name, slug in MODELS.items():
        path = RESULTS / f"benchmark_{slug}.csv"
        if not path.exists():
            print(f"[attention] {path} introuvable, ignore.")
            continue
        df = pd.read_csv(path)
        df.insert(0, "modele", name)
        frames.append(df)
    if not frames:
        return
    all_df = pd.concat(frames, ignore_index=True)
    all_df.to_csv("comparatif_final.csv", index=False)
    print("-> comparatif_final.csv")

    rows = []
    for name, g in all_df.groupby("modele"):
        auto = g[g["auto_status"].isin(["pass", "fail", "timeout"])]
        notes = pd.to_numeric(g["note_qualite"], errors="coerce")
        labels = [str(x).strip().upper() for x in g["bug_label"].dropna()]
        p, r, f = prf1(labels)
        halluc = g["hallucination"].dropna().astype(str).str.lower()
        rows.append({
            "modele": name,
            "ttft_moyen_s": g["ttft_s"].mean(),
            "latence_moyenne_s": g["latency_s"].mean(),
            "tokens_par_sec_moyen": g["tokens_per_sec"].mean(),
            "memoire_go_max": g["gpu_memory_go"].max(),
            "tokens_sortie_moyens": g["output_tokens"].mean(),
            "tests_auto_reussis_%": 100 * (auto["auto_status"] == "pass").mean() if len(auto) else None,
            "note_qualite_moyenne": notes.mean(),
            "bug_precision": p, "bug_rappel": r, "bug_f1": f,
            "hallucinations": int(halluc.isin(["oui", "yes", "1", "true"]).sum()),
        })
    pd.DataFrame(rows).round(2).to_csv("resume_final.csv", index=False)
    print("-> resume_final.csv")


def merge_humaneval():
    summary, detail = [], []
    for name, slug in MODELS.items():
        path = RESULTS / f"humaneval_{slug}.json"
        if not path.exists():
            print(f"[attention] {path} introuvable, ignore.")
            continue
        d = json.load(open(path, encoding="utf-8"))
        det = pd.DataFrame(d["details"]).drop(columns=["response"], errors="ignore")
        det.insert(0, "modele", name)
        detail.append(det)
        summary.append({
            "modele": name, "gpu": d["gpu"], "precision": d["precision"],
            "n_problems": d["n_problems"], "n_pass": d["n_pass"], "pass@1_%": d["pass@1"],
            "ttft_moyen_s": round(det["ttft_s"].mean(), 3),
            "tokens_par_sec_moyen": round(det["tokens_per_sec"].mean(), 2),
        })
    if summary:
        pd.DataFrame(summary).to_csv("comparatif_humaneval.csv", index=False)
        pd.concat(detail).to_csv("detail_humaneval.csv", index=False)
        print("-> comparatif_humaneval.csv, detail_humaneval.csv")
        print(pd.DataFrame(summary)[["modele", "pass@1_%"]].to_string(index=False))


if __name__ == "__main__":
    merge_prompts()
    merge_humaneval()
