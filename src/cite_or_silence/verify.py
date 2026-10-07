"""Checking an answer sentence by sentence; whatever fails is dropped.

Each sentence comes with the passage it cites and a quote copied from that passage. Two checks:
1. the quote is really in the passage (code: exact match after normalising quotes, dashes,
   whitespace and case) and is long enough to carry a claim;
2. the quote supports the sentence (a judge model, one call for all sentences of an answer).
When no sentence survives, the answer is silence.
"""

import re
import unicodedata
from dataclasses import dataclass

from cite_or_silence.provider import Provider

MIN_QUOTE_WORDS = 5  # a name or a short phrase proves nothing; fixed before any evaluation
SILENCE = "La SEP no cubre esta pregunta."

_TRANSLATE = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE).lower()
    return re.sub(r"\s+", " ", text).strip().strip("\"'.,;: ")


def quote_in(quote: str, passage: str) -> bool:
    q = normalize(quote)
    return len(q.split()) >= MIN_QUOTE_WORDS and q in normalize(passage)


@dataclass
class Sentence:
    text: str
    source: int  # 1-based index into the passages given to the model
    quote: str
    dropped: str | None = None  # why it was dropped; None if kept


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"n": {"type": "integer"}, "supported": {"type": "boolean"}},
                "required": ["n", "supported"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


def judge_prompt(pairs: list[tuple[int, Sentence]]) -> str:
    items = "\n\n".join(f"[{n}]\nCLAIM: {s.text}\nQUOTE: {s.quote}" for n, s in pairs)
    return (
        "You check citations. For each numbered item, decide whether the QUOTE alone supports the "
        "CLAIM: everything the claim asserts must be stated or directly implied by the quote. The "
        "claim may be in another language than the quote; judge meaning, not wording. If the claim "
        "adds a name, date, cause or nuance the quote does not give, it is not supported.\n\n"
        f"{items}\n\nReturn one verdict per item, with its number."
    )


def verify(sentences: list[Sentence], passages: list[str], judge: Provider) -> list[Sentence]:
    """Marks every sentence kept or dropped (in place) and returns them all."""
    for s in sentences:
        if not 1 <= s.source <= len(passages):
            s.dropped = "cites a passage that was not given"
        elif not quote_in(s.quote, passages[s.source - 1]):
            s.dropped = "quote not found in the cited passage"
    pending = [(n, s) for n, s in enumerate(sentences, start=1) if s.dropped is None]
    if pending:
        verdicts = {v["n"]: v["supported"] for v in judge.complete(judge_prompt(pending), JUDGE_SCHEMA)["verdicts"]}
        for n, s in pending:
            if not verdicts.get(n, False):  # a missing verdict counts as unsupported
                s.dropped = "quote does not support the sentence"
    return sentences
