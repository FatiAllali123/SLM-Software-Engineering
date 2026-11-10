"""Prepare QLoRA training data: decontaminate, filter, split, format. CPU only.
No code from the dataset is ever executed."""
import json, os, re, random, collections
from importlib.metadata import version

REPO_BENCH = "/kaggle/working/SLM-Software-Engineering/benchmarking"
OUT_DIR = "/kaggle/working/ft_data"
CFG = {
    "dataset": "ise-uiuc/Magicoder-OSS-Instruct-75K",
    "lang": "python",
    "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
    "seed": 42,
    "ngram_n": 10,                      # used for filtering
    "ngram_sensitivity": [8, 10, 13],   # counts only (ngram_n must be in this list)
    "min_name_len": 5,
    "max_seq_len": 2048,
    "train_n": 6000,
    "val_n": 300,
}
os.makedirs(OUT_DIR, exist_ok=True)

from datasets import load_dataset
from transformers import AutoTokenizer

TOK_RE = re.compile(r"[A-Za-z_]\w*|\d+|\S")
def toks(text): return TOK_RE.findall(text.lower())

# ---------- 1. evaluation texts that must not appear in training data ----------
eval_items, entry_points = [], set()
he = load_dataset("openai/openai_humaneval", split="test")
assert len(he) == 164, len(he)
for ex in he:
    for field in ("prompt", "canonical_solution", "test"):
        eval_items.append((ex["task_id"], ex[field]))
    entry_points.add(ex["entry_point"])

def strings_of(d, skip=("id", "task")):
    return [v for k, v in d.items() if k not in skip and isinstance(v, str) and v.strip()]

prompts = json.load(open(f"{REPO_BENCH}/prompts.json", encoding="utf-8"))["prompts"]
sec = json.load(open(f"{REPO_BENCH}/prompts_securite.json", encoding="utf-8"))["prompts"]
for p in prompts + sec:
    for s in strings_of(p):
        eval_items.append((p["id"], s))
print("eval texts:", len(eval_items), "| prompts:", len(prompts), "| security prompts:", len(sec))

DEF_RE = re.compile(r"def\s+([A-Za-z_]\w*)\s*\(")
FR_RE = re.compile(r"fonction Python\s+([A-Za-z_]\w*)\s*\(")
names = set(entry_points)
for p in prompts:
    for s in strings_of(p):
        names.update(DEF_RE.findall(s)); names.update(FR_RE.findall(s))
GENERIC = {"wrapper", "solve", "solution", "main", "helper"}
names = {n for n in names if len(n) >= CFG["min_name_len"] and not n.startswith("__") and n not in GENERIC}
print("protected function names:", len(names))

def build_index(n):
    idx, skipped = {}, 0
    for label, text in eval_items:
        t = toks(text)
        if len(t) < n:
            skipped += 1
            continue
        for i in range(len(t) - n + 1):
            idx.setdefault(tuple(t[i:i + n]), label)
    return idx, skipped

indexes, skipped = {}, {}
for N in CFG["ngram_sensitivity"]:
    indexes[N], skipped[N] = build_index(N)
MAIN_N = CFG["ngram_n"]
assert MAIN_N in indexes

# ---------- 2. decontaminate the Python pool ----------
ds = load_dataset(CFG["dataset"], split="train")
print("dataset rows:", len(ds))
pool = [i for i, l in enumerate(ds["lang"]) if l == CFG["lang"]]
print(f"{CFG['lang']} pool:", len(pool))

sens_count = collections.Counter()
label_count = {N: collections.Counter() for N in indexes}
name_count = collections.Counter()
kept, removed = [], {}
for r in pool:
    ex = ds[r]
    t = toks(ex["problem"] + "\n" + ex["solution"])
    main_hits = set()
    for N, idx in indexes.items():
        hits = set()
        for i in range(len(t) - N + 1):
            lab = idx.get(tuple(t[i:i + N]))
            if lab: hits.add(lab)
        if hits:
            sens_count[N] += 1
            label_count[N].update(hits)
        if N == MAIN_N: main_hits = hits
    defined = set(DEF_RE.findall(ex["solution"] + "\n" + ex["problem"])) & names
    name_count.update(defined)
    if main_hits or defined:
        removed[r] = {"ngram": sorted(main_hits), "names": sorted(defined)}
    else:
        kept.append(r)

n_ng = sum(1 for v in removed.values() if v["ngram"])
n_nm = sum(1 for v in removed.values() if v["names"])
n_both = sum(1 for v in removed.values() if v["ngram"] and v["names"])
print(f"removed total {len(removed)} (n-gram {n_ng}, name {n_nm}, both {n_both}) -> kept {len(kept)}")
print("n-gram sensitivity (examples with >=1 hit):", {N: sens_count[N] for N in indexes})
print("eval texts skipped (shorter than n):", skipped)
print("top eval items hit (n=%d):" % MAIN_N, label_count[MAIN_N].most_common(15))
print("top function-name hits:", name_count.most_common(15))

# ---------- 3. template check, length filter, split ----------
tok = AutoTokenizer.from_pretrained(CFG["model"])
probe = "Write a Python function add(a, b) that returns a + b."
eval_prefix = tok.apply_chat_template([{"role": "user", "content": probe}],
                                      add_generation_prompt=True, tokenize=False)
train_text = tok.apply_chat_template([{"role": "user", "content": probe},
                                      {"role": "assistant", "content": "x"}], tokenize=False)
assert train_text.startswith(eval_prefix), "Training template differs from the benchmark prompt format"
print("eval prompt prefix:", repr(eval_prefix))

rng = random.Random(CFG["seed"]); rng.shuffle(kept)
need = CFG["val_n"] + CFG["train_n"]
selected, too_long, examined = [], 0, 0
for r in kept:
    ex = ds[r]
    msgs = [{"role": "user", "content": ex["problem"]},
            {"role": "assistant", "content": ex["solution"]}]
    text = tok.apply_chat_template(msgs, tokenize=False)
    n_tok = len(tok(text, add_special_tokens=False)["input_ids"])
    examined += 1
    if n_tok > CFG["max_seq_len"]:
        too_long += 1; continue
    selected.append((r, msgs, n_tok))
    if len(selected) == need: break
assert len(selected) == need, f"only {len(selected)} examples available"
val, train = selected[:CFG["val_n"]], selected[CFG["val_n"]:]

def dump(path, items):
    with open(path, "w", encoding="utf-8") as f:
        for r, msgs, n_tok in items:
            f.write(json.dumps({"row_id": r, "raw_index": ds[r]["raw_index"],
                                "messages": msgs, "n_tokens": n_tok}, ensure_ascii=False) + "\n")
dump(f"{OUT_DIR}/train.jsonl", train)
dump(f"{OUT_DIR}/val.jsonl", val)

nt = sorted(x[2] for x in train)
tok_stats = {"mean": round(sum(nt) / len(nt), 1), "median": nt[len(nt) // 2], "max": nt[-1]}
report = {
    "config": CFG,
    "versions": {"datasets": version("datasets"), "transformers": version("transformers")},
    "dataset_rows": len(ds), "pool_rows": len(pool),
    "eval_texts": len(eval_items), "eval_texts_skipped_short": skipped,
    "protected_function_names": sorted(names), "generic_names_excluded": sorted(GENERIC),
    "removed_total": len(removed), "removed_ngram": n_ng, "removed_name": n_nm, "removed_both": n_both,
    "kept_after_decontamination": len(kept),
    "ngram_sensitivity_counts": {str(N): sens_count[N] for N in indexes},
    "top_eval_items_hit": label_count[MAIN_N].most_common(30),
    "name_hits": name_count.most_common(30),
    "examined_for_length": examined, "dropped_too_long": too_long,
    "train_examples": len(train), "val_examples": len(val), "train_token_stats": tok_stats,
}
json.dump(report, open(f"{OUT_DIR}/report.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
json.dump({str(k): v for k, v in removed.items()}, open(f"{OUT_DIR}/removed_row_ids.json", "w"))
print("train token stats:", tok_stats, "| too long dropped:", too_long, "of", examined)
print("wrote", OUT_DIR)
