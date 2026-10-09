"""Draws a sample of the bench judge's sentence grades for an independent second review.

Stratified, seed 0: per provider, PER_LABEL['supported'] sentences the judge called supported and
PER_LABEL['other'] it called unbacked or contradicted (all of them if there are fewer). Agreement is
then reported per judge label, so the oversampling of the rarer labels does not skew it.

Writes, under data/review/ (gitignored: the batches carry SEP text):
- batch-N.md: question, reference and sentences to grade, WITHOUT the judge's labels (blind review);
- key.jsonl: the judge's label for every item, to compare against afterwards.

    uv run python scripts/review_sample.py
"""

import json
import random
from pathlib import Path

from cite_or_silence import bench, search
from cite_or_silence.answer import passages_of

PER_LABEL = {"supported": 35, "other": 15}
BATCHES = 8
PROVIDERS = ["codex_gpt-6-luna_low", "ollama_qwen3_14b"]
OUT = Path("data/review")

questions = {q["id"]: q for q in map(json.loads, Path("eval/questions.jsonl").read_text().splitlines())}
items = []
for provider in PROVIDERS:
    for path in sorted(Path("data/bench", provider).glob("*.json")):
        r = json.loads(path.read_text())
        if r["type"] not in ("single", "multi"):
            continue
        to_arm = {letter: arm for arm, letter in bench.letters(r["id"]).items()}
        for g in r["grades"]:
            arm, n = to_arm[g["sentence"][0]], int(g["sentence"][1:])
            items.append({"provider": provider, "qid": r["id"], "arm": arm, "n": n,
                          "sentence": r["texts"][arm][n - 1], "judge": g["label"]})  # fmt: skip

rng, sample = random.Random(0), []
for provider in PROVIDERS:
    for group, k in PER_LABEL.items():
        pool = [it for it in items if it["provider"] == provider and (it["judge"] == "supported") == (group == "supported")]
        sample += rng.sample(pool, min(k, len(pool)))
rng.shuffle(sample)
N = len(sample)
for i, it in enumerate(sample, 1):
    it["item"] = i

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "key.jsonl").write_text("".join(json.dumps(it, ensure_ascii=False) + "\n" for it in sample))

con = search.connect(Path("data/sep.duckdb"), read_only=True)
per_batch = -(-N // BATCHES)
for b in range(BATCHES):
    chunk = sorted(sample[b * per_batch : (b + 1) * per_batch], key=lambda it: (it["provider"], it["qid"]))
    parts, seen = [], None
    for it in chunk:
        key = (it["provider"], it["qid"])
        if key != seen:  # one reference per question, then its sentences
            seen = key
            q = questions[it["qid"]]
            r = json.loads(Path("data/bench", it["provider"], f"{it['qid']}.json").read_text())
            ref = bench.gold_text(con, q["gold"]) + passages_of(con, r["passages"])
            text = "\n\n".join(f"[{p.entry} — {p.heading}]\n{p.text}" for p in ref)
            parts.append(f"\n\n=====\nQUESTION: {q['question']}\n\nREFERENCE\n\n{text}\n\nSENTENCES TO GRADE")
        parts.append(f"\nITEM {it['item']}: {it['sentence']}")
    (OUT / f"batch-{b + 1}.md").write_text("".join(parts).strip() + "\n")
print(f"{len(items)} graded sentences, {N} sampled into {BATCHES} batches under {OUT}/")
