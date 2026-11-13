"""Unblind grading sheet 2 (quantized fine-tuned variants) and compute detection metrics.

  python unblind_quant.py --sheet grading_sheet_blind_quant.xlsx --key quant_blind_key_DO_NOT_OPEN.csv \
      --quant-dir <folder with the quant_ft_results files> --ref-dir <folder with graded ft bf16 CSVs> --out graded_quant

--ref-dir must contain the graded benchmark_...-ft-run1-bf16.csv and vulnerabilites_...-ft-run1-bf16.csv (labels by member C).
Rows whose text equals the bf16 answer reuse C's label; the others use the new grader's label.
The 12 'ft_bf16' rows are anchors: they measure agreement between the two graders.
"""
import argparse, os, sys
import pandas as pd

S = "qwen2.5-coder-1.5b-instruct"
ap = argparse.ArgumentParser()
for a_ in ("sheet", "key", "quant_dir", "ref_dir"): ap.add_argument("--" + a_.replace("_", "-"), required=True)
ap.add_argument("--out", default="graded_quant")
a = ap.parse_args()

if a.sheet.lower().endswith(".csv"):
    raw = open(a.sheet, "rb").read()
    try: enc = "utf-8-sig"; raw.decode(enc)
    except UnicodeDecodeError: enc = "cp1252"
    g = pd.read_csv(a.sheet, dtype=str, encoding=enc, sep=None, engine="python")
    g = g.loc[:, ~g.columns.astype(str).str.startswith("Unnamed")]
else:
    g = pd.read_excel(a.sheet, sheet_name="Grading", dtype=str)
key = pd.read_csv(a.key, dtype=str)
df = g.merge(key[["row_id", "systems"]], on="row_id", how="left")
assert df["systems"].notna().all(), "a row_id is missing from the key"
bad = [f"{r.row_id} ({r.prompt_id}): label = {r.label!r}" for r in df.itertuples()
       if str(r.label).strip().upper() not in {"TP", "FP", "FN", "TN"}]
if bad: print("\n".join(bad)); sys.exit(f"{len(bad)} row(s) without a valid label: finish the sheet first")
df["label"] = df["label"].str.strip().str.upper()
new = {}          # (system, prompt_id) -> label from the new grader
for r in df.itertuples():
    for s in r.systems.split("+"): new[(s, r.prompt_id)] = r.label

refA = pd.read_csv(os.path.join(a.ref_dir, f"benchmark_{S}-ft-run1-bf16.csv")).set_index("id")
refC = pd.read_csv(os.path.join(a.ref_dir, f"vulnerabilites_{S}-ft-run1-bf16.csv")).set_index("id")
cref = {pid: str(refA.loc[pid, "bug_label"]).upper() for pid in ("P7", "P8", "P9")}
cref.update({pid: str(refC.loc[pid, "vuln_label"]).upper() for pid in refC.index})

# ---- inter-grader agreement on the 12 anchors ----
anc = [(pid, new[("ft_bf16", pid)], cref[pid]) for (s, pid) in new if s == "ft_bf16"]
agree = sum(x == y for _, x, y in anc)
print(f"Anchor agreement (new grader vs member C, same bf16 answers): {agree}/{len(anc)}")
for pid, x, y in sorted(anc):
    if x != y: print(f"   disagreement {pid}: new={x} | C={y}")

def prf1(l):
    tp, fp, fn = (sum(x == k for x in l) for k in ("TP", "FP", "FN"))
    p = tp / (tp + fp) if tp + fp else None; r = tp / (tp + fn) if tp + fn else None
    f = None if p is None or r is None else (0.0 if p + r == 0 else 2 * p * r / (p + r))
    return p, r, f

os.makedirs(a.out, exist_ok=True)
labels = {"bf16": {pid: cref[pid] for pid in cref}}
for v in ("fp16", "int8", "nf4"):
    A = pd.read_csv(os.path.join(a.quant_dir, f"benchmark_{S}__ft__{v}.csv")).set_index("id")
    C = pd.read_csv(os.path.join(a.quant_dir, f"vulnerabilites_{S}__ft__{v}.csv")).set_index("id")
    L = {}
    for pid in ("P7", "P8", "P9"):
        L[pid] = cref[pid] if bool(A.loc[pid, "same_as_bf16"]) else new[(f"ft_{v}", pid)]
    for pid in C.index:
        L[pid] = cref[pid] if bool(C.loc[pid, "same_as_ref"]) else new[(f"ft_{v}", pid)]
    labels[v] = L
    A["bug_label"] = [L.get(i) if i in ("P7", "P8", "P9") else None for i in A.index]
    C["vuln_label"] = [L[i] for i in C.index]
    A.reset_index().to_csv(os.path.join(a.out, f"benchmark_{S}__ft__{v}.csv"), index=False)
    C.reset_index().to_csv(os.path.join(a.out, f"vulnerabilites_{S}__ft__{v}.csv"), index=False)

rows = []
for v, L in labels.items():
    bug = [L[p] for p in ("P7", "P8", "P9")]; vul = [L[k] for k in L if k.startswith("V")]
    bp, br, bf = prf1(bug); vp, vr, vf = prf1(vul)
    rows.append({"variant": v, "bug_P": bp, "bug_R": br, "bug_F1": bf,
                 "vuln_P": vp, "vuln_R": vr, "vuln_F1": vf,
                 "vuln_TP": vul.count("TP"), "vuln_FP": vul.count("FP"), "vuln_FN": vul.count("FN"), "vuln_TN": vul.count("TN")})
res = pd.DataFrame(rows).set_index("variant").round(3)
res.to_csv(os.path.join(a.out, "summary_quant_grading.csv"))
print(res.T.to_string())
print("\nbf16 labels are member C's. With 6 vulnerable prompts, differences are descriptive, not statistical.")
