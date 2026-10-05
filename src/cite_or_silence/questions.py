"""The evaluation set: questions written before retrieval existed, with their gold sections.

Gold anchors are chosen by reading an entry's section headings, never by looking at what the
system retrieves; `check` only reports problems and lists headings to choose from.
"""

import json
from pathlib import Path

from cite_or_silence.chunk import parse_entry

TYPES = {"single", "multi", "none", "false_premise"}


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check(questions: list[dict], raw_dir: Path) -> list[str]:
    """Problems that make the set unusable for scoring. Empty list = ready."""
    problems = []
    seen = set()
    for q in questions:
        qid = q["id"]
        if qid in seen:
            problems.append(f"{qid}: duplicate id")
        seen.add(qid)
        if q["type"] not in TYPES:
            problems.append(f"{qid}: unknown type {q['type']!r}")
        if (q["type"] == "none") != (not q["gold"]):
            problems.append(f"{qid}: only 'none' questions have no gold")
        if q["type"] == "multi" and len({g["entry"] for g in q["gold"]}) < 2:
            problems.append(f"{qid}: 'multi' needs at least two entries")
        for g in q["gold"]:
            path = raw_dir / f"{g['entry']}.html"
            if not path.exists():
                problems.append(f"{qid}: entry {g['entry']} not downloaded")
                continue
            if g.get("anchor") is None:
                problems.append(f"{qid}: no anchor chosen in {g['entry']}")
                continue
            _, sections = parse_entry(path.read_text(encoding="utf-8"))
            if g["anchor"] not in {s.anchor or "preamble" for s in sections}:
                problems.append(f"{qid}: anchor {g['anchor']} not found in {g['entry']}")
    return problems


def headings(entry: str, raw_dir: Path) -> list[str]:
    _, sections = parse_entry((raw_dir / f"{entry}.html").read_text(encoding="utf-8"))
    return [f"{s.anchor or 'preamble'}  {s.number or ''} {s.heading}".replace("  ", " ") for s in sections]
