"""SE-Tasks benchmark built on the 164 HumanEval problems (all automatic, no human grading).

  A. Bug fixing      : a function with ONE injected bug (a mutant that the official tests detect); the model must return the fixed function.
  B. Test generation : the model writes plain `assert` tests for the correct function; we measure
                       validity (all asserts pass on the correct code), line coverage of the function, and mutation score
                       (valid tests that fail on the injected-bug versions).
  C. Docstrings      : the model adds a docstring to a function; we check the code is unchanged and the docstring is useful.
  D. DevOps          : 20 Dockerfile and 20 GitHub Actions specs, checked by parsing and by requirement matching.
Generated code is executed in a subprocess with a timeout. This is NOT a sandbox: run it only in a throwaway VM.
"""
import ast, copy, json, os, random, re, subprocess, sys, tempfile, hashlib

HEADER = "from typing import *\nimport math\n\n"
TEST_PROMPT = ("Write unit tests for this Python code. Use plain `assert` statements, one per line, "
               "covering normal cases and edge cases.\n\n```python\n{code}\n```")
BUG_PROMPT = "This Python function has a bug. Find it and return the complete corrected function.\n\n```python\n{code}\n```"
DOC_PROMPT = ("Add a clear docstring to this Python function (describe what it does, its parameters and its return value). "
              "Return the complete function.\n\n```python\n{code}\n```")

def extract_block(text):
    """First fenced code block, whatever its language tag and case (```Python, ```Dockerfile, ```YAML ...); the whole text if there is none."""
    m = re.search(r"```[ \t]*[\w+#.\-]*[ \t]*\r?\n(.*?)```", text or "", re.S)
    return (m.group(1) if m else (text or "")).strip("\n")

def run_program(code, timeout=10):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "prog.py"); open(p, "w", encoding="utf-8").write(code)
        try:
            r = subprocess.run([sys.executable, p], capture_output=True, text=True, timeout=timeout, cwd=d)
        except subprocess.TimeoutExpired:
            return "timeout", "timeout"
        return ("pass", "") if r.returncode == 0 else ("fail", (r.stderr.strip().splitlines() or [""])[-1][:200])

TRACER = r'''
import sys, json
src = open(sys.argv[1], encoding="utf-8").read(); executed = set()
def tr(frame, event, arg):
    if frame.f_code.co_filename == "<prog>":
        if event == "line": executed.add(frame.f_lineno)
        return tr
    return None
sys.settrace(tr); ok = True; err = ""
try: exec(compile(src, "<prog>", "exec"), {"__name__": "__main__"})
except BaseException as e: ok = False; err = repr(e)[:200]
sys.settrace(None)
print("@@" + json.dumps({"ok": ok, "err": err, "lines": sorted(executed)}))
'''
def run_traced(code, timeout=15):
    with tempfile.TemporaryDirectory() as d:
        p, t = os.path.join(d, "prog.py"), os.path.join(d, "tracer.py")
        open(p, "w", encoding="utf-8").write(code); open(t, "w").write(TRACER)
        try: r = subprocess.run([sys.executable, t, p], capture_output=True, text=True, timeout=timeout, cwd=d)
        except subprocess.TimeoutExpired: return False, "timeout", set()
        for line in reversed(r.stdout.splitlines()):
            if line.startswith("@@"):
                j = json.loads(line[2:]); return j["ok"], j["err"], set(j["lines"])
        return False, "no trace", set()

def full_code(ex): return HEADER + ex["prompt"] + ex["canonical_solution"]
def official_check(code, ex, timeout=10):
    return run_program(code + "\n\n" + ex["test"] + f"\ncheck({ex['entry_point']})\n", timeout)
def strip_header(code): return code.replace(HEADER.strip(), "", 1).strip() if code.startswith("from typing import *") else code

def entry_node(tree, name):
    return next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None)

# ---------------- mutation ----------------
CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}
BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add, ast.Mod: ast.FloorDiv, ast.FloorDiv: ast.Mod}
class Mutator(ast.NodeTransformer):
    def __init__(self, entry, target): self.entry, self.target, self.count, self.inside = entry, target, 0, False
    def _hit(self):
        self.count += 1; return self.count - 1 == self.target
    def visit_FunctionDef(self, node):
        if node.name != self.entry: return node
        self.inside = True
        body = node.body[1:] if (node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                                 and isinstance(node.body[0].value.value, str)) else node.body
        doc = node.body[:len(node.body) - len(body)]
        node.body = doc + [self.visit(s) for s in body]; self.inside = False; return node
    def visit_Compare(self, node):
        self.generic_visit(node)
        if self.inside:
            for i, op in enumerate(node.ops):
                if type(op) in CMP and self._hit(): node.ops[i] = CMP[type(op)]()
        return node
    def visit_BinOp(self, node):
        self.generic_visit(node)
        if self.inside and type(node.op) in BIN and self._hit(): node.op = BIN[type(node.op)]()
        return node
    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self.inside and self._hit(): node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node
    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if self.inside and isinstance(node.op, ast.Not) and self._hit(): return node.operand
        return node
    def visit_Constant(self, node):
        if self.inside:
            if isinstance(node.value, bool):
                if self._hit(): return ast.copy_location(ast.Constant(value=not node.value), node)
            elif isinstance(node.value, int):
                if self._hit(): return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node

def make_mutants(ex, n_mut=3, seed=42, max_try=14):
    code = full_code(ex); tree0 = ast.parse(code)
    cnt = Mutator(ex["entry_point"], -1); cnt.visit(copy.deepcopy(tree0)); n_sites = cnt.count
    order = list(range(n_sites)); random.Random(f"{seed}-{ex['task_id']}").shuffle(order)
    out = []
    for k in order[:max_try]:
        t = copy.deepcopy(tree0); Mutator(ex["entry_point"], k).visit(t); ast.fix_missing_locations(t)
        try: src = HEADER + ast.unparse(t)
        except Exception: continue
        if src.strip() == (HEADER + ast.unparse(tree0)).strip(): continue
        status, _ = official_check(src, ex, timeout=6)
        if status == "fail": out.append(src)          # a real bug w.r.t. the official tests (timeouts are excluded)
        if len(out) == n_mut: break
    return out

# ---------------- A. bug fixing ----------------
def bugfix_prompt(mutant_code): return BUG_PROMPT.format(code=strip_header(mutant_code))
def score_bugfix(ex, mutant_code, model_text, timeout=10):
    fixed = extract_block(model_text)
    status, err = run_program(mutant_code + "\n\n" + fixed + "\n\n" + ex["test"] + f"\ncheck({ex['entry_point']})\n", timeout)
    return {"passed": status == "pass", "status": status, "error": err}

# ---------------- B. test generation ----------------
def testgen_prompt(ex): return TEST_PROMPT.format(code=(ex["prompt"] + ex["canonical_solution"]).strip("\n"))
def toplevel_asserts(tree):
    """Number of assert statements that execute when the module runs: anything not nested in a def or a class."""
    def count(nodes):
        n = 0
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)): continue
            if isinstance(node, ast.Assert): n += 1
            n += count(ast.iter_child_nodes(node))
        return n
    return count(tree.body)

def score_tests(ex, mutants, model_text, timeout=10):
    tests = extract_block(model_text)
    res = {"valid": False, "n_assert": 0, "coverage": 0.0, "mutants_total": len(mutants), "mutants_killed": 0, "reason": ""}
    try: tree = ast.parse(tests)
    except SyntaxError: res["reason"] = "syntax"; return res
    res["n_assert"] = toplevel_asserts(tree)           # only asserts that really execute when the file runs (not inside def/class)
    if res["n_assert"] == 0: res["reason"] = "no assert"; return res
    sol = full_code(ex)
    ok, err, executed = run_traced(sol + "\n\n" + tests + "\n", timeout + 5)
    if not ok: res["reason"] = ("timeout" if err == "timeout" else "fails on the correct code"); return res
    res["valid"] = True
    fn = entry_node(ast.parse(sol), ex["entry_point"])
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr) and isinstance(getattr(fn.body[0], "value", None), ast.Constant)) else fn.body
    stmts = {n.lineno for b in body for n in ast.walk(b) if isinstance(n, ast.stmt)}
    res["coverage"] = len(stmts & executed) / len(stmts) if stmts else 1.0
    for m in mutants:
        status, _ = run_program(m + "\n\n" + tests + "\n", timeout)
        if status == "fail": res["mutants_killed"] += 1
    return res

LENIENT_HARNESS = """
import unittest as __u, os as __os
__suite = __u.TestSuite()
for __n, __c in list(globals().items()):
    if isinstance(__c, type) and issubclass(__c, __u.TestCase) and __c is not __u.TestCase:
        __suite.addTests(__u.defaultTestLoader.loadTestsFromTestCase(__c))
for __n, __f in list(globals().items()):
    if __n.startswith("test_") and callable(__f) and getattr(__f, "__module__", "__main__") == "__main__":
        __f()
if __suite.countTestCases():
    __res = __u.TextTestRunner(stream=open(__os.devnull, "w"), verbosity=0).run(__suite)
    if not __res.wasSuccessful(): raise SystemExit(1)
"""
def _clean_tests(tree):
    """Drop `if __name__ == "__main__":` blocks and bare unittest.main()/pytest.main() calls, then unparse."""
    keep = []
    for n in tree.body:
        if isinstance(n, ast.If) and "__name__" in ast.dump(n.test): continue
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "main": continue
        keep.append(n)
    tree.body = keep
    return ast.unparse(tree)

def lenient_asserts(tree):
    """Assertions that really execute under the lenient harness: module-level asserts, asserts/assert* calls inside
    test_* functions and inside test* methods of unittest.TestCase classes."""
    def asserts_in(node):
        return sum(isinstance(n, ast.Assert) or (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("assert"))
                   for n in ast.walk(node))
    n = toplevel_asserts(tree)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"): n += asserts_in(node)
        elif isinstance(node, ast.ClassDef) and any("TestCase" in ast.unparse(b) for b in node.bases):
            for f in node.body:
                if isinstance(f, ast.FunctionDef) and f.name.startswith("test"): n += asserts_in(f)
    return n

def score_tests_lenient(ex, mutants, model_text, timeout=10):
    """Secondary scorer: also accepts unittest-style and pytest-style tests (assert* calls count as assertions)."""
    res = {"valid": False, "n_assert": 0, "coverage": 0.0, "mutants_total": len(mutants), "mutants_killed": 0, "reason": ""}
    try: tree = ast.parse(extract_block(model_text))
    except SyntaxError: res["reason"] = "syntax"; return res
    res["n_assert"] = lenient_asserts(tree)
    if res["n_assert"] == 0: res["reason"] = "no assertion"; return res
    tests = _clean_tests(tree) + "\n" + LENIENT_HARNESS
    sol = full_code(ex)
    ok, err, executed = run_traced(sol + "\n\n" + tests + "\n", timeout + 5)
    if not ok: res["reason"] = ("timeout" if err == "timeout" else "fails on the correct code"); return res
    res["valid"] = True
    fn = entry_node(ast.parse(sol), ex["entry_point"])
    body = fn.body[1:] if (fn.body and isinstance(fn.body[0], ast.Expr) and isinstance(getattr(fn.body[0], "value", None), ast.Constant)) else fn.body
    stmts = {n.lineno for b in body for n in ast.walk(b) if isinstance(n, ast.stmt)}
    res["coverage"] = len(stmts & executed) / len(stmts) if stmts else 1.0
    for m in mutants:
        status, _ = run_program(m + "\n\n" + tests + "\n", timeout)
        if status == "fail": res["mutants_killed"] += 1
    return res

# ---------------- C. docstrings ----------------
def doc_item(ex):
    tree = ast.parse(full_code(ex)); fn = entry_node(tree, ex["entry_point"])
    params = [a.arg for a in fn.args.args if a.arg != "self"]
    if fn.body and isinstance(fn.body[0], ast.Expr) and isinstance(getattr(fn.body[0], "value", None), ast.Constant): fn.body = fn.body[1:] or [ast.Pass()]
    ref = ast.dump(fn); code = ast.unparse(tree)
    return {"code": strip_header(HEADER + code), "ref_dump": ref, "params": params}
def doc_prompt(item): return DOC_PROMPT.format(code=item["code"])
def score_doc(ex, item, model_text):
    res = {"parses": False, "same_code": False, "has_doc": False, "mentions_params": False, "ok": False}
    try: tree = ast.parse(extract_block(model_text))
    except SyntaxError: return res
    res["parses"] = True; fn = entry_node(tree, ex["entry_point"])
    if not fn: return res
    doc = ast.get_docstring(fn) or ""
    res["has_doc"] = len(doc) >= 30
    res["mentions_params"] = all(p in doc for p in item["params"])
    f2 = copy.deepcopy(fn)
    if f2.body and isinstance(f2.body[0], ast.Expr) and isinstance(getattr(f2.body[0], "value", None), ast.Constant): f2.body = f2.body[1:] or [ast.Pass()]
    res["same_code"] = ast.dump(f2) == item["ref_dump"]
    res["ok"] = res["same_code"] and res["has_doc"]          # parameter mentions are reported separately (the original HumanEval docstrings often omit them)
    return res

# ---------------- D. DevOps specs ----------------
DOCKER_SPECS = [
 dict(base="python:3.11-slim", workdir="/app", copy=[("requirements.txt", ".")], run=["pip install -r requirements.txt"], expose=8000, cmd=["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]),
 dict(base="python:3.12-alpine", workdir="/srv", env=[("FLASK_ENV", "production")], copy=[("app.py", "/srv/app.py")], run=["pip install flask gunicorn"], expose=5000, cmd=["gunicorn", "-b", "0.0.0.0:5000", "app:app"]),
 dict(base="node:20-alpine", workdir="/usr/src/app", copy=[("package.json", ".")], run=["npm install --production"], expose=3000, user="node", cmd=["node", "server.js"]),
 dict(base="golang:1.22", workdir="/go/src/app", copy=[(".", ".")], run=["go build -o server ."], expose=8080, cmd=["./server"]),
 dict(base="nginx:1.25-alpine", copy=[("index.html", "/usr/share/nginx/html/index.html")], expose=80, cmd=["nginx", "-g", "daemon off;"]),
 dict(base="openjdk:17-jdk-slim", workdir="/opt/app", copy=[("target/app.jar", "app.jar")], expose=8080, entrypoint=["java", "-jar", "app.jar"]),
 dict(base="ruby:3.2", workdir="/myapp", copy=[("Gemfile", "Gemfile")], run=["bundle install"], expose=4567, cmd=["ruby", "app.rb"]),
 dict(base="php:8.2-apache", copy=[("src/", "/var/www/html/")], run=["docker-php-ext-install mysqli"], expose=80),
 dict(base="python:3.10", workdir="/code", env=[("PYTHONUNBUFFERED", "1")], copy=[("requirements.txt", "requirements.txt")], run=["pip install --no-cache-dir -r requirements.txt"], cmd=["python", "worker.py"]),
 dict(base="rust:1.75", workdir="/usr/src/myapp", copy=[(".", ".")], run=["cargo build --release"], cmd=["./target/release/myapp"]),
 dict(base="mcr.microsoft.com/dotnet/aspnet:8.0", workdir="/app", copy=[("publish/", ".")], expose=8080, entrypoint=["dotnet", "Api.dll"]),
 dict(base="alpine:3.19", run=["apk add --no-cache curl"], user="nobody", cmd=["curl", "--version"]),
 dict(base="python:3.11-slim", workdir="/app", env=[("APP_ENV", "prod"), ("PORT", "9000")], copy=[("requirements.txt", "."), ("src/", "src/")], run=["pip install -r requirements.txt"], expose=9000, user="appuser", cmd=["python", "src/main.py"]),
 dict(base="redis:7-alpine", copy=[("redis.conf", "/usr/local/etc/redis/redis.conf")], expose=6379, cmd=["redis-server", "/usr/local/etc/redis/redis.conf"]),
 dict(base="postgres:16", env=[("POSTGRES_DB", "appdb")], copy=[("init.sql", "/docker-entrypoint-initdb.d/init.sql")], expose=5432),
 dict(base="node:18", workdir="/app", copy=[("package.json", "package.json"), ("package-lock.json", "package-lock.json")], run=["npm ci"], expose=4000, cmd=["npm", "start"]),
 dict(base="python:3.9-slim", workdir="/opt/jobs", copy=[("jobs/", "/opt/jobs/")], run=["pip install celery redis"], cmd=["celery", "-A", "jobs", "worker"]),
 dict(base="ubuntu:22.04", env=[("DEBIAN_FRONTEND", "noninteractive")], run=["apt-get update && apt-get install -y git"], cmd=["git", "--version"]),
 dict(base="golang:1.21-alpine", workdir="/app", env=[("CGO_ENABLED", "0")], copy=[("go.mod", "."), ("main.go", ".")], run=["go build -o /bin/app"], entrypoint=["/bin/app"]),
 dict(base="python:3.12-slim", workdir="/app", copy=[("app/", "app/")], run=["pip install fastapi uvicorn"], expose=8001, user="nobody", cmd=["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]),
]
def docker_prompt(s):
    b = [f"- Base image: {s['base']}"]
    if s.get("workdir"): b.append(f"- Working directory: {s['workdir']}")
    if s.get("env"): b.append("- Environment variables: " + ", ".join(f"{k}={v}" for k, v in s["env"]))
    for a, c in s.get("copy", []): b.append(f"- Copy {a} to {c}")
    for r in s.get("run", []): b.append(f"- Run: {r}")
    if s.get("expose"): b.append(f"- Exposed port: {s['expose']}")
    if s.get("user"): b.append(f"- Runs as user: {s['user']}")
    if s.get("cmd"): b.append("- Container start: CMD " + json.dumps(s["cmd"]))
    if s.get("entrypoint"): b.append("- Container start: ENTRYPOINT " + json.dumps(s["entrypoint"]))
    return "Write a Dockerfile that meets these requirements:\n" + "\n".join(b)
def docker_oracle(s):
    L = [f"FROM {s['base']}"]
    if s.get("workdir"): L.append(f"WORKDIR {s['workdir']}")
    for k, v in s.get("env", []): L.append(f"ENV {k}={v}")
    for a, c in s.get("copy", []): L.append(f"COPY {a} {c}")
    for r in s.get("run", []): L.append(f"RUN {r}")
    if s.get("expose"): L.append(f"EXPOSE {s['expose']}")
    if s.get("user"): L.append(f"USER {s['user']}")
    if s.get("cmd"): L.append("CMD " + json.dumps(s["cmd"]))
    if s.get("entrypoint"): L.append("ENTRYPOINT " + json.dumps(s["entrypoint"]))
    return "\n".join(L)
DOCKER_KW = {"FROM", "RUN", "CMD", "LABEL", "EXPOSE", "ENV", "ADD", "COPY", "ENTRYPOINT", "VOLUME", "USER", "WORKDIR", "ARG", "ONBUILD", "STOPSIGNAL", "HEALTHCHECK", "SHELL", "MAINTAINER"}
def score_docker(s, model_text):
    text = extract_block(model_text); lines = []
    for raw in text.replace("\\\n", " ").splitlines():
        if raw.strip() and not raw.strip().startswith("#"): lines.append(raw.strip())
    valid = bool(lines) and all(l.split()[0].upper() in DOCKER_KW for l in lines) and lines[0].split()[0].upper() in ("FROM", "ARG") \
            and any(l.split()[0].upper() == "FROM" for l in lines)
    norm = lambda t: re.sub(r"\s+", " ", t.replace('"', "").replace("'", "").replace("[", "").replace("]", "").replace(",", " ")).strip().lower()
    body = norm("\n".join(lines)); reqs = []
    reqs.append(("FROM " + s["base"]).lower() in body)
    if s.get("workdir"): reqs.append("workdir " + s["workdir"].lower() in body)
    for k, v in s.get("env", []): reqs.append(k.lower() in body and v.lower() in body)
    for a, c in s.get("copy", []): reqs.append(bool(re.search(r"\b(copy|add) .*" + re.escape(a.lower()), body)))
    for r in s.get("run", []): reqs.append(norm(r) in body)
    if s.get("expose"): reqs.append(f"expose {s['expose']}" in body)
    if s.get("user"): reqs.append("user " + s["user"].lower() in body)
    if s.get("cmd"): reqs.append("cmd " + norm(" ".join(s["cmd"])) in body or norm(" ".join(s["cmd"])) in body)
    if s.get("entrypoint"): reqs.append("entrypoint " + norm(" ".join(s["entrypoint"])) in body or norm(" ".join(s["entrypoint"])) in body)
    return {"valid": valid, "frac_met": sum(reqs) / len(reqs), "all_met": valid and all(reqs)}

def _wf(name, on, jobs): return dict(name=name, on=on, jobs=jobs)
WF_SPECS = [
 _wf("CI", ["push", "pull_request"], {"test": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "actions/setup-python"), ("run", "pip install -r requirements.txt"), ("run", "pytest")])}),
 _wf("Node CI", ["push"], {"build": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "actions/setup-node"), ("run", "npm ci"), ("run", "npm test")])}),
 _wf("Lint", ["pull_request"], {"lint": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "pip install flake8"), ("run", "flake8 .")])}),
 _wf("Go build", ["push", "workflow_dispatch"], {"build": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "actions/setup-go"), ("run", "go build ./..."), ("run", "go test ./...")])}),
 _wf("Docker image", ["push"], {"docker": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "docker/setup-buildx-action"), ("uses", "docker/build-push-action")])}),
 _wf("Java CI", ["push", "pull_request"], {"build": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "actions/setup-java"), ("run", "mvn -B package")])}),
 _wf("Nightly", ["schedule"], {"nightly": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "make test")])}),
 _wf("Release", ["release"], {"publish": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "python -m build"), ("run", "twine upload dist/*")])}),
 _wf("Test and deploy", ["push"], {"test": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "make test")]),
                                    "deploy": dict(runs_on="ubuntu-latest", needs="test", steps=[("uses", "actions/checkout"), ("run", "make deploy")])}),
 _wf("Docs", ["push"], {"docs": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "actions/setup-python"), ("run", "pip install mkdocs"), ("run", "mkdocs build")])}),
 _wf("Security scan", ["pull_request", "schedule"], {"scan": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "pip install bandit"), ("run", "bandit -r src")])}),
 _wf("Terraform check", ["pull_request"], {"validate": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "hashicorp/setup-terraform"), ("run", "terraform init"), ("run", "terraform validate")])}),
 _wf("Rust CI", ["push"], {"cargo": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "cargo build --release"), ("run", "cargo test")])}),
 _wf("Mac build", ["push"], {"build": dict(runs_on="macos-latest", steps=[("uses", "actions/checkout"), ("run", "make build")])}),
 _wf("Frontend", ["push", "pull_request"], {"build": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "actions/setup-node"), ("run", "npm ci"), ("run", "npm run build")])}),
 _wf("Format check", ["pull_request"], {"format": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "actions/setup-python"), ("run", "pip install black"), ("run", "black --check .")])}),
 _wf("Build and test", ["push"], {"build": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "make build")]),
                                  "test": dict(runs_on="ubuntu-latest", needs="build", steps=[("uses", "actions/checkout"), ("run", "make test")])}),
 _wf("Static site", ["push"], {"pages": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "npm run build"), ("uses", "actions/upload-pages-artifact")])}),
 _wf("Ansible lint", ["pull_request"], {"lint": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("run", "pip install ansible-lint"), ("run", "ansible-lint")])}),
 _wf("Helm lint", ["push"], {"helm": dict(runs_on="ubuntu-latest", steps=[("uses", "actions/checkout"), ("uses", "azure/setup-helm"), ("run", "helm lint charts/app")])}),
]
def workflow_prompt(s):
    b = [f"- Name: {s['name']}", "- Triggers: " + ", ".join(s["on"])]
    for jn, j in s["jobs"].items():
        st = "; ".join(("uses " + v) if k == "uses" else (f"runs `{v}`") for k, v in j["steps"])
        b.append(f"- Job `{jn}` on {j['runs_on']}" + (f" (needs `{j['needs']}`)" if j.get("needs") else "") + ": " + st)
    return "Write a GitHub Actions workflow file (YAML) that meets these requirements:\n" + "\n".join(b)
def workflow_oracle(s):
    import yaml
    jobs = {}
    for jn, j in s["jobs"].items():
        steps = [({"uses": v + "@v4"} if k == "uses" else {"run": v}) for k, v in j["steps"]]
        d = {"runs-on": j["runs_on"], "steps": steps}
        if j.get("needs"): d["needs"] = j["needs"]
        jobs[jn] = d
    return yaml.safe_dump({"name": s["name"], "on": {e: None for e in s["on"]}, "jobs": jobs}, sort_keys=False)
def score_workflow(s, model_text):
    import yaml
    res = {"valid": False, "frac_met": 0.0, "all_met": False}
    try: d = yaml.safe_load(extract_block(model_text))
    except Exception: return res
    if not isinstance(d, dict) or not isinstance(d.get("jobs"), dict): return res
    trig = d.get("on", d.get(True))
    if trig is None: return res
    res["valid"] = True
    events = set([trig] if isinstance(trig, str) else trig.keys() if isinstance(trig, dict) else trig)
    reqs = [str(d.get("name", "")).strip().lower() == s["name"].lower()]
    reqs += [e in events for e in s["on"]]
    for jn, j in s["jobs"].items():
        jd = d["jobs"].get(jn)
        reqs.append(isinstance(jd, dict))
        if not isinstance(jd, dict): reqs += [False] * (1 + len(j["steps"])); continue
        reqs.append(str(jd.get("runs-on", "")).lower() == j["runs_on"].lower())
        if j.get("needs"): reqs.append(jd.get("needs") == j["needs"] or j["needs"] in (jd.get("needs") or []))
        steps = jd.get("steps") if isinstance(jd.get("steps"), list) else []
        for k, v in j["steps"]:
            if k == "uses": reqs.append(any(str(st.get("uses", "")).split("@")[0] == v for st in steps if isinstance(st, dict)))
            else: reqs.append(any(re.sub(r"\s+", " ", str(st.get("run", ""))).strip() == v or v in str(st.get("run", "")) for st in steps if isinstance(st, dict)))
    res["frac_met"] = sum(reqs) / len(reqs); res["all_met"] = all(reqs)
    return res

# ---------------- statistics ----------------
def paired_bootstrap(a, b, n=10000, seed=42):
    """a, b: per-item scores (same items) for model A and model B. Returns (mean(b)-mean(a), lo, hi) in points."""
    assert len(a) == len(b) and a
    rng = random.Random(seed); idx = range(len(a)); diffs = []
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        diffs.append(100 * (sum(b[i] for i in s) - sum(a[i] for i in s)) / len(a))
    diffs.sort()
    return 100 * (sum(b) - sum(a)) / len(a), diffs[int(0.025 * n)], diffs[int(0.975 * n) - 1]
