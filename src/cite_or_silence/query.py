"""What the search looks for: not the question itself, but a sketch of its answer.

The embedding of a question finds the right entry but often a neighbouring section: a question
looks like other questions and like introductions, not like the paragraph that answers it. So
the model first writes, from memory and in English, the two or three sentences an encyclopedia
would use to answer (HyDE, "hypothetical document embeddings"), and the search uses the vector
of that sketch. Measured on the question set (scripts/recall_hyde.py), the gold section is among
the ten passages 69 % of the time instead of 58 %; translating the question into English, the
first idea, gave 3 points at most (scripts/recall_translated.py).

The sketch is only a search query. It never reaches the answer: the model still answers the
original question from the retrieved passages alone, and every sentence is still verified, so
a wrong sketch can at worst retrieve the wrong passages.

Rewrites are cached per model in a JSON file keyed by the question, so a rerun searches with
the same words.
"""

import json
from collections.abc import Callable
from pathlib import Path

from cite_or_silence.provider import Provider

BATCH = 30

SCHEMA = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
    "required": ["translations"],
    "additionalProperties": False,
}


def _numbered(questions: list[str]) -> str:
    return "\n".join(f"{n}. {q}" for n, q in enumerate(questions, start=1))


def sketch_prompt(questions: list[str]) -> str:
    return (
        "For each numbered question write, in English, the two or three sentences an encyclopedia of "
        "philosophy would use to answer it, one passage per question, in the same order. Write the "
        "passage even if you are unsure; it is only used as a search query. If the question assumes "
        "something false, write what the encyclopedia would say about that topic instead.\n\n" + _numbered(questions)
    )


def translation_prompt(questions: list[str]) -> str:
    return (
        "Translate each numbered question into English, one translation per question, in the same "
        "order. Translate literally: keep every name, claim and assumption exactly as asked, even "
        "if it is wrong or the thing does not exist. Do not answer, correct or explain anything. "
        "A question already in English is returned unchanged.\n\n" + _numbered(questions)
    )


def rewrite(
    questions: list[str], model: Provider, cache: Path | None = None, prompt: Callable[[list[str]], str] = sketch_prompt
) -> list[str]:
    """One rewriting per question, in order; only the ones not in the cache reach the model."""
    known: dict[str, str] = json.loads(cache.read_text(encoding="utf-8")) if cache and cache.exists() else {}
    todo = [q for q in dict.fromkeys(questions) if q not in known]
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        got = model.complete(prompt(batch), SCHEMA)["translations"]
        if len(got) != len(batch):
            raise RuntimeError(f"asked for {len(batch)} rewritings, got {len(got)}")
        known.update(zip(batch, got))
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
    return [known[q] for q in questions]
