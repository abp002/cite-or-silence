import argparse
import json
import statistics
from pathlib import Path

from cite_or_silence.chunk import chunk_entry
from cite_or_silence.fetch import fetch_all
from cite_or_silence import questions

DATA = Path("data")
RAW = DATA / "raw"
CHUNKS = DATA / "chunks.jsonl"
QUESTIONS = Path("eval/questions.jsonl")


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
    qs = sub.add_parser("questions", help="check eval/questions.jsonl, or list an entry's sections")
    qs.add_argument("entry", nargs="?", help="list this entry's anchors and headings")
    qs.set_defaults(func=cmd_questions)
    args = parser.parse_args()
    args.func(args)
