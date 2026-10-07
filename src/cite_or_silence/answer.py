"""Answering a question from retrieved SEP passages, every sentence with its passage and quote.

The model only sees the passages; it may answer in the question's language but quotes stay in
the SEP's English, so verify.quote_in can check them exactly. An answer that the passages do not
support should come back empty, which ends as silence after verification.
"""

from dataclasses import dataclass, field

import duckdb

from cite_or_silence.provider import Provider
from cite_or_silence.verify import SILENCE, Sentence, verify

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source": {"type": "integer"},
                    "quote": {"type": "string"},
                },
                "required": ["text", "source", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sentences"],
    "additionalProperties": False,
}


@dataclass
class Passage:
    id: str
    entry: str
    anchor: str
    heading: str
    text: str

    @property
    def url(self) -> str:
        base = f"https://plato.stanford.edu/entries/{self.entry}/"
        return base if self.anchor == "preamble" else f"{base}#{self.anchor}"


@dataclass
class Answer:
    question: str
    passages: list[Passage]
    sentences: list[Sentence] = field(default_factory=list)

    @property
    def kept(self) -> list[Sentence]:
        return [s for s in self.sentences if s.dropped is None]

    @property
    def silent(self) -> bool:
        return not self.kept

    def render(self) -> str:
        if self.silent:
            return SILENCE
        return " ".join(f"{s.text} [{s.source}]" for s in self.kept) + "\n\n" + "\n".join(
            f"[{n}] {self.passages[n - 1].url}" for n in sorted({s.source for s in self.kept})
        )


def passages_of(con: duckdb.DuckDBPyConnection, ids: list[str]) -> list[Passage]:
    rows = con.execute("SELECT id, entry, anchor, heading, text FROM chunks WHERE id IN ?", [ids]).fetchall()
    by_id = {r[0]: Passage(*r) for r in rows}
    return [by_id[i] for i in ids]


def answer_prompt(question: str, passages: list[Passage]) -> str:
    sources = "\n\n".join(f"[{n}] {p.entry} — {p.heading}\n{p.text}" for n, p in enumerate(passages, start=1))
    return (
        "Answer the question using ONLY the numbered passages from the Stanford Encyclopedia of "
        "Philosophy below. Write the answer in the language of the question, as a list of short "
        "sentences. For each sentence give:\n"
        "- source: the number of the passage it comes from;\n"
        "- quote: a span copied character for character from that passage, in its original English, "
        "long enough to back the whole sentence (at least a full clause; no ellipses, no paraphrase).\n"
        "Every sentence must be backed by its own quote. Do not add anything the passages do not say, "
        "not even well-known facts. If the question rests on a false premise, correct it with cited "
        "sentences. If the passages do not answer the question, return an empty list.\n\n"
        f"PASSAGES\n\n{sources}\n\nQUESTION: {question}"
    )


def answer(question: str, passages: list[Passage], model: Provider, judge: Provider) -> Answer:
    raw = model.complete(answer_prompt(question, passages), ANSWER_SCHEMA)["sentences"]
    sentences = [Sentence(s["text"], s["source"], s["quote"]) for s in raw]
    verify(sentences, [p.text for p in passages], judge)
    return Answer(question, passages, sentences)
