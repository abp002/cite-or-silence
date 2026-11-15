"""Does searching in English find the right section more often? (issue #3)

Compares, on the same questions, the production search (Spanish question, `diverse`) with the
same searches run on an English translation of the question, and with mixes of both.
Needs the index and a translation cache (`data/queries/<provider>-english.json`, written on the
first run through the provider).

    uv run python scripts/recall_translated.py [--provider codex] [-k 5]
"""

import argparse
from pathlib import Path

from cite_or_silence import embed, evaluate, provider, questions, search
from cite_or_silence import query

DATA = Path("data")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="codex")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--only", choices=("old", "new"), help="old: the first 101 questions; new: the ones added later")
    args = ap.parse_args()

    asked = questions.load(Path("eval/questions.jsonl"))
    if args.only:
        asked = asked[:101] if args.only == "old" else asked[101:]
    asked = [q for q in asked if q["gold"]]
    llm = provider.get(args.provider)
    english = query.rewrite([q["question"] for q in asked], llm, DATA / "queries" / f"{llm.name.replace(':', '_')}-english.json", query.translation_prompt)

    con = search.connect(DATA / "sep.duckdb", read_only=True)
    sections = {r[0]: evaluate.Section(*r[1:]) for r in con.execute("SELECT id, entry, anchor, section FROM chunks").fetchall()}
    number = {(s.entry, s.anchor): s.number for s in sections.values()}
    model = embed.load_model()
    es = embed.encode(model, [q["question"] for q in asked])
    en = embed.encode(model, english)
    scorer = embed.load_reranker()
    k = args.k

    def variants(q, qe, ves, ven):
        d_es, d_en = search.dense(con, ves), search.dense(con, ven)
        b_en = search.bm25(con, qe)
        both = search.rrf([d_es, d_en])
        r_en = search.rerank(con, qe, d_en, scorer)
        r_both = search.rerank(con, qe, both[: search.POOL], scorer)
        return {
            "es dense": d_es[:k],
            "es diverse (now)": search.cap_per_entry(d_es, k),
            "en dense": d_en[:k],
            "en diverse": search.cap_per_entry(d_en, k),
            "en hybrid": search.rrf([d_en, b_en])[:k],
            "en hybrid diverse": search.cap_per_entry(search.rrf([d_en, b_en]), k),
            "en rerank": r_en[:k],
            "en rerank diverse": search.cap_per_entry(r_en, k),
            "es+en diverse": search.cap_per_entry(both, k),
            "es+en rerank": r_both[:k],
            "es+en rerank diverse": search.cap_per_entry(r_both, k),
            "es+en+bm25 diverse": search.cap_per_entry(search.rrf([d_es, d_en, b_en]), k),
        }

    scores: dict[str, list] = {}
    entries: dict[str, list] = {}
    for q, qe, ves, ven in zip(asked, english, es, en):
        gold = [evaluate.Section(g["entry"], g["anchor"], number[g["entry"], g["anchor"]]) for g in q["gold"]]
        for label, ids in variants(q, qe, ves, ven).items():
            got = [sections[i] for i in ids]
            scores.setdefault(label, []).append((q["type"], evaluate.recall(gold, got)))
            entries.setdefault(label, []).append((q["type"], evaluate.entry_recall(gold, got)))

    types = ("single", "multi", "false_premise", "all")
    print(f"Recall@{k} by section (by entry in brackets), translations by {llm.name}\n")
    first = evaluate.by_type(next(iter(scores.values())))
    print(f"{'':<24}" + "".join(f"{t + ' n=' + str(first[t][0]):>22}" for t in types if t in first))
    for label in scores:
        s, e = evaluate.by_type(scores[label]), evaluate.by_type(entries[label])
        print(f"{label:<24}" + "".join(f"{s[t][1]:>15.2f} [{e[t][1]:.2f}]" for t in types if t in s))


if __name__ == "__main__":
    main()
