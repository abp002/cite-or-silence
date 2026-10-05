"""Cut an SEP entry into sections (§1, §2.3…) and then into paragraph-sized chunks.

Every chunk remembers its entry, section number and the anchor of its section, so an
answer can cite https://plato.stanford.edu/entries/<entry>/#<anchor> and a reader lands
on the exact section.
"""

import re
from dataclasses import asdict, dataclass

from bs4 import BeautifulSoup, Tag

from cite_or_silence.fetch import entry_url

HEADINGS = ("h2", "h3", "h4")
BLOCKS = ("p", "li", "dd", "pre")
MIN_WORDS = 60  # shorter paragraphs are merged with the next one in the same section
MAX_WORDS = 300  # longer paragraphs are split on sentence boundaries

NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$", re.S)
FOOTNOTE = re.compile(r"^\[\d+\]$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")


@dataclass
class Section:
    anchor: str | None  # None for the preamble, which has no id of its own
    number: str | None  # "4.1"; None for the preamble and unnumbered headings
    heading: str
    paragraphs: list[str]


@dataclass
class Chunk:
    id: str
    entry: str
    entry_title: str
    section: str | None
    heading: str
    url: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_heading(text: str) -> tuple[str | None, str]:
    """'4.1 The Humanity Formula' -> ('4.1', 'The Humanity Formula')."""
    match = NUMBERED.match(clean(text))
    if match:
        return match.group(1), clean(match.group(2))
    return None, clean(text)


def _blocks(container: Tag):
    """Headings and text blocks in document order, skipping blocks nested in other blocks."""
    for el in container.find_all((*HEADINGS, *BLOCKS)):
        parent = el.find_parent(BLOCKS)
        if el.name in BLOCKS and parent is not None and container in parent.parents:
            continue
        yield el


def heading_anchor(el: Tag) -> str | None:
    """SEP headings carry their anchor as <h2 id>, <h2><a name></h2> or <h2><a id></h2>."""
    if el.get("id"):
        return el["id"]
    link = el.find("a", attrs={"name": True}) or el.find("a", attrs={"id": True})
    return (link.get("name") or link.get("id")) if link else None


def parse_entry(html: str) -> tuple[str, list[Section]]:
    soup = BeautifulSoup(html, "lxml")
    for sup in soup.find_all("sup"):
        if FOOTNOTE.match(clean(sup.get_text())):
            sup.decompose()
    title = clean(soup.find("h1").get_text()) if soup.find("h1") else ""

    sections: list[Section] = []
    preamble = soup.find(id="preamble")
    if preamble:
        paragraphs = [clean(el.get_text(" ")) for el in _blocks(preamble) if el.name in BLOCKS]
        sections.append(Section(None, None, "Preamble", [p for p in paragraphs if p]))

    main = soup.find(id="main-text")
    if main:
        current: Section | None = None
        for el in _blocks(main):
            if el.name in HEADINGS:
                number, heading = split_heading(el.get_text(" "))
                # A heading without an anchor of its own is linked through the nearest one above it.
                anchor = heading_anchor(el) or (current.anchor if current else None)
                current = Section(anchor, number, heading, [])
                sections.append(current)
            elif current is not None:
                text = clean(el.get_text(" "))
                if text:
                    current.paragraphs.append(text)
    return title, [s for s in sections if s.paragraphs]


def _split_long(paragraph: str) -> list[str]:
    if len(paragraph.split()) <= MAX_WORDS:
        return [paragraph]
    pieces, current = [], []
    for sentence in SENTENCE_END.split(paragraph):
        if current and len(" ".join(current + [sentence]).split()) > MAX_WORDS:
            pieces.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        pieces.append(" ".join(current))
    return pieces


def section_chunks(paragraphs: list[str]) -> list[str]:
    """Merge short paragraphs forward and split long ones, never crossing the section."""
    pieces = [piece for p in paragraphs for piece in _split_long(p)]
    chunks: list[str] = []
    buffer = ""
    for piece in pieces:
        buffer = f"{buffer} {piece}".strip()
        if len(buffer.split()) >= MIN_WORDS:
            chunks.append(buffer)
            buffer = ""
    if buffer:
        if chunks and len(f"{chunks[-1]} {buffer}".split()) <= MAX_WORDS:
            chunks[-1] = f"{chunks[-1]} {buffer}"
        else:
            chunks.append(buffer)
    return chunks


def chunk_entry(slug: str, html: str) -> list[Chunk]:
    title, sections = parse_entry(html)
    chunks = []
    per_anchor: dict[str, int] = {}  # sections can share an anchor, so numbering runs per anchor
    for section in sections:
        anchor = section.anchor or "preamble"
        url = entry_url(slug) + (f"#{section.anchor}" if section.anchor else "")
        for text in section_chunks(section.paragraphs):
            k = per_anchor.get(anchor, 0)
            per_anchor[anchor] = k + 1
            chunks.append(Chunk(f"{slug}#{anchor}:{k}", slug, title, section.number, section.heading, url, text))
    return chunks
