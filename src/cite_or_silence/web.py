"""A local page to ask questions and watch each step: how retrieval chose its passages, the model's
draft with a quote per sentence, and verification keeping or striking every sentence.

Listens on 127.0.0.1 only: the page shows SEP passages and quotes, which the SEP's terms let you
read, not republish. Steps reach the page as server-sent events while they happen. Every complete
answer is saved (under data/, gitignored: it holds SEP quotes), so asking the same question again
replays the same answer at once, also after a restart, which keeps a recorded demo repeatable;
fresh=1 asks the model again and replaces the saved answer.

`export` writes the public demo instead: the same page, static, replaying only the saved answers to
the example questions, with every quote removed so nothing of the SEP's text is published. Titles,
section headings and links to plato.stanford.edu stay: the SEP's terms allow linking.
"""

import html
import json
import re
import shutil
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import duckdb

from cite_or_silence.answer import Passage, draft
from cite_or_silence.provider import Provider
from cite_or_silence.search import PER_ENTRY
from cite_or_silence.verify import verify

PAGE = Path(__file__).with_name("web.html")
STATIC = Path(__file__).with_name("static")  # the logo files, also used by the README
TYPES = {".svg": "image/svg+xml", ".png": "image/png"}

Event = tuple[str, dict]
HEAD = 48  # how many of the question's embedding values the page draws


@dataclass
class Retrieval:
    """What the search did for one question: the passages it kept, and how it got to them."""

    passages: list[Passage]
    vector: list[float]  # the question's embedding
    candidates: list[tuple[Passage, float, str]]  # the dense pool, nearest first: passage, similarity, fate

# The questions the page offers, per language, grouped by what they test (the bench's types; the page
# names each group in TEXT.groups); the public demo can answer only these. Taken from eval/questions.jsonl.
EXAMPLES = {
    "es": {
        "single": [
            "¿Qué intenta mostrar Searle con el argumento de la habitación china?",
            "¿Qué son los casos Gettier y qué ponen en duda?",
            "¿Qué es el velo de ignorancia de Rawls?",
            "¿Qué ilustra la alegoría de la caverna de Platón?",
            "¿Qué significa «wu wei» en el Daodejing?",
        ],
        "multi": [
            "¿Qué dirían Kant y un consecuencialista sobre mentir para salvar a alguien?",
            "¿En qué discrepan Popper y Kuhn sobre cómo avanza la ciencia?",
            "¿Qué relación hay entre la habitación china y el test de Turing?",
        ],
        "false_premise": [
            "¿Por qué Kant defendía el utilitarismo?",
            "¿Por qué Hume era racionalista?",
        ],
        "none": [
            "¿Qué opinaba Platón de los smartphones?",
            "¿Qué es el «principio de resonancia ontológica» de Heidegger?",
        ],
    },
    "en": {
        "single": [
            "What does Searle try to show with the Chinese room argument?",
            "What are Gettier cases and what do they call into question?",
            "What is Rawls's veil of ignorance?",
            "What does Plato's allegory of the cave illustrate?",
            "What does \"wu wei\" mean in the Daodejing?",
        ],
        "multi": [
            "What would Kant and a consequentialist say about lying to save someone?",
            "Where do Popper and Kuhn disagree about how science advances?",
            "How is the Chinese room related to the Turing test?",
        ],
        "false_premise": [
            "Why did Kant defend utilitarianism?",
            "Why was Hume a rationalist?",
        ],
        "none": [
            "What did Plato think of smartphones?",
            "What is Heidegger's \"principle of ontological resonance\"?",
        ],
    },
}


def examples() -> list[str]:
    """Every example question, all languages and groups, in page order."""
    return [q for groups in EXAMPLES.values() for qs in groups.values() for q in qs]


def pool(found: Retrieval, describe: Callable[[Passage], dict]) -> dict:
    """The search as the page shows it: the start of the question's vector, then every candidate
    with its similarity and why it was kept or left out. Like the passages, no SEP text."""
    return {
        "dims": len(found.vector),
        "head": [round(x, 3) for x in found.vector[:HEAD]],
        "cap": PER_ENTRY,
        "candidates": [describe(p) | {"score": round(score, 3), "fate": fate} for p, score, fate in found.candidates],
    }


def steps(question: str, retrieve: Callable[[str], Retrieval], model: Provider, describe: Callable[[Passage], dict]) -> Iterator[Event]:
    """The answer in the order the page shows it: pool, passages, draft, verdicts, done."""
    found = retrieve(question)
    passages = found.passages
    yield "pool", pool(found, describe)
    yield "passages", {"passages": [describe(p) for p in passages]}
    sentences = draft(question, passages, model)
    yield "draft", {"sentences": [{"text": s.text, "source": s.source, "quote": s.quote} for s in sentences]}
    verify(sentences, [p.text for p in passages], model)
    yield "verdicts", {"dropped": [s.dropped for s in sentences]}
    yield "done", {"silent": all(s.dropped for s in sentences)}


def describer(con: duckdb.DuckDBPyConnection, raw: Path) -> Callable[[Passage], dict]:
    """Passage -> what the page shows of it: entry title, section number and heading, link."""

    @cache
    def title(entry: str) -> str:
        path = raw / f"{entry}.html"
        if not path.exists():
            return entry
        with path.open(encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
        found = re.search(r"<title>\s*(.*?)\s*\(Stanford Encyclopedia of Philosophy\)", head, re.S)
        return html.unescape(found[1]) if found else entry

    def describe(p: Passage) -> dict:
        (section,) = con.execute("SELECT section FROM chunks WHERE id = ?", [p.id]).fetchone()
        heading = None if p.anchor == "preamble" else p.heading
        return {"title": title(p.entry), "section": section, "heading": heading, "url": p.url}

    return describe


class Session:
    """One model and one database connection, so one answer at a time; answers saved for replay."""

    def __init__(self, retrieve: Callable[[str], Retrieval], model: Provider, describe: Callable[[Passage], dict], saved: Path | None = None):
        self.retrieve, self.model, self.describe, self.saved = retrieve, model, describe, saved
        self.lock = threading.Lock()
        self.answers: dict[str, list[Event]] = {}
        if saved and saved.exists():
            self.answers = {q: [tuple(e) for e in events] for q, events in json.loads(saved.read_text()).items()}

    def ask(self, question: str, fresh: bool = False) -> Iterator[Event]:
        key = " ".join(question.split())
        with self.lock:
            if not fresh and key in self.answers:
                events = self.answers[key]
                if "pool" not in dict(events):  # saved before the page showed the search: search again, no model
                    events = [("pool", pool(self.retrieve(key), self.describe)), *events]
                    self.answers[key] = events
                    self.save()
                yield from events
                return
            events = []
            for event in steps(key, self.retrieve, self.model, self.describe):
                events.append(event)
                yield event
            self.answers[key] = events  # only complete answers: a failed one is asked again
            self.save()

    def save(self) -> None:
        if self.saved:
            self.saved.parent.mkdir(parents=True, exist_ok=True)
            self.saved.write_text(json.dumps(self.answers, ensure_ascii=False, indent=1))


def render(facts: dict[str, str]) -> str:
    """The page with its __NAME__ placeholders filled in (escaped: they go into attributes)."""
    page = PAGE.read_text(encoding="utf-8")
    for name, value in (facts | {"EXAMPLES": json.dumps(EXAMPLES, ensure_ascii=False)}).items():
        page = page.replace(f"__{name}__", html.escape(value))
    return page


def public(events: list[Event]) -> list[Event]:
    """An answer without SEP text: the draft loses its quotes; passages never carried any."""
    out = []
    for name, data in events:
        if name == "draft":
            data = {"sentences": [{k: v for k, v in s.items() if k != "quote"} for s in data["sentences"]]}
        out.append((name, data))
    return out


def export(session: Session, out: Path, facts: dict[str, str]) -> int:
    """Write the public demo to out: page, logo and the example answers (asking the model for any
    not saved yet). Returns how many answers it holds."""
    answers = {q: public(list(session.ask(q))) for q in examples()}
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(facts | {"MODE": "public"}), encoding="utf-8")
    (out / "answers.json").write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    shutil.copytree(STATIC, out / "static", dirs_exist_ok=True)
    return len(answers)


def index_facts(model: Provider, entries: int, passages: int) -> dict[str, str]:
    """What the page quotes: the model, and the size of the index while it searches."""
    return {"MODEL": model.name, "ENTRIES": str(entries), "PASSAGES": str(passages)}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/":
            self.reply(render(self.server.facts | {"MODE": "live"}).encode(), "text/html; charset=utf-8")
        elif url.path.startswith("/static/"):
            path = STATIC / url.path.removeprefix("/static/")
            if path.parent != STATIC or path.suffix not in TYPES or not path.is_file():
                self.send_error(404)
                return
            self.reply(path.read_bytes(), TYPES[path.suffix])
        elif url.path == "/ask":
            query = parse_qs(url.query)
            question = query.get("q", [""])[0].strip()
            if not question:
                self.send_error(400, "missing q")
                return
            fresh = "fresh" in query
            print(f"? {question}" + (" (fresh)" if fresh else ""), flush=True)
            self.stream(self.server.session.ask(question, fresh))
        else:
            self.send_error(404)

    def reply(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def stream(self, events: Iterator[Event]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            for name, data in events:
                self.event(name, data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the page was closed or asked something else mid-answer
        except Exception as e:  # a model or search failure: tell the page instead of leaving it waiting
            print(f"  failed: {type(e).__name__}: {e}", flush=True)
            try:
                self.event("failed", {"message": f"{type(e).__name__}: {e}"})
            except OSError:
                pass
        finally:
            events.close()

    def event(self, name: str, data: dict) -> None:
        self.wfile.write(f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()

    def log_message(self, format, *args) -> None:
        pass  # one line per question (above) instead of the access log


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, session: Session, facts: dict[str, str]):
        super().__init__(("127.0.0.1", port), Handler)
        self.session, self.facts = session, facts


def serve(session: Session, port: int, entries: int = 0, passages: int = 0) -> None:
    """entries and passages: the size of the index, which the page quotes while it searches."""
    with Server(port, session, index_facts(session.model, entries, passages)) as server:
        print(f"cite-or-silence on http://127.0.0.1:{port} ({session.model.name}), {len(session.answers)} saved answers.", flush=True)
        print("A question asked before replays its saved answer; Shift+Enter or Shift+click asks the model again. Ctrl+C stops.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
