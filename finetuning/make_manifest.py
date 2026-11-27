"""Write finetuning/MANIFEST.json: sha256 of frozen artifacts + git commit + environment."""
import argparse, hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def git(*args):
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return None

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--files", nargs="+", required=True,
                   help="artifacts to fingerprint: adapter files, train/val jsonl, training config, run report")
    p.add_argument("--adapter-location", required=True, help="repo path or release URL of the adapter")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    p.add_argument("--out", default="finetuning/MANIFEST.json")
    a = p.parse_args()

    files = {}
    for f in a.files:
        path = Path(f)
        if not path.is_file():
            sys.exit(f"Missing file: {f}")
        files[f.replace("\\", "/")] = {"sha256": sha256(path), "bytes": path.stat().st_size}

    manifest = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_model": a.base_model,
        "adapter_location": a.adapter_location,
        "git_commit_before_freeze": git("rev-parse", "HEAD"),
        "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "working_tree_clean": git("status", "--porcelain") == "",
        "python": platform.python_version(),
        "files": files,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {a.out}")
    for name, info in files.items():
        print(f"{info['sha256']}  {name}")

if __name__ == "__main__":
    main()