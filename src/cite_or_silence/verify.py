"""Checking an answer sentence by sentence; whatever fails is dropped.

Each sentence comes with the passage it cites and a quote copied from that passage. Two checks:
1. the quote is really in the passage (code: exact match after normalising quotes, dashes,
   whitespace and case) and is long enough to carry a claim;
2. the quote supports the sentence (a judge model, one call for all sentences of an answer).
When no sentence survives, the answer is silence.

A sentence that corrects a false premise of the question ("Kant did not defend utilitarianism")
has no passage that says so in those words: the SEP states what Kant held, not what he did not.
Such a sentence names the premise it denies and is checked differently in step 2: its quote must
state something that cannot be true together with the premise. Step 1 is the same, so a
correction still rests on words that are in the SEP.
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
    text = re.sub(r"\\[()\[\]]", "", text)  # MathJax delimiters: the page shows F where the chunk has \(F\)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r" ([.,;:!?)])", r"\1", text)  # gap left by a removed footnote marker
    return text.strip().strip("\"'.,;: ")


def quote_in(quote: str, passage: str) -> bool:
    q = normalize(quote)
    return len(q.split()) >= MIN_QUOTE_WORDS and q in normalize(passage)


@dataclass
class Sentence:
    text: str
    source: int  # 1-based index into the passages given to the model
    quote: str
    dropped: str | None = None  # why it was dropped; None if kept
    premise: str = ""  # the assumption of the question this sentence denies; empty for an ordinary claim


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


def judge_prompt(pairs: list[tuple[int, Sentence]], question: str = "") -> str:
    def item(n: int, s: Sentence) -> str:
        if s.premise:
            return f"[{n}]\nPREMISE: {s.premise}\nCORRECTION: {s.text}\nQUOTE: {s.quote}"
        return f"[{n}]\nCLAIM: {s.text}\nQUOTE: {s.quote}"

    items = "\n\n".join(item(n, s) for n, s in pairs)
    corrections = ""
    if any(s.premise for _, s in pairs):  # the prompt for ordinary claims stays exactly as it was
        corrections = (
            "Some items have a PREMISE and a CORRECTION instead of a claim. The PREMISE is something "
            "the user's QUESTION takes for granted, and the CORRECTION denies it. Such an item is "
            "supported only if all three hold: the QUESTION really assumes the PREMISE; the QUOTE "
            "states something that cannot be true together with the PREMISE (a quote that is merely "
            "about the same topic, or silent on the matter, does not count); and the CORRECTION says "
            "nothing beyond denying the PREMISE and what the QUOTE states.\n\n"
            f"QUESTION: {question}\n\n"
        )
    return (
        "You check citations. For each numbered item, decide whether the QUOTE alone supports the "
        "CLAIM: everything the claim asserts must be stated or directly implied by the quote. The "
        "claim may be in another language than the quote; judge meaning, not wording. If the claim "
        "adds a name, date, cause or nuance the quote does not give, it is not supported.\n\n"
        f"{corrections}{items}\n\nReturn one verdict per item, with its number."
    )


def verify(sentences: list[Sentence], passages: list[str], judge: Provider, question: str = "") -> list[Sentence]:
    """Marks every sentence kept or dropped (in place) and returns them all."""
    for s in sentences:
        if not 1 <= s.source <= len(passages):
            s.dropped = "cites a passage that was not given"
        elif not quote_in(s.quote, passages[s.source - 1]):
            s.dropped = "quote not found in the cited passage"
    pending = [(n, s) for n, s in enumerate(sentences, start=1) if s.dropped is None]
    if pending:
        verdicts = {v["n"]: v["supported"] for v in judge.complete(judge_prompt(pending, question), JUDGE_SCHEMA)["verdicts"]}
        for n, s in pending:
            if not verdicts.get(n, False):  # a missing verdict counts as unsupported
                s.dropped = "quote does not contradict the premise" if s.premise else "quote does not support the sentence"
    return sentences
