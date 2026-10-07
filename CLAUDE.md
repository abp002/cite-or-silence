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
- `embed`: bge-m3 (multilingual, 1,024 dims, fp16 on MPS, batch 8, max 512 tokens) over
  "entry title — heading\ntext" of every chunk, saved as shards of 4,096 in `data/embeddings/`.
  Resumable. ~9 chunks/s on the M4, so the full run takes hours, not minutes.
- `index`: loads chunks + vectors into `data/sep.duckdb`: HNSW index (vss, cosine) and BM25 (fts,
  english stemmer, over heading + text). HNSW persistence is an experimental DuckDB flag.
- Search modes: `dense`, `bm25`, `hybrid` (top 50 of each fused with RRF, k = 60), `rerank` (dense top 50
  reordered by bge-reranker-v2-m3) and `diverse` (dense, at most 2 chunks per entry, cap fixed before
  measuring). Recall@5 by section: dense 0.51, hybrid 0.37, rerank 0.49, diverse 0.51 (multi 0.30 vs 0.28);
  Recall@50 dense 0.86. The gold is in the pool but badly ordered, and none of the cheap reorderings beat
  dense: the limit is Spanish questions against English text. Production search: `diverse`, k = 10.
- `recall`: Recall@k per question type for the three modes, by section and by entry. A chunk from
  subsection 3.2 counts for gold section 3. `none` questions have no gold and are left out.
  Questions are Spanish and the SEP English, so BM25 alone only helps with names and loanwords.

- `ask`: diverse search (k = 10) -> the model answers as JSON sentences, each with a passage number
  and a quote copied from it in English -> `verify` drops a sentence whose quote is not in the cited
  passage (exact after normalising quotes, dashes, whitespace, case; at least 5 words) and then asks a
  judge, in one call per answer, whether each quote supports its sentence. Nothing left -> silence.
- Providers (`provider.py`): `codex` runs `codex exec` with the ChatGPT login (OAuth, no API key) in an
  empty temp dir, read-only, `--ignore-user-config`, stdin closed (open stdin makes it hang); ~15k
  tokens per call because of Codex's agent prompt. `ollama` (qwen3:14b) is the free local fallback.
  If codex fails with "refresh token was already used", run `codex login` again.

- `bench`: three arms of the same model per question: `bare` (no retrieval), `rag` (before
  verification), `verified`. Every arm may return an empty list. One judge call per question grades the
  arms under shuffled letters: none -> abstains; false_premise -> corrects; single/multi -> each
  sentence against the gold sections + the retrieved passages (supported / contradicted / unbacked).
  Rules fixed before the first run. Results in `data/bench/<provider>/<qid>.json`, resumable.
- Known limit: a sentence about the question itself ("the premise is wrong") has no quote to back it,
  so verification drops the explicit correction of a false premise.

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
- `uv run cite-or-silence embed` (hours; run with `caffeinate -i`)
- `uv run cite-or-silence index`
- `uv run cite-or-silence search "question" [--mode dense|bm25|hybrid] [-k 5]`
- `uv run cite-or-silence recall [-k 5] [--misses MODE]`
- `uv run cite-or-silence ask "question" [--provider codex|ollama] [-k 10]`
- `uv run cite-or-silence bench [--ids s01,m02] [--limit N] [--provider codex|ollama]` (~1 h for all)
