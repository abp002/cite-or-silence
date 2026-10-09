"""How the verification judge does on the sentences the second review already labelled.

Takes every reviewed item that carried a quote (arms rag and verified), with the second reviewer's
label (data/review/claude-*.jsonl) as the expected outcome, and asks the verification judge, quote
against claim exactly as `verify` does:
- should drop: the reviewer found the sentence unbacked or contradicted;
- should keep: the reviewer and the bench judge both found it supported;
- contested: the reviewer kept it but the bench judge did not (reported, not scored).

Reads data/review/ and data/bench/ (gitignored: they carry SEP text) and prints only counts and
item numbers.

    uv run python scripts/verifier_cases.py [codex|ollama]
"""

import glob
import json
import sys
from pathlib import Path

from cite_or_silence import provider
from cite_or_silence.answer import Sentence
from cite_or_silence.verify import JUDGE_SCHEMA, judge_prompt

OUT = Path("data/review")
BATCH = 8

key = {it["item"]: it for it in map(json.loads, (OUT / "key.jsonl").read_text().splitlines())}
second = {}
for path in sorted(glob.glob(str(OUT / "claude-*.jsonl"))):
    for line in Path(path).read_text().splitlines():
        if line.strip():
            g = json.loads(line)
            second[g["item"]] = g["label"]

cases = []
for i, it in sorted(key.items()):
    if it["arm"] == "bare" or i not in second:
        continue
    r = json.loads(Path("data/bench", it["provider"], f"{it['qid']}.json").read_text())
    s = next((s for s in r["sentences"] if s["text"] == it["sentence"]), None)
    if s is None:
        continue
    if second[i] != "supported":
        group = "should drop"
    elif it["judge"] == "supported":
        group = "should keep"
    else:
        group = "contested"
    cases.append((i, group, Sentence(s["text"], s["source"], s["quote"])))

judge = provider.get(sys.argv[1] if len(sys.argv) > 1 else "codex")
kept = {}
for start in range(0, len(cases), BATCH):
    chunk = cases[start : start + BATCH]
    pairs = [(n, s) for n, (_, _, s) in enumerate(chunk, start=1)]
    verdicts = {v["n"]: v["supported"] for v in judge.complete(judge_prompt(pairs), JUDGE_SCHEMA)["verdicts"]}
    for n, (i, _, _) in enumerate(chunk, start=1):
        kept[i] = verdicts.get(n, False)

print(f"verification judge: {judge.name}")
for group in ("should drop", "should keep", "contested"):
    items = [i for i, g, _ in cases if g == group]
    dropped = [i for i in items if not kept[i]]
    print(f"  {group:<12} {len(items):>2} items, dropped {len(dropped):>2}  {dropped if group != 'should keep' else ''}")
    if group == "should keep" and dropped:
        print(f"    wrongly dropped: {dropped}")
