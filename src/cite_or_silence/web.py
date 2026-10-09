"""A local page to ask questions and watch each step: the passages retrieval finds, the model's
draft with a quote per sentence, and verification keeping or striking every sentence.

Listens on 127.0.0.1 only: the page shows SEP passages and quotes, which the SEP's terms let you
read, not republish. Steps reach the page as server-sent events while they happen. Every complete
answer is saved (under data/, gitignored: it holds SEP quotes), so asking the same question again
replays the same answer at once, also after a restart, which keeps a recorded demo repeatable;
fresh=1 asks the model again and replaces the saved answer.
"""

import html
import json
import re
import threading
from collections.abc import Callable, Iterator
from functools import cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import duckdb

from cite_or_silence.answer import Passage, draft
from cite_or_silence.provider import Provider
from cite_or_silence.verify import verify

PAGE = Path(__file__).with_name("web.html")

Event = tuple[str, dict]


def steps(question: str, retrieve: Callable[[str], list[Passage]], model: Provider, describe: Callable[[Passage], dict]) -> Iterator[Event]:
    """The answer in the order the page shows it: passages, draft, verdicts, done."""
    passages = retrieve(question)
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

    def __init__(self, retrieve: Callable[[str], list[Passage]], model: Provider, describe: Callable[[Passage], dict], saved: Path | None = None):
        self.retrieve, self.model, self.describe, self.saved = retrieve, model, describe, saved
        self.lock = threading.Lock()
        self.answers: dict[str, list[Event]] = {}
        if saved and saved.exists():
            self.answers = {q: [tuple(e) for e in events] for q, events in json.loads(saved.read_text()).items()}

    def ask(self, question: str, fresh: bool = False) -> Iterator[Event]:
        key = " ".join(question.split())
        with self.lock:
            if not fresh and key in self.answers:
                yield from self.answers[key]
                return
            events = []
            for event in steps(key, self.retrieve, self.model, self.describe):
                events.append(event)
                yield event
            self.answers[key] = events  # only complete answers: a failed one is asked again
            if self.saved:
                self.saved.parent.mkdir(parents=True, exist_ok=True)
                self.saved.write_text(json.dumps(self.answers, ensure_ascii=False, indent=1))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/":
            page = PAGE.read_text(encoding="utf-8").replace("__MODEL__", html.escape(self.server.session.model.name))
            body = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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

    def __init__(self, port: int, session: Session):
        super().__init__(("127.0.0.1", port), Handler)
        self.session = session


def serve(session: Session, port: int) -> None:
    with Server(port, session) as server:
        print(f"cite-or-silence on http://127.0.0.1:{port} ({session.model.name}), {len(session.answers)} saved answers.", flush=True)
        print("A question asked before replays its saved answer; Shift+Enter or Shift+click asks the model again. Ctrl+C stops.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
