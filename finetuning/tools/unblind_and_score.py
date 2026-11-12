"""Unblind the graded sheet and compute the grading metrics for base vs fine-tuned.

Usage (after ALL rows are graded):
  python unblind_and_score.py --sheet grading_sheet_blind.xlsx --key blind_key_DO_NOT_OPEN.csv \
      --base-dir <folder with benchmark_...-ctrl.csv and vulnerabilites_...-ctrl.csv> \
      --ft-dir   <folder with benchmark_...-ft-run1-bf16.csv and vulnerabilites_...-ft-run1-bf16.csv> \
      --out graded
Writes graded copies of the result CSVs (manual columns filled) and summary_blind_grading.csv.
"""
import argparse, os, sys
import pandas as pd

BASE_SLUG = "qwen2.5-coder-1.5b-instruct-ctrl"
FT_SLUG = "qwen2.5-coder-1.5b-instruct-ft-run1-bf16"
ap = argparse.ArgumentParser()
ap.add_argument("--sheet", required=True); ap.add_argument("--key", required=True)
ap.add_argument("--base-dir", required=True); ap.add_argument("--ft-dir", required=True)
ap.add_argument("--out", default="graded")
a = ap.parse_args()

if a.sheet.lower().endswith(".csv"):      # sheet exported as CSV from Excel/Sheets
    raw = open(a.sheet, "rb").read()
    try: txt_enc = "utf-8-sig"; raw.decode(txt_enc)
    except UnicodeDecodeError: txt_enc = "cp1252"
    g = pd.read_csv(a.sheet, dtype=str, encoding=txt_enc, sep=None, engine="python")
    g = g.loc[:, ~g.columns.astype(str).str.startswith("Unnamed")]
else:
    g = pd.read_excel(a.sheet, sheet_name="Grading", dtype=str)
key = pd.read_csv(a.key, dtype=str)
df = g.merge(key[["row_id", "system"]], on="row_id", how="left")
assert df["system"].notna().all(), "a row_id is missing from the key"

def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    v = str(v).strip()
    return None if v in ("", "n/a", "nan") else v

# --- completeness and value checks (fail loudly, never score a half-graded sheet) ---
errors = []
for _, r in df.iterrows():
    pid = r["prompt_id"]; n = int(pid[1:]); isP = pid.startswith("P")
    need = []
    if isP and pid in ("P7", "P8", "P9"): need.append(("bug_label", {"TP", "FP", "FN", "TN"}))
    if pid.startswith("V"): need.append(("vuln_label", {"TP", "FP", "FN", "TN"}))
    if isP and 10 <= n <= 15: need.append(("note_qualite", {"1", "2", "3", "4", "5"}))
    if clean(r["hallucination"]) is not None or (isP and "```" in str(r["response"])):
        need.append(("hallucination", {"oui", "non"}))
    for col, ok in need:
        v = clean(r[col])
        if v is None: errors.append(f"{r['row_id']} ({pid}): {col} is empty")
        else:
            v = v.upper() if col.endswith("label") else v.lower()
            if col == "note_qualite": v = str(int(float(v)))
            if v not in ({x.upper() for x in ok} if col.endswith("label") else ok):
                errors.append(f"{r['row_id']} ({pid}): invalid {col} = {r[col]!r}")
if errors:
    print("\n".join(errors[:40])); sys.exit(f"{len(errors)} problem(s): finish/fix the sheet first")

def expand(df):
    # rows graded as 'both' (identical answers) count for both systems
    out = []
    for _, r in df.iterrows():
        for s in (["base", "ft"] if r["system"] == "both" else [r["system"]]):
            d = r.to_dict(); d["system"] = s; out.append(d)
    return pd.DataFrame(out)
ex = expand(df)

def prf1(labels):
    tp, fp, fn = (sum(l == k for l in labels) for k in ("TP", "FP", "FN"))
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = None if p is None or r is None else (0.0 if p + r == 0 else 2 * p * r / (p + r))
    return p, r, f

os.makedirs(a.out, exist_ok=True)
summary = []
for sysname, folder, slug in (("base", a.base_dir, BASE_SLUG), ("ft", a.ft_dir, FT_SLUG)):
    sub = ex[ex["system"] == sysname].set_index("prompt_id")
    b = pd.read_csv(os.path.join(folder, f"benchmark_{slug}.csv")).set_index("id")
    v = pd.read_csv(os.path.join(folder, f"vulnerabilites_{slug}.csv")).set_index("id")
    for col in ("bug_label", "note_qualite", "hallucination"): b[col] = b[col].astype(object)
    v["vuln_label"] = v["vuln_label"].astype(object)
    for pid, r in sub.iterrows():
        if pid.startswith("V"):
            lab = clean(r["vuln_label"]);  v.loc[pid, "vuln_label"] = lab.upper() if lab else None
        else:
            if clean(r["bug_label"]): b.loc[pid, "bug_label"] = clean(r["bug_label"]).upper()
            if clean(r["note_qualite"]): b.loc[pid, "note_qualite"] = int(float(clean(r["note_qualite"])))
            if clean(r["hallucination"]): b.loc[pid, "hallucination"] = clean(r["hallucination"]).lower()
    b.reset_index().to_csv(os.path.join(a.out, f"benchmark_{slug}.csv"), index=False)
    v.reset_index().to_csv(os.path.join(a.out, f"vulnerabilites_{slug}.csv"), index=False)
    bl = [str(x).upper() for x in b["bug_label"].dropna()]; vl = [str(x).upper() for x in v["vuln_label"].dropna()]
    bp, br, bf = prf1(bl); vp, vr, vf = prf1(vl)
    notes = pd.to_numeric(b["note_qualite"], errors="coerce").dropna()
    h = b["hallucination"].dropna().astype(str).str.lower(); h = h[h.isin(["oui", "non"])]
    summary.append({"system": sysname, "bug_precision": bp, "bug_recall": br, "bug_f1": bf, "n_bug": len(bl),
                    "vuln_precision": vp, "vuln_recall": vr, "vuln_f1": vf, "n_vuln": len(vl),
                    "mean_quality_P10_P15": notes.mean(), "n_notes": len(notes),
                    "hallucinations": int((h == "oui").sum()), "n_judged_hallu": len(h),
                    "hallucination_rate_pct": 100 * (h == "oui").mean() if len(h) else None})
res = pd.DataFrame(summary).set_index("system").round(3)
res.to_csv(os.path.join(a.out, "summary_blind_grading.csv"))
print(res.T.to_string())
print("\nWritten to", a.out, "- with so few items, differences are descriptive, not statistical.")
