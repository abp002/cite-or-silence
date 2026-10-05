"""Recall@k: of the sections a question needs (its gold), how many show up among the k chunks
retrieved for it. A chunk counts for a gold section when it comes from that section or from one
of its subsections (gold "3" is hit by a chunk of "3.2"): citing 3.2 is citing inside 3.

Questions of type "none" have no gold, so they have no recall; they are judged in generation.
"""

from dataclasses import dataclass
from statistics import mean


@dataclass(frozen=True)
class Section:
    entry: str
    anchor: str
    number: str | None  # "3.2"; None for the preamble and unnumbered sections


def covers(gold: Section, chunk: Section) -> bool:
    if gold.entry != chunk.entry:
        return False
    if gold.anchor == chunk.anchor:
        return True
    return bool(gold.number and chunk.number and chunk.number.startswith(gold.number + "."))


def recall(gold: list[Section], retrieved: list[Section]) -> float:
    return sum(any(covers(g, r) for r in retrieved) for g in gold) / len(gold)


def entry_recall(gold: list[Section], retrieved: list[Section]) -> float:
    """Looser: the right entry was found, whichever section. Shows how far off the misses are."""
    found = {r.entry for r in retrieved}
    entries = {g.entry for g in gold}
    return len(entries & found) / len(entries)


def by_type(scored: list[tuple[str, float]]) -> dict[str, tuple[int, float]]:
    """(question type, score) pairs -> {type: (count, mean)}, plus 'all'."""
    groups: dict[str, list[float]] = {}
    for qtype, score in scored:
        groups.setdefault(qtype, []).append(score)
        groups.setdefault("all", []).append(score)
    return {t: (len(s), mean(s)) for t, s in groups.items()}
