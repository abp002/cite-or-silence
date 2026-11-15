"""Second round for issue #3: does searching with a made-up answer find the right section?

The translation round (recall_translated.py) showed the language is not the limit. Here the
search vector comes from a short passage the model writes as if it were the encyclopedia's
answer (HyDE), and chunks are also grouped by section before ranking.

    uv run python scripts/recall_hyde.py [--provider codex] [-k 5] [--only old|new]

The prompt that writes the made-up answer is `query.sketch_prompt`.
"""

import argparse
from pathlib import Path

from cite_or_silence import embed, evaluate, provider, questions, search
from cite_or_silence import query

DATA = Path("data")


def by_section(scored: list[tuple[str, float]], k: int) -> list[str]:
    """Rank sections by the sum of their chunks' similarity in the pool, then give each section's
    best chunk, best section first."""
    total: dict[str, float] = {}
    best: dict[str, str] = {}
    for chunk_id, score in scored:
        section = chunk_id.rsplit(":", 1)[0]
        total[section] = total.get(section, 0.0) + score
        best.setdefault(section, chunk_id)
    return [best[s] for s in sorted(total, key=lambda s: -total[s])][:k]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="codex")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--only", choices=("old", "new"))
    args = ap.parse_args()
    asked = questions.load(Path("eval/questions.jsonl"))
    if args.only:
        asked = asked[:101] if args.only == "old" else asked[101:]
    asked = [q for q in asked if q["gold"]]
    llm = provider.get(args.provider)
    tag = llm.name.replace(":", "_")
    texts = [q["question"] for q in asked]
    english = query.rewrite(texts, llm, DATA / "queries" / f"{tag}-english.json", query.translation_prompt)
    made_up = query.rewrite(texts, llm, DATA / "queries" / f"{tag}-sketch.json")

    con = search.connect(DATA / "sep.duckdb", read_only=True)
    sections = {r[0]: evaluate.Section(*r[1:]) for r in con.execute("SELECT id, entry, anchor, section FROM chunks").fetchall()}
    number = {(s.entry, s.anchor): s.number for s in sections.values()}
    model = embed.load_model()
    es, en, hy = (embed.encode(model, t) for t in (texts, english, made_up))
    k = args.k
    scores: dict[str, list] = {}
    entries: dict[str, list] = {}
    for q, ves, ven, vhy in zip(asked, es, en, hy):
        d_es, d_en, d_hy = (search.dense(con, v) for v in (ves, ven, vhy))
        variants = {
            "es diverse (now)": search.cap_per_entry(d_es, k),
            "es+en diverse": search.cap_per_entry(search.rrf([d_es, d_en]), k),
            "hyde dense": d_hy[:k],
            "hyde diverse": search.cap_per_entry(d_hy, k),
            "es+hyde diverse": search.cap_per_entry(search.rrf([d_es, d_hy]), k),
            "es+en+hyde diverse": search.cap_per_entry(search.rrf([d_es, d_en, d_hy]), k),
            "es by section": by_section(search.dense_scored(con, ves, 200), k),
            "hyde by section": by_section(search.dense_scored(con, vhy, 200), k),
        }
        gold = [evaluate.Section(g["entry"], g["anchor"], number[g["entry"], g["anchor"]]) for g in q["gold"]]
        for label, ids in variants.items():
            got = [sections[i] for i in ids]
            scores.setdefault(label, []).append((q["type"], evaluate.recall(gold, got)))
            entries.setdefault(label, []).append((q["type"], evaluate.entry_recall(gold, got)))
    types = ("single", "multi", "false_premise", "all")
    first = evaluate.by_type(next(iter(scores.values())))
    print(f"Recall@{k} by section (by entry in brackets), rewritten by {llm.name}\n")
    print(f"{'':<24}" + "".join(f"{t + ' n=' + str(first[t][0]):>22}" for t in types if t in first))
    for label in scores:
        s, e = evaluate.by_type(scores[label]), evaluate.by_type(entries[label])
        print(f"{label:<24}" + "".join(f"{s[t][1]:>15.2f} [{e[t][1]:.2f}]" for t in types if t in s))


if __name__ == "__main__":
    main()
