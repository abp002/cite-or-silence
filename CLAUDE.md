# cite-or-silence

Philosophy Q&A answered only from the Stanford Encyclopedia of Philosophy (SEP). Every sentence
carries a citation to the exact section, every citation is checked automatically, and when the SEP
does not cover the question the answer is "I don't know". Questions may be asked in Spanish even
though the SEP is in English. Public repo, written in English.

## QA
Nivel: activo

Bitácora: ALE

## Licensing rule (do not break)
The SEP terms allow crawling each entry for indexing, not redistributing it (only links, or closed
groups of at most 30 people). Nothing containing SEP text is committed or published: not the raw
HTML, not chunks, not the DuckDB file, not dumps of retrieved passages. `data/` is gitignored for
that reason. Eval questions with their `entry#anchor` targets and short quotes in the README are fine.
Test fixtures use invented text that only mimics SEP markup.

## How it works
- `fetch`: reads https://plato.stanford.edu/contents.html (~1,870 entries) and downloads each entry
  to `data/raw/<slug>.html`, 5 s apart (`crawl-delay: 5` in robots.txt). Resumable: existing files are
  skipped; writes go through a `.part` file. A full run takes ~2.5 h.
- `chunk`: cuts each entry into the preamble plus every `h2/h3/h4` section of `#main-text`, keeping the
  section number ("4.1") and its `id` anchor, so a citation is `entries/<slug>/#<anchor>`. Bibliography,
  TOC, academic tools and related entries are outside `#main-text` and ignored. Paragraphs under
  60 words merge forward, over 300 split on sentence ends; chunks never cross a section. Output:
  `data/chunks.jsonl`. A handful of chunks exceed 300 words (one sentence full of formulas).
- Footnote markers (`<sup>[1]</sup>`) are dropped; the footnotes themselves (notes.html) are not fetched.

## Plan (v1)
1. Fetch and chunk, checking sections come out right.
2. Question set (~100: single entry, multi-entry, not in the SEP), written BEFORE the RAG exists.
3. Hybrid retrieval (multilingual embeddings + BM25) in DuckDB (vss + fts); measure Recall@5.
4. Generation with per-sentence citations + verification (quote exists verbatim and supports the
   sentence; failing sentences are dropped; nothing left -> "the SEP doesn't cover this").
5. README with numbers (no-RAG vs RAG+verification), "where it fails", demo video, blog post.

LLM provider stays behind an interface (ChatGPT via OAuth first; free APIs or local as fallback).
The README must say which model produced each number.

## Commands
- `uv run pytest`
- `uv run cite-or-silence fetch [--limit N]`
- `uv run cite-or-silence chunk`
