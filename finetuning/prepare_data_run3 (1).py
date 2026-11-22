"""Run 3 data: a software-engineering task mix (code generation + test generation + bug fixing/refactoring + security review).

Sources (licences read from the dataset pages on 21-22 Nov 2026; re-verify before publishing):
  A  Run 1 data (Magicoder OSS-Instruct, Python)             MIT          code generation
  B  nvidia/OpenCodeInstruct                                 CC BY 4.0    test generation (execution-validated unit tests)
  C  bigcode/commitpackft (python, permissive repo licences) card: MIT    bug fixing / refactoring (commit = instruction)
  D  CyberNative/Code_Vulnerability_Security_DPO             Apache-2.0   security review (synthetic, fields checked at run time)
  E  Helmcode/stack-v3-devops (dockerfile, workflow configs) ODC-By       DevOps: Dockerfile and GitHub Actions from a spec derived from the file
  F  docstring tasks built from B (CC BY 4.0) and explanation tasks built from A (MIT): documentation and code explanation

Every example is decontaminated against: all 164 HumanEval problems (prompt, solution, tests), P1-P15, V1-V9 and V10-V39.
Nothing from any dataset is executed. Output: train.jsonl, val.jsonl, report.json (+ sha256 of both files).

  python prepare_data_run3.py --bench <repo>/benchmarking --run1-dir /kaggle/working/ft_data --out /kaggle/working/ft_data_run3
"""
import argparse, ast, glob, hashlib, json, math, os, random, re, sys, collections, warnings
warnings.filterwarnings("ignore", category=SyntaxWarning)   # dataset code often has invalid escapes: harmless when only parsing

SEED = 42
QUOTA = {"gen": 3000, "test": 2000, "bugfix": 1000, "refactor": 1000, "sec_vuln": 500, "sec_safe": 500,
         "docs": 500, "explain": 500, "dockerfile": 500, "workflow": 500}
VAL = {"gen": 150, "test": 100, "edit": 100, "sec": 50, "docs": 25, "explain": 25, "devops": 50}
MAX_TOKENS = 2048
NGRAM = 10
PERMISSIVE = {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc", "cc0-1.0", "unlicense"}
PERMISSIVE_WORDS = {"permissive", "public domain", "public_domain", "publicdomain"}
GENERIC = {"wrapper", "solve", "solution", "main", "helper", "test", "setup", "run", "process", "update", "build"}
TOK = re.compile(r"[A-Za-z_]\w*|\d+|\S")
DEF_RE = re.compile(r"def\s+([A-Za-z_]\w*)\s*\(")
BUGFIX_RE = re.compile(r"\b(fix|fixes|fixed|bug|crash|error|typo|wrong|incorrect|broken)\b", re.I)
REFACTOR_RE = re.compile(r"\b(refactor|refactoring|clean ?up|simplify|rename|extract|reorganize|restructure)\b", re.I)
toks = lambda t: TOK.findall(t.lower())

# ---------------- secret scan (same heuristics as the Run 1 scan; examples with hits are dropped) ----------------
SECRET_PATTERNS = {
    "aws": r"\bAKIA[0-9A-Z]{16}\b", "github": r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "slack": r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
    "google": r"\bAIza[0-9A-Za-z_\-]{35}\b", "stripe": r"\bsk_live_[0-9a-zA-Z]{24,}\b", "sk": r"\bsk-[A-Za-z0-9]{32,}\b",
    "privkey": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
}
ASSIGN = re.compile(r"(?i)\b(?:api[_-]?key|secret|token|passwd|password|access[_-]?key)\w*\s*[=:]\s*['\"]([^'\"\s]{20,})['\"]")
PLACEHOLDER = re.compile(r"(?i)example|your|xxx|changeme|dummy|placeholder|test|sample|fake|<|\{|\$|1234|abcd|secret|password|token")
def entropy(s): return -sum((s.count(c) / len(s)) * math.log2(s.count(c) / len(s)) for c in set(s))
def has_secret(text):
    if any(re.search(p, text) for p in SECRET_PATTERNS.values()): return True
    for m in ASSIGN.finditer(text):
        v = m.group(1)
        if not PLACEHOLDER.search(v) and entropy(v) >= 3.5: return True
    return False

# ---------------- helpers ----------------
def first_code_block(text):
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return m.group(1).strip("\n") if m else None

def build_eval_index(eval_texts, n=NGRAM):
    idx = {}
    for label, text in eval_texts:
        t = toks(text)
        for i in range(len(t) - n + 1): idx.setdefault(tuple(t[i:i + n]), label)
    return idx

def contaminated(text, idx, names, n=NGRAM):
    t = toks(text)
    for i in range(len(t) - n + 1):
        if tuple(t[i:i + n]) in idx: return "ngram"
    if set(DEF_RE.findall(text)) & names: return "name"
    return None

def count_tokens_factory(model_name, use_tokenizer=True):
    if not use_tokenizer: return lambda msgs: sum(len(m["content"]) // 3 for m in msgs) + 30
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_name)
    return lambda msgs: len(tok(tok.apply_chat_template(msgs, tokenize=False), add_special_tokens=False)["input_ids"])

# ---------------- builders (each takes an iterable of raw rows, returns a list of candidate examples) ----------------
def make_doc_example(code):
    """Take a function that has a docstring, remove the docstring, ask to add one back (answer = original code)."""
    try: tree = ast.parse(code)
    except Exception: return None
    lines = code.split("\n")
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and ast.get_docstring(node) and node.body and isinstance(node.body[0], ast.Expr):
            d = node.body[0]
            stripped = lines[:d.lineno - 1] + lines[d.end_lineno:]
            body = "\n".join(stripped)
            try: ast.parse(body)
            except Exception: return None
            if len(ast.get_docstring(node)) < 25: return None
            return body, code
    return None

def build_testgen(rows, limit_scan):
    docs = []
    out, seen = [], 0
    for row in rows:
        seen += 1
        if seen > limit_scan: break
        try:
            if float(row["average_test_score"]) < 1.0: continue
            status = ast.literal_eval(row["tests_execution_status"]); tests = ast.literal_eval(row["unit_tests"])
        except Exception: continue
        if not tests or not all(s == "pass" for s in status): continue
        tests = [t.strip() for t in tests if isinstance(t, str)][:8]
        if not tests or any(len(t) > 240 or "\n" in t for t in tests): continue
        code = first_code_block(row.get("output", "") or "")
        if not code or "def " not in code or len(code) > 1500: continue
        names = {n for n in DEF_RE.findall(code) if not n.startswith("_")} | set(re.findall(r"class\s+([A-Za-z]\w*)", code))
        if not any(n in "\n".join(tests) for n in names): continue
        prompt = ("Write unit tests for this Python code. Use plain `assert` statements, one per line, "
                  "covering normal cases and edge cases.\n\n```python\n" + code + "\n```")
        de = make_doc_example(code)
        if de:
            nodoc, withdoc = de
            docs.append({"source": "F_docs_from_opencodeinstruct", "task": "docs", "row_id": row.get("id"), "text_check": withdoc,
                         "messages": [{"role": "user", "content": "Add a clear docstring to this Python function (describe what it does, its parameters and its return value). Return the complete function.\n\n```python\n" + nodoc + "\n```"},
                                      {"role": "assistant", "content": "```python\n" + withdoc + "\n```"}]})
        out.append({"source": "B_opencodeinstruct", "task": "test", "row_id": row.get("id"),
                    "text_check": code + "\n" + "\n".join(tests),
                    "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": "```python\n" + "\n".join(tests) + "\n```"}]})
    return out, docs, seen

def build_edits(rows, limit_scan):
    out, seen = [], 0
    for row in rows:
        seen += 1
        if seen > limit_scan: break
        lic = str(row.get("license", "")).lower()
        if lic not in PERMISSIVE: continue
        old, new, subj = row.get("old_contents") or "", row.get("new_contents") or "", (row.get("subject") or "").strip()
        if not old or not new or old.strip() == new.strip(): continue
        if not (10 <= len(subj) <= 120) or len(old) > 2500 or len(new) > 2500: continue
        kind = "bugfix" if BUGFIX_RE.search(subj) else "refactor" if REFACTOR_RE.search(subj) else None
        if not kind: continue
        fname = os.path.basename(row.get("old_file") or "module.py")
        prompt = (f"Apply this change to the Python file.\nChange request: {subj}\n\nFile `{fname}`:\n```python\n{old}\n```\n"
                  "Return the complete updated file.")
        out.append({"source": "C_commitpackft", "task": kind, "row_id": row.get("commit"),
                    "text_check": old + "\n" + new,
                    "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": "```python\n" + new.rstrip("\n") + "\n```"}]})
    return out, seen

def build_security(rows, columns):
    need = {"question", "chosen", "rejected"}
    if not need <= set(columns):
        raise SystemExit(f"CyberNative columns are {columns}: expected at least {sorted(need)}. Send me this line and I will adapt the mapping.")
    out = []
    for row in rows:
        lang = str(row.get("lang", "python")).lower()
        if lang != "python": continue
        bad, good = row["rejected"], row["chosen"]
        vul = (row.get("vulnerability") or "").strip()
        if not bad or not good or len(bad) > 2500 or len(good) > 2500: continue
        if vul:
            ans = f"Yes, this code has a security vulnerability.\n\nVulnerability: {vul}\n\nFixed version:\n```python\n{good.strip()}\n```"
            out.append({"source": "D_cybernative", "task": "sec_vuln", "row_id": None, "text_check": bad + "\n" + good,
                        "messages": [{"role": "user", "content": "Does this Python code have a security vulnerability? If yes, name it and give a fixed version.\n\n```python\n" + bad.strip() + "\n```"},
                                     {"role": "assistant", "content": ans}]})
        out.append({"source": "D_cybernative", "task": "sec_safe", "row_id": None, "text_check": good,
                    "messages": [{"role": "user", "content": "Does this Python code have a security vulnerability? If yes, name it and give a fixed version.\n\n```python\n" + good.strip() + "\n```"},
                                 {"role": "assistant", "content": "No security vulnerability found in this code. It follows safe practices for the operations it performs."}]})
    return out

def build_explain(rows):
    """Explanation tasks from Run 1 examples whose answer is code followed by a prose explanation."""
    out = []
    for r in rows:
        ans = r["messages"][-1]["content"]
        blocks = list(re.finditer(r"```(?:python|py)?\s*\n(.*?)```", ans, re.S))
        if len(blocks) != 1: continue
        b = blocks[0]; code, after = b.group(1).strip("\n"), ans[b.end():].strip()
        if len(after) < 200 or "```" in after or len(code) > 1500 or len(code) < 80: continue
        out.append({"source": "F_explain_from_magicoder", "task": "explain", "row_id": r.get("row_id"), "text_check": code + "\n" + after,
                    "messages": [{"role": "user", "content": "Explain what this Python code does and how it works.\n\n```python\n" + code + "\n```"},
                                 {"role": "assistant", "content": after}]})
    return out

def license_ok(row):
    lts = [str(x).lower() for x in (row.get("license_types") or [f.get("license_type") for f in (row.get("files") or [])]) if x]
    if lts and all(x in PERMISSIVE_WORDS for x in lts): return True
    det = []
    for f in (row.get("files") or []):
        det += [str(x).lower() for x in (f.get("detected_licenses") or [])]
    return bool(det) and all(x in PERMISSIVE for x in det)

def dockerfile_spec(content):
    ins = [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    first = lambda kw: next((l[len(kw):].strip() for l in ins if l.upper().startswith(kw + " ")), None)
    allk = lambda kw: [l[len(kw):].strip() for l in ins if l.upper().startswith(kw + " ")]
    base, cmd, ent = first("FROM"), first("CMD"), first("ENTRYPOINT")
    if not base or not (cmd or ent) or len(ins) < 4: return None
    spec = [f"- Base image: {base.split(' AS ')[0].split(' as ')[0]}"]
    if first("WORKDIR"): spec.append(f"- Working directory: {first('WORKDIR')}")
    if allk("ENV"): spec.append("- Environment variables: " + ", ".join(e.split("=")[0].split()[0] for e in allk("ENV")[:4]))
    if allk("EXPOSE"): spec.append("- Exposed port(s): " + ", ".join(allk("EXPOSE")))
    runs = allk("RUN")
    if runs: spec.append(f"- {len(runs)} RUN step(s), for example: {runs[0][:80]}")
    if allk("COPY") or allk("ADD"): spec.append("- Copies the application files into the image")
    if first("USER"): spec.append(f"- Runs as user: {first('USER')}")
    spec.append(f"- Container start: {'ENTRYPOINT ' + ent if ent else 'CMD ' + cmd}"[:140])
    return "\n".join(spec)

def workflow_spec(content):
    import yaml
    try: d = yaml.safe_load(content)
    except Exception: return None
    if not isinstance(d, dict) or not isinstance(d.get("jobs"), dict): return None
    trig = d.get("on", d.get(True))
    if trig is None: return None
    jobs = d["jobs"]
    if not (1 <= len(jobs) <= 3): return None
    if isinstance(trig, dict): tr = ", ".join(f"{k}" + (f" ({', '.join(str(x) for x in v['branches'])})" if isinstance(v, dict) and isinstance(v.get("branches"), list) else "") for k, v in trig.items())
    elif isinstance(trig, list): tr = ", ".join(str(x) for x in trig)
    else: tr = str(trig)
    spec = [f"- Name: {d.get('name', 'CI')}", f"- Triggers: {tr}"]
    for jn, j in jobs.items():
        if not isinstance(j, dict) or not isinstance(j.get("steps"), list) or len(j["steps"]) > 8: return None
        steps = []
        for st in j["steps"]:
            if not isinstance(st, dict): return None
            if "uses" in st: steps.append("uses " + str(st["uses"]).split("@")[0])
            elif "run" in st: steps.append("runs `" + str(st["run"]).strip().splitlines()[0][:70] + "`")
        spec.append(f"- Job `{jn}` on {j.get('runs-on', 'ubuntu-latest')}: " + "; ".join(steps))
    return "\n".join(spec)

def build_devops(rows, kind, limit_scan):
    out, seen, lic_seen = [], 0, collections.Counter()
    for row in rows:
        seen += 1
        if seen > limit_scan: break
        files = row.get("files") or []
        for f in files: lic_seen[str(f.get("license_type"))] += 1
        if len(files) != 1 or not license_ok(row): continue
        content = files[0].get("content") or ""
        if not (80 <= len(content) <= 2200): continue
        spec = dockerfile_spec(content) if kind == "dockerfile" else workflow_spec(content)
        if not spec: continue
        if kind == "dockerfile": prompt, lang = "Write a Dockerfile that meets these requirements:\n" + spec, "dockerfile"
        else: prompt, lang = "Write a GitHub Actions workflow file (YAML) that meets these requirements:\n" + spec, "yaml"
        out.append({"source": "E_stack_v3_devops", "task": kind, "row_id": None, "text_check": content,
                    "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": f"```{lang}\n" + content.strip("\n") + "\n```"}]})
    return out, seen, dict(lic_seen.most_common(8))

# ---------------- main ----------------
def load_eval_texts(bench, extra_path=None):
    from datasets import load_dataset
    he = load_dataset("openai/openai_humaneval", split="test"); assert len(he) == 164
    texts, names = [], set()
    for ex in he:
        for f in ("prompt", "canonical_solution", "test"): texts.append((ex["task_id"], ex[f]))
        names.add(ex["entry_point"])
    def strings(d): return [v for k, v in d.items() if k not in ("id", "task") and isinstance(v, str) and v.strip()]
    files = [f"{bench}/prompts.json", f"{bench}/prompts_securite.json"]
    extra = extra_path or f"{bench}/prompts_securite_extra.json"
    if not os.path.exists(extra):
        hits = glob.glob("/kaggle/input/**/prompts_securite_extra.json", recursive=True); extra = hits[0] if hits else None
    assert extra and os.path.exists(extra), "prompts_securite_extra.json not found: push it to the repo main branch or add it as an Input"
    files.append(extra)
    for f in files:
        for p in json.load(open(f, encoding="utf-8"))["prompts"]:
            for s in strings(p):
                texts.append((p["id"], s)); names.update(DEF_RE.findall(s))
    names = {n for n in names if len(n) >= 5 and not n.startswith("__") and n not in GENERIC}
    return texts, names, len(files)

def read_jsonl(path, limit):
    rows = []
    for line in open(path, encoding="utf-8"):
        rows.append(json.loads(line))
        if len(rows) == limit: break
    return rows

def main(argv=None, streams=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", required=True); ap.add_argument("--run1-dir", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="Qwen/Qwen2.5-Coder-1.5B-Instruct"); ap.add_argument("--scan-limit", type=int, default=400000)
    ap.add_argument("--no-tokenizer", action="store_true"); ap.add_argument("--eval-texts-file")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True); rng = random.Random(SEED)

    if streams is None:
        from datasets import load_dataset
        def stream_opencode():
            return load_dataset("nvidia/OpenCodeInstruct", split="train", streaming=True).shuffle(seed=SEED, buffer_size=20000)
        def stream_commit():
            try: return load_dataset("bigcode/commitpackft", "python", split="train", streaming=True)
            except Exception as e:
                print("commitpackft config load failed, trying the json file:", type(e).__name__)
                return load_dataset("json", data_files="hf://datasets/bigcode/commitpackft/data/python/data.jsonl", split="train", streaming=True)
        def load_cyber():
            d = load_dataset("CyberNative/Code_Vulnerability_Security_DPO", split="train"); return list(d), d.column_names
        def stream_devops(kind):
            return lambda: load_dataset("Helmcode/stack-v3-devops", kind, split="train", streaming=True).shuffle(seed=SEED, buffer_size=10000)
        streams = {"opencode": stream_opencode, "commit": stream_commit, "cyber": load_cyber,
                   "dockerfile": stream_devops("dockerfile"), "workflow": stream_devops("workflow")}

    eval_texts, names, nfiles = load_eval_texts(a.bench) if not a.eval_texts_file else (json.load(open(a.eval_texts_file))["texts"], set(json.load(open(a.eval_texts_file))["names"]), 0)
    idx = build_eval_index(eval_texts)
    print(f"eval texts: {len(eval_texts)} | protected names: {len(names)} | n-gram index: {len(idx)}")
    count_tokens = count_tokens_factory(a.model, not a.no_tokenizer)

    report = {"seed": SEED, "quota": QUOTA, "ngram": NGRAM, "removed": {}, "scanned": {}, "available_after_filters": {}}
    pools = {}

    # A: Run 1 generation examples (re-decontaminated against the new V10-V39 prompts too)
    for split, key, n in (("train", "gen", QUOTA["gen"]), ("val", "gen_val", VAL["gen"])):
        rows = read_jsonl(os.path.join(a.run1_dir, f"{split}.jsonl"), None)
        kept, rem = [], 0
        for r in rows:
            text = "\n".join(m["content"] for m in r["messages"])
            if contaminated(text, idx, names): rem += 1; continue
            kept.append({"source": "A_magicoder_run1", "task": "gen", "row_id": r.get("row_id"), "messages": r["messages"]})
        pools[key] = kept[:n]; report["removed"][f"A_{split}"] = rem

    # B, C, D
    print("reading OpenCodeInstruct (streaming)...", flush=True)
    cand_b, cand_docs, seen_b = build_testgen(streams["opencode"](), a.scan_limit); report["scanned"]["B"] = seen_b
    print(f"  OpenCodeInstruct: scanned {seen_b} rows -> {len(cand_b)} test-generation and {len(cand_docs)} docstring candidates", flush=True)
    print("reading CommitPackFT (streaming)...", flush=True)
    try: cand_c, seen_c = build_edits(streams["commit"](), a.scan_limit)
    except Exception as e: raise SystemExit(f"CommitPackFT could not be read: {type(e).__name__}: {str(e)[:300]}. Send me this line.")
    report["scanned"]["C"] = seen_c
    print(f"  CommitPackFT: scanned {seen_c} rows -> {len(cand_c)} bugfix/refactor candidates", flush=True)
    rows_d, cols_d = streams["cyber"](); cand_d = build_security(rows_d, cols_d); report["cyber_columns"] = cols_d
    cand_e, cand_x = [], []
    for kind in ("dockerfile", "workflow"):
        c, n_seen, lic = build_devops(streams[kind](), kind, a.scan_limit // 4)
        cand_e += c; report["scanned"][f"E_{kind}"] = n_seen; report.setdefault("devops_license_types_seen", {})[kind] = lic
        if not c: raise SystemExit(f"No usable {kind} rows. License types seen in the first rows: {lic}. Send me this line and I will adapt the filter.")

    def valid_text(c):
        try:
            for m in c["messages"]: m["content"].encode("utf-8")
            c["text_check"].encode("utf-8"); return True
        except Exception: return False

    def clean(cands, label):
        kept = {"ngram": 0, "name": 0, "secret": 0, "tokens": 0, "bad_text": 0, "tokenize_error": 0}; ok = []
        for c in cands:
            if not valid_text(c): kept["bad_text"] += 1; continue
            why = contaminated(c["text_check"], idx, names)
            if why: kept[why] += 1; continue
            if has_secret(c["text_check"]): kept["secret"] += 1; continue
            try: n_tok = count_tokens(c["messages"])
            except Exception: kept["tokenize_error"] += 1; continue
            if n_tok > MAX_TOKENS: kept["tokens"] += 1; continue
            c["n_tokens"] = n_tok; c.pop("text_check", None); ok.append(c)
        print(f"  cleaned {label}: {len(ok)} kept of {len(cands)} | removed: {kept}", flush=True)
        report["removed"][label] = kept; return ok

    def cap(cands, per_task):
        by = collections.defaultdict(list)
        for c in cands: by[c["task"]].append(c)
        out = []
        for t, v in by.items(): rng.shuffle(v); out += v[:per_task]
        return out
    run1_train = read_jsonl(os.path.join(a.run1_dir, "train.jsonl"), None)
    cand_x = build_explain(run1_train[QUOTA["gen"]:])          # rows not used as generation examples
    print("cleaning candidates (decontamination, secrets, length)...", flush=True)
    ok_b = clean(cap(cand_b, 6000), "B"); ok_c = clean(cap(cand_c, 3000), "C"); ok_d = clean(cand_d, "D")
    ok_e = clean(cap(cand_e, 2000), "E"); ok_f1 = clean(cap(cand_docs, 2000), "F_docs"); ok_f2 = clean(cand_x, "F_explain")
    for k, v in (("test", [c for c in ok_b]), ("bugfix", [c for c in ok_c if c["task"] == "bugfix"]),
                 ("refactor", [c for c in ok_c if c["task"] == "refactor"]),
                 ("sec_vuln", [c for c in ok_d if c["task"] == "sec_vuln"]), ("sec_safe", [c for c in ok_d if c["task"] == "sec_safe"]),
                 ("docs", ok_f1), ("explain", ok_f2),
                 ("dockerfile", [c for c in ok_e if c["task"] == "dockerfile"]), ("workflow", [c for c in ok_e if c["task"] == "workflow"])):
        rng.shuffle(v); report["available_after_filters"][k] = len(v); pools[k] = v
    # every task gets its quota, and an edit-task shortfall is filled from the other edit task
    short = QUOTA["bugfix"] + QUOTA["refactor"] - min(len(pools["bugfix"]), QUOTA["bugfix"]) - min(len(pools["refactor"]), QUOTA["refactor"])
    sel = {k: pools[k][:QUOTA[k]] for k in ("test", "bugfix", "refactor", "sec_vuln", "sec_safe", "docs", "explain", "dockerfile", "workflow")}
    if short > 0:
        for k in ("bugfix", "refactor"):
            extra = pools[k][len(sel[k]):len(sel[k]) + short]; sel[k] += extra; short -= len(extra)
    train, val = [], []
    for c in pools["gen"]: train.append(c)
    for c in pools["gen_val"]: val.append(c)
    for k, vk in (("test", "test"), ("bugfix", "edit"), ("refactor", "edit"), ("sec_vuln", "sec"), ("sec_safe", "sec"),
                  ("docs", "docs"), ("explain", "explain"), ("dockerfile", "devops"), ("workflow", "devops")):
        items = sel[k]; nval = VAL[vk] // (2 if vk in ("edit", "sec", "devops") else 1)
        val += items[:nval]; train += items[nval:]
    for c in pools["gen"]:
        if "n_tokens" not in c: c["n_tokens"] = count_tokens(c["messages"])
    for c in pools["gen_val"]:
        if "n_tokens" not in c: c["n_tokens"] = count_tokens(c["messages"])
    rng.shuffle(train); rng.shuffle(val)
    def dump(path, items):
        with open(path, "w", encoding="utf-8") as f:
            for c in items: f.write(json.dumps({k: c[k] for k in ("source", "task", "row_id", "messages", "n_tokens")}, ensure_ascii=False) + "\n")
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    h_tr, h_va = dump(os.path.join(a.out, "train.jsonl"), train), dump(os.path.join(a.out, "val.jsonl"), val)
    ct = collections.Counter(c["task"] for c in train); cv = collections.Counter(c["task"] for c in val)
    ntok = [c["n_tokens"] for c in train]
    report.update({"train_examples": len(train), "val_examples": len(val), "train_by_task": dict(ct), "val_by_task": dict(cv),
                   "train_tokens_total": sum(ntok), "train_token_mean": round(sum(ntok) / len(ntok), 1), "train_token_max": max(ntok),
                   "sha256": {"train.jsonl": h_tr, "val.jsonl": h_va}, "eval_files_used": nfiles})
    json.dump(report, open(os.path.join(a.out, "report.json"), "w"), indent=2)
    print(json.dumps({k: report[k] for k in ("train_examples", "val_examples", "train_by_task", "val_by_task", "train_tokens_total", "train_token_mean", "removed", "available_after_filters", "sha256")}, indent=1))

if __name__ == "__main__":
    main()
