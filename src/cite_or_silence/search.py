"""Hybrid retrieval over the chunks, stored in DuckDB.

Two searches look at the same chunks in different ways and their rankings are merged:
- dense: the question's embedding against every chunk's embedding (meaning, any language),
  answered by an HNSW index so it doesn't compare against all 156k chunks one by one;
- bm25: classic keyword search over heading + text (exact words, names, rare terms);
- hybrid: both rankings fused with Reciprocal Rank Fusion;
- diverse: dense, but at most PER_ENTRY chunks from one entry, so a question comparing two
  authors gets both entries instead of five chunks of the first;
- rerank: the dense pool read again by a cross-encoder, which sees question and passage together
  and so can tell the exact section apart from its neighbours in the same entry.
"""

import json
from collections.abc import Callable
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa

MODES = ("dense", "bm25", "hybrid", "rerank", "diverse")
POOL = 50  # how deep each search looks before fusing or reranking
PER_ENTRY = 2  # fixed before measuring it, not tuned on the eval set

Scorer = Callable[[str, list[str]], list[float]]  # (question, passages) -> one score per passage


def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion: each ranking gives an item 1 / (k + position); scores add up.

    Only positions matter, never the raw scores, so a cosine similarity and a BM25 score can be
    combined without putting them on a common scale. k damps the gap between the very top
    positions; 60 is the value from the original paper. Ties keep first-seen order.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + position)
    return sorted(scores, key=lambda item: -scores[item])


def connect(db: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db))
    for ext in ("vss", "fts"):
        con.install_extension(ext)
        con.load_extension(ext)
    # The HNSW index lives in memory unless told to persist; we build it once and reuse it.
    con.execute("SET hnsw_enable_experimental_persistence = true")
    return con


def build_index(con: duckdb.DuckDBPyConnection, chunks: list[dict], vectors: np.ndarray) -> None:
    if len(chunks) != len(vectors):
        raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
    dim = vectors.shape[1]
    arrow_chunks = pa.table(
        {
            "id": [c["id"] for c in chunks],
            "entry": [c["entry"] for c in chunks],
            "anchor": [c["id"].split("#", 1)[1].rsplit(":", 1)[0] for c in chunks],
            "section": [c["section"] for c in chunks],
            "heading": [c["heading"] for c in chunks],
            "text": [c["text"] for c in chunks],
            "emb": pa.FixedSizeListArray.from_arrays(pa.array(vectors.astype(np.float32).ravel()), dim),
        }
    )
    con.execute("DROP TABLE IF EXISTS chunks")
    con.execute("CREATE TABLE chunks AS SELECT * FROM arrow_chunks")
    con.execute("CREATE INDEX chunks_hnsw ON chunks USING HNSW (emb) WITH (metric = 'cosine')")
    con.execute("PRAGMA create_fts_index('chunks', 'id', 'heading', 'text', stemmer = 'english', overwrite = 1)")


def dense(con: duckdb.DuckDBPyConnection, vector: np.ndarray, n: int = POOL) -> list[str]:
    dim = len(vector)
    rows = con.execute(
        f"SELECT id FROM chunks ORDER BY array_cosine_distance(emb, ?::FLOAT[{dim}]) LIMIT ?",
        [vector.astype(np.float32).tolist(), n],
    ).fetchall()
    return [r[0] for r in rows]


def bm25(con: duckdb.DuckDBPyConnection, query: str, n: int = POOL) -> list[str]:
    rows = con.execute(
        """SELECT id FROM (SELECT id, fts_main_chunks.match_bm25(id, ?) AS score FROM chunks)
           WHERE score IS NOT NULL ORDER BY score DESC, id LIMIT ?""",
        [query, n],
    ).fetchall()
    return [r[0] for r in rows]


def cap_per_entry(ids: list[str], k: int, cap: int = PER_ENTRY) -> list[str]:
    """The first k ids, skipping any whose entry already has cap ids in; order is kept."""
    taken: dict[str, int] = {}
    kept = []
    for i in ids:
        entry = i.split("#", 1)[0]
        if taken.get(entry, 0) < cap:
            taken[entry] = taken.get(entry, 0) + 1
            kept.append(i)
            if len(kept) == k:
                break
    return kept


def rerank(con: duckdb.DuckDBPyConnection, query: str, ids: list[str], scorer: Scorer) -> list[str]:
    """Reorder ids by the scorer's verdict on each passage; ties keep the incoming order."""
    texts = dict(con.execute("SELECT id, heading || '\n' || text FROM chunks WHERE id IN ?", [ids]).fetchall())
    scores = scorer(query, [texts[i] for i in ids])
    order = sorted(range(len(ids)), key=lambda n: -scores[n])
    return [ids[n] for n in order]


def search(
    con: duckdb.DuckDBPyConnection,
    query: str,
    vector: np.ndarray,
    mode: str = "hybrid",
    k: int = 5,
    scorer: Scorer | None = None,
) -> list[str]:
    if mode == "dense":
        return dense(con, vector, k)
    if mode == "bm25":
        return bm25(con, query, k)
    if mode == "diverse":
        return cap_per_entry(dense(con, vector), k)
    if mode == "rerank":
        if scorer is None:
            raise ValueError("rerank mode needs a scorer")
        return rerank(con, query, dense(con, vector), scorer)[:k]
    return rrf([dense(con, vector), bm25(con, query)])[:k]


def chunks_of(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]
