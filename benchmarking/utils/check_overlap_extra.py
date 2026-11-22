"""Check that an evaluation prompt set does not overlap the training data (10-token windows by default).
  python check_overlap_extra.py --train ft_data/train.jsonl --val ft_data/val.jsonl --prompts prompts_securite_extra.json [--n 10]
Prints, per prompt, the number of training examples sharing a window; a prompt with hits is reported, not silently dropped."""
import argparse, json, re
ap = argparse.ArgumentParser()
ap.add_argument("--train", required=True); ap.add_argument("--val"); ap.add_argument("--prompts", required=True)
ap.add_argument("--n", type=int, default=10)
a = ap.parse_args()
TOK = re.compile(r"[A-Za-z_]\w*|\d+|\S")
toks = lambda t: TOK.findall(t.lower())
prompts = json.load(open(a.prompts, encoding="utf-8"))["prompts"]
idx = {}
for p in prompts:
    t = toks(p["prompt"].split("\n\n", 1)[-1])          # the code part (after the question line)
    for i in range(len(t) - a.n + 1): idx.setdefault(tuple(t[i:i + a.n]), set()).add(p["id"])
hits = {p["id"]: 0 for p in prompts}
for path in [x for x in (a.train, a.val) if x]:
    for line in open(path, encoding="utf-8"):
        ex = json.loads(line); t = toks("\n".join(m["content"] for m in ex["messages"]))
        found = set()
        for i in range(len(t) - a.n + 1):
            found |= idx.get(tuple(t[i:i + a.n]), set())
        for pid in found: hits[pid] += 1
flag = {k: v for k, v in hits.items() if v}
print(f"window size {a.n} tokens | prompts checked: {len(prompts)} | prompts with at least one training example sharing a window: {len(flag)}")
for k, v in sorted(flag.items(), key=lambda kv: int(kv[0][1:])): print(f"  {k}: {v} training example(s)")
if not flag: print("no overlap found")
