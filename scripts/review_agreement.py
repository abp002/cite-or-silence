"""Agreement between the bench judge and a second reviewer, per judge label.

The sample is stratified by judge label (see review_sample.py), so agreement is reported per label
rather than pooled: "when the judge says supported, the reviewer agrees X of Y".

    uv run python scripts/review_agreement.py claude    # data/review/claude-*.jsonl
    uv run python scripts/review_agreement.py humano    # data/review/humano.jsonl
"""

import json
import sys
from collections import Counter
from pathlib import Path

OUT = Path("data/review")
who = sys.argv[1] if len(sys.argv) > 1 else "claude"
key = {it["item"]: it for it in map(json.loads, (OUT / "key.jsonl").read_text().splitlines())}
second = {}
for path in sorted(OUT.glob(f"{who}*.jsonl")):
    for line in path.read_text().splitlines():
        if line.strip():
            g = json.loads(line)
            second[g["item"]] = g

missing = sorted(set(key) - set(second)) if who == "claude" else []
both = [(key[i], second[i]) for i in sorted(second) if i in key]
print(f"{who}: {len(both)} items" + (f", missing {missing}" if missing else ""))

for provider in sorted({k["provider"] for k, _ in both}) + ["all"]:
    rows = [(k, s) for k, s in both if provider in ("all", k["provider"])]
    print(f"\n{provider}")
    for label in ("supported", "unbacked", "contradicted"):
        sub = [(k, s) for k, s in rows if k["judge"] == label]
        if sub:
            agree = sum(k["judge"] == s["label"] for k, s in sub)
            other = Counter(s["label"] for k, s in sub if s["label"] != label)
            print(f"  judge {label:<13} reviewer agrees {agree:>2}/{len(sub):<2}  otherwise: {dict(other)}")

print("\ndisagreements:")
for k, s in both:
    if k["judge"] != s["label"]:
        print(f"  item {k['item']:>3} {k['provider'][:6]} {k['qid']:<4} {k['arm']:<8} judge={k['judge']:<11} {who}={s['label']:<11} {s.get('why', '')}")
