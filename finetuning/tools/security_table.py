"""Security detection table from ONE grader (member B), base vs fine-tuned, bf16/fp16/INT8/nf4.

  python security_table.py --sheet2 <B sheet 2> --key2 quant_blind_key_DO_NOT_OPEN.csv \
      --sheet3 <B sheet 3> --key3 quant3_blind_key_DO_NOT_OPEN.csv \
      --ft-quant-dir <quant_ft_results folder> --base-quant-dir <quant_base_results folder> \
      --ref-dir <folder with the graded bf16 CSVs by member C> --out security_out

A quantized answer whose text equals the bf16 answer takes B's label of that bf16 answer, so every label
comes from the same grader. Member C's labels are only used to measure agreement on the bf16 answers.
"""
import argparse, os, sys
import pandas as pd

S = "qwen2.5-coder-1.5b-instruct"
ap = argparse.ArgumentParser()
for n in ("sheet2", "key2", "sheet3", "key3", "ft-quant-dir", "base-quant-dir", "ref-dir"): ap.add_argument("--" + n, required=True)
ap.add_argument("--out", default="security_out")
a = ap.parse_args()

def read_sheet(p):
    if p.lower().endswith(".csv"):
        raw = open(p, "rb").read()
        try: enc = "utf-8-sig"; raw.decode(enc)
        except UnicodeDecodeError: enc = "cp1252"
        g = pd.read_csv(p, dtype=str, encoding=enc, sep=None, engine="python")
        return g.loc[:, ~g.columns.astype(str).str.startswith("Unnamed")]
    return pd.read_excel(p, sheet_name="Grading", dtype=str)

B = {}   # (system, prompt_id) -> label by member B
for sheet, key in ((a.sheet2, a.key2), (a.sheet3, a.key3)):
    d = read_sheet(sheet).merge(pd.read_csv(key, dtype=str)[["row_id", "systems"]], on="row_id", how="left")
    assert d["systems"].notna().all(), f"row_id missing from {key}"
    bad = [f"{r.row_id} ({r.prompt_id}): {r.label!r}" for r in d.itertuples() if str(r.label).strip().upper() not in {"TP", "FP", "FN", "TN"}]
    if bad: print("\n".join(bad)); sys.exit(f"{len(bad)} row(s) without a valid label in {os.path.basename(sheet)}")
    for r in d.itertuples():
        for s in r.systems.split("+"): B[(s, r.prompt_id)] = r.label.strip().upper()

V = [f"V{i}" for i in range(1, 10)]
qdir = {"ft": a.ft_quant_dir, "base": a.base_quant_dir}
labels = {}
for model, qd in qdir.items():
    for v in ("bf16", "fp16", "int8", "nf4"):
        L = {}
        if v != "bf16":
            c = pd.read_csv(os.path.join(qd, f"vulnerabilites_{S}__{model}__{v}.csv")).set_index("id")
        for pid in V:
            L[pid] = B[(f"{model}_bf16", pid)] if v == "bf16" or bool(c.loc[pid, "same_as_ref"]) else B[(f"{model}_{v}", pid)]
        labels[(model, v)] = L

# agreement with member C on the bf16 answers
C = {"ft": pd.read_csv(os.path.join(a.ref_dir, f"vulnerabilites_{S}-ft-run1-bf16.csv")).set_index("id")["vuln_label"],
     "base": pd.read_csv(os.path.join(a.ref_dir, f"vulnerabilites_{S}-ctrl.csv")).set_index("id")["vuln_label"]}
tot = ok = 0
for model in ("ft", "base"):
    for pid in V:
        tot += 1; same = labels[(model, "bf16")][pid] == str(C[model][pid]).upper(); ok += same
        if not same: print(f"B vs C disagreement ({model}, {pid}): B={labels[(model,'bf16')][pid]} | C={C[model][pid]}")
print(f"Agreement B vs C on the 18 bf16 security answers: {ok}/{tot}\n")

def prf1(l):
    tp, fp, fn = (l.count(k) for k in ("TP", "FP", "FN"))
    p = tp / (tp + fp) if tp + fp else None; r = tp / (tp + fn) if tp + fn else None
    f = None if p is None or r is None else (0.0 if p + r == 0 else 2 * p * r / (p + r))
    return p, r, f
rows = []
for (model, v), L in labels.items():
    l = list(L.values()); p, r, f = prf1(l)
    rows.append({"model": model, "variant": v, "precision": p, "recall": r, "F1": f,
                 "TP": l.count("TP"), "FP": l.count("FP"), "FN": l.count("FN"), "TN": l.count("TN")})
t = pd.DataFrame(rows).round(3)
os.makedirs(a.out, exist_ok=True)
t.to_csv(os.path.join(a.out, "security_table_single_grader.csv"), index=False)
pd.DataFrame([{"model": m, "variant": v, "prompt_id": k, "label": x} for (m, v), L in labels.items() for k, x in L.items()]
             ).to_csv(os.path.join(a.out, "security_labels_single_grader.csv"), index=False)
print(t.to_string(index=False))
print("\n6 vulnerable prompts and 3 safe prompts only: descriptive, not statistical.")
