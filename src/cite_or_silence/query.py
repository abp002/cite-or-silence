"""Rewriting the question before searching: two experiments, neither adopted (issue #3).

The embedding of a Spanish question finds the right SEP entry but often a neighbouring section.
Two rewritings were tried, each written by the answering model and cached per model:

- a literal English translation (`translation_prompt`). The language turned out not to be the
  limit: the gold section is among the top five 55 % of the time instead of 51 %
  (scripts/recall_translated.py);
- a sketch of the answer (`sketch_prompt`): the two or three sentences an encyclopedia would
  use, written from memory, whose vector is searched instead of the question's (HyDE). It
  does find the gold section more often (69 % instead of 58 % among the ten passages the system
  uses; scripts/recall_hyde.py), but the answers got no better in the bench: the gold section
  was cited no more often, false premises were corrected less often, and it costs a call per
  question. So search still embeds the question; `bench --search sketch` reruns the experiment.

A rewriting is only ever a search query: the model answers the original question from the
retrieved passages alone.
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
