"""Re-score saved SE-Tasks responses WITHOUT a GPU, with the corrected se_bench.py.

  python rescore_se.py --results-dir <folder with bugfix_<model>.json, testgen_<model>.json, doc_..., docker_..., workflow_..., mutants.json> \
                       --humaneval <HumanEval.jsonl.gz>  (or --humaneval hf to use the datasets library) [--base base] --out rescored

Reads the saved model responses, applies the corrected extractor (any fence tag/case) and the corrected strict test scorer,
adds the lenient (unittest/pytest) test scorer as a secondary metric, and prints per-model tables plus paired bootstrap vs the base model.
"""
import argparse, glob, gzip, json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import se_bench as sb

ap = argparse.ArgumentParser()
ap.add_argument("--results-dir", required=True); ap.add_argument("--humaneval", required=True)
ap.add_argument("--base", default="base"); ap.add_argument("--out", default="rescored")
a = ap.parse_args()

if a.humaneval == "hf":
    from datasets import load_dataset
    rows = list(load_dataset("openai/openai_humaneval", split="test"))
else:
    rows = [json.loads(l) for l in gzip.open(a.humaneval, "rt")]
EX = {r["task_id"]: r for r in rows}; assert len(EX) == 164
MUT = json.load(open(os.path.join(a.results_dir, "mutants.json")))
items = [t for t in EX if MUT.get(t)]
doc_tasks = [t for t in EX if int(t.split("/")[1]) % 2 == 0]
models = sorted({os.path.basename(p)[len("testgen_"):-5] for p in glob.glob(os.path.join(a.results_dir, "testgen_*.json"))})
print("models found:", models, "| items with a bug:", len(items))
os.makedirs(a.out, exist_ok=True)

def load(task, m):
    p = os.path.join(a.results_dir, f"{task}_{m}.json"); return json.load(open(p)) if os.path.exists(p) else {}

R = {}
for m in models:
    bf, tg, dc, dk, wf = (load(t, m) for t in ("bugfix", "testgen", "doc", "docker", "workflow"))
    out = {"bugfix": {}, "strict": {}, "lenient": {}, "doc": {}, "docker": {}, "workflow": {}}
    for t, v in bf.items(): out["bugfix"][t] = sb.score_bugfix(EX[t], MUT[t][0], v["response"])
    for t, v in tg.items():
        out["strict"][t] = sb.score_tests(EX[t], MUT[t], v["response"]); out["lenient"][t] = sb.score_tests_lenient(EX[t], MUT[t], v["response"])
    for t, v in dc.items(): out["doc"][t] = sb.score_doc(EX[t], sb.doc_item(EX[t]), v["response"])
    for i, v in dk.items(): out["docker"][i] = sb.score_docker(sb.DOCKER_SPECS[int(i)], v["response"])
    for i, v in wf.items(): out["workflow"][i] = sb.score_workflow(sb.WF_SPECS[int(i)], v["response"])
    out["tokens"] = {"bugfix": np.mean([v["output_tokens"] for v in bf.values()]) if bf else float("nan"),
                     "testgen": np.mean([v["output_tokens"] for v in tg.values()]) if tg else float("nan")}
    out["reasons_strict"] = pd.Series([v["reason"] or "ok" for v in out["strict"].values()]).value_counts().to_dict()
    out["reasons_lenient"] = pd.Series([v["reason"] or "ok" for v in out["lenient"].values()]).value_counts().to_dict()
    R[m] = out

def mut_scores(tg): return [(tg[t]["mutants_killed"] / tg[t]["mutants_total"]) if (tg[t]["valid"] and tg[t]["mutants_total"]) else 0.0 for t in items if t in tg]
rows_out = {}
for m, r in R.items():
    d = {"bugfix_pass_%": 100 * np.mean([r["bugfix"][t]["passed"] for t in items if t in r["bugfix"]])}
    for k in ("strict", "lenient"):
        tg = r[k]
        d[f"{k}_valid_tests_%"] = 100 * np.mean([v["valid"] for v in tg.values()])
        d[f"{k}_mutation_score_%"] = 100 * np.mean(mut_scores(tg))
        cv = [v["coverage"] for v in tg.values() if v["valid"]]; d[f"{k}_coverage_of_valid_%"] = 100 * (np.mean(cv) if cv else 0)
    d["docstring_ok_%"] = 100 * np.mean([v["ok"] for v in r["doc"].values()])
    for k in ("docker", "workflow"):
        d[f"{k}_valid_%"] = 100 * np.mean([v["valid"] for v in r[k].values()]); d[f"{k}_req_met_%"] = 100 * np.mean([v["frac_met"] for v in r[k].values()])
    d["tokens_bugfix"], d["tokens_testgen"] = r["tokens"]["bugfix"], r["tokens"]["testgen"]
    rows_out[m] = d
table = pd.DataFrame(rows_out).round(1); print(table.to_string()); table.to_csv(os.path.join(a.out, "se_tasks_rescored.csv"))
for m in models:
    print(f"\n{m}: why tests were rejected (strict): {R[m]['reasons_strict']}\n{' '*len(m)}  (lenient): {R[m]['reasons_lenient']}")

if a.base in R:
    for m in models:
        if m == a.base: continue
        print(f"\n{m} minus {a.base} (paired bootstrap 95% CI, points):")
        def arr(k, key):
            if key == "bugfix": return [float(R[k]["bugfix"][t]["passed"]) for t in items]
            tg = R[k][key[0]]
            return [float(tg[t]["valid"]) for t in EX if t in tg] if key[1] == "valid" else mut_scores(tg)
        for label, keyb, keyr in (("bug fix", "bugfix", "bugfix"), ("valid tests (strict)", ("strict", "valid"), ("strict", "valid")),
                                  ("mutation score (strict)", ("strict", "mut"), ("strict", "mut")), ("valid tests (lenient)", ("lenient", "valid"), ("lenient", "valid")),
                                  ("mutation score (lenient)", ("lenient", "mut"), ("lenient", "mut"))):
            d, lo, hi = sb.paired_bootstrap(arr(a.base, keyb), arr(m, keyr))
            print(f"  {label:26s}: {d:+.1f}  (CI {lo:+.1f} to {hi:+.1f})  {'rule met' if d >= 5 and lo > 0 else 'rule not met'}")
