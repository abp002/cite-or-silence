import argparse
import json
import statistics
from pathlib import Path

from cite_or_silence.chunk import chunk_entry
from cite_or_silence import answer, embed, evaluate, provider, search
from cite_or_silence.fetch import fetch_all
from cite_or_silence import questions

DATA = Path("data")
RAW = DATA / "raw"
CHUNKS = DATA / "chunks.jsonl"
QUESTIONS = Path("eval/questions.jsonl")
EMBEDDINGS = DATA / "embeddings"
DB = DATA / "sep.duckdb"


def cmd_fetch(args) -> None:
    fetch_all(RAW, limit=args.limit, log=lambda m: print(m, flush=True))


def cmd_chunk(args) -> None:
    files = sorted(RAW.glob("*.html"))
    sizes, empty, per_entry = [], [], []
    with CHUNKS.open("w", encoding="utf-8") as out:
        for path in files:
            chunks = chunk_entry(path.stem, path.read_text(encoding="utf-8"))
            if not chunks:
                empty.append(path.stem)
            per_entry.append(len(chunks))
            for chunk in chunks:
                sizes.append(len(chunk.text.split()))
                out.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")
    print(f"{len(files)} entries -> {len(sizes)} chunks in {CHUNKS}")
    if sizes:
        q = statistics.quantiles(sizes, n=20)
        print(f"words per chunk: median {statistics.median(sizes):.0f}, p5 {q[0]:.0f}, p95 {q[-1]:.0f}, max {max(sizes)}")
        print(f"chunks per entry: median {statistics.median(per_entry):.0f}, max {max(per_entry)}")
    if empty:
        print(f"{len(empty)} entries without chunks: {', '.join(empty[:20])}")


def cmd_embed(args) -> None:
    embed.embed_all(CHUNKS, EMBEDDINGS, log=lambda m: print(m, flush=True))


def cmd_index(args) -> None:
    chunks = search.chunks_of(CHUNKS)
    con = search.connect(DB)
    search.build_index(con, chunks, embed.load_all(EMBEDDINGS))
    print(f"{len(chunks)} chunks indexed in {DB}")


def cmd_search(args) -> None:
    con = search.connect(DB)
    vector = embed.encode(embed.load_model(), [args.query])[0]
    scorer = embed.load_reranker() if args.mode == "rerank" else None
    for chunk_id in search.search(con, args.query, vector, args.mode, args.k, scorer):
        heading, text = con.execute("SELECT heading, text FROM chunks WHERE id = ?", [chunk_id]).fetchone()
        print(f"{chunk_id}  [{heading}]\n    {text[:200]}...\n")


def cmd_ask(args) -> None:
    con = search.connect(DB)
    vector = embed.encode(embed.load_model(), [args.question])[0]
    passages = answer.passages_of(con, search.search(con, args.question, vector, "diverse", args.k))
    llm = provider.get(args.provider)
    result = answer.answer(args.question, passages, llm, llm)
    print(f"({llm.name})\n\n{result.render()}")
    dropped = [s for s in result.sentences if s.dropped]
    if dropped:
        print(f"\ndropped ({len(dropped)}):")
        for s in dropped:
            print(f"- {s.text} [{s.source}] -- {s.dropped}\n    quote: {s.quote}")


def cmd_recall(args) -> None:
    con = search.connect(DB)
    sections = {
        row[0]: evaluate.Section(*row[1:])
        for row in con.execute("SELECT id, entry, anchor, section FROM chunks").fetchall()
    }
    number = {(s.entry, s.anchor): s.number for s in sections.values()}
    asked = [q for q in questions.load(QUESTIONS) if q["gold"]]
    vectors = embed.encode(embed.load_model(), [q["question"] for q in asked])
    scorer = embed.load_reranker()
    scores = {mode: [] for mode in search.MODES}
    entry_scores = {mode: [] for mode in search.MODES}
    misses = []
    for q, vector in zip(asked, vectors):
        gold = [evaluate.Section(g["entry"], g["anchor"], number[g["entry"], g["anchor"]]) for g in q["gold"]]
        for mode in search.MODES:
            got = [sections[i] for i in search.search(con, q["question"], vector, mode, args.k, scorer)]
            scores[mode].append((q["type"], evaluate.recall(gold, got)))
            entry_scores[mode].append((q["type"], evaluate.entry_recall(gold, got)))
            if mode == args.misses and scores[mode][-1][1] < 1:
                misses.append((q, got))
    tables = {m: evaluate.by_type(scores[m]) for m in search.MODES}
    entry_tables = {m: evaluate.by_type(entry_scores[m]) for m in search.MODES}
    print(f"Recall@{args.k} by section (by entry in brackets); 'none' questions have no gold\n")
    print(f"{'type':<14}{'n':>4}" + "".join(f"{m:>18}" for m in search.MODES))
    for t in ("single", "multi", "false_premise", "all"):
        n = tables["dense"][t][0]
        cells = "".join(f"{tables[m][t][1]:>9.2f} [{entry_tables[m][t][1]:.2f}]" for m in search.MODES)
        print(f"{t:<14}{n:>4}{cells}")
    if args.misses:
        print(f"\n{args.misses} misses ({len(misses)}):")
        for q, got in misses:
            want = ", ".join(f"{g['entry']}#{g['anchor']}" for g in q["gold"])
            print(f"- {q['id']} {q['question']}\n    want {want}\n    got  {', '.join(f'{s.entry}#{s.anchor}' for s in got)}")


def cmd_questions(args) -> None:
    if args.entry:
        print("\n".join(questions.headings(args.entry, RAW)))
        return
    problems = questions.check(questions.load(QUESTIONS), RAW)
    print("\n".join(problems) or "question set ready")
    print(f"{len(problems)} problems")


def main() -> None:
    parser = argparse.ArgumentParser(prog="cite-or-silence")
    sub = parser.add_subparsers(required=True)
    fetch = sub.add_parser("fetch", help="download SEP entries into data/raw (5 s between requests)")
    fetch.add_argument("--limit", type=int, help="download at most N new entries")
    fetch.set_defaults(func=cmd_fetch)
    chunk = sub.add_parser("chunk", help="cut data/raw into data/chunks.jsonl")
    chunk.set_defaults(func=cmd_chunk)
    emb = sub.add_parser("embed", help="embed data/chunks.jsonl into data/embeddings (resumable, hours)")
    emb.set_defaults(func=cmd_embed)
    idx = sub.add_parser("index", help="load chunks and embeddings into data/sep.duckdb (HNSW + BM25)")
    idx.set_defaults(func=cmd_index)
    se = sub.add_parser("search", help="show the top chunks for a question")
    se.add_argument("query")
    se.add_argument("--mode", choices=search.MODES, default="hybrid")
    se.add_argument("-k", type=int, default=5)
    se.set_defaults(func=cmd_search)
    ak = sub.add_parser("ask", help="answer a question with cited, verified sentences")
    ak.add_argument("question")
    ak.add_argument("--provider", choices=("codex", "ollama"), default="codex")
    ak.add_argument("-k", type=int, default=10)
    ak.set_defaults(func=cmd_ask)
    rc = sub.add_parser("recall", help="Recall@k of every search mode against eval/questions.jsonl")
    rc.add_argument("-k", type=int, default=5)
    rc.add_argument("--misses", nargs="?", const="rerank", choices=search.MODES, help="list the questions this mode misses (default: rerank)")
    rc.set_defaults(func=cmd_recall)
    qs = sub.add_parser("questions", help="check eval/questions.jsonl, or list an entry's sections")
    qs.add_argument("entry", nargs="?", help="list this entry's anchors and headings")
    qs.set_defaults(func=cmd_questions)
    args = parser.parse_args()
    args.func(args)
