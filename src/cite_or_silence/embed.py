"""Embeddings: each chunk becomes a vector of 1,024 numbers, so chunks that mean similar things
land close together whatever language they are written in.

The model is bge-m3 (multilingual, runs locally on the M-series GPU through MPS). Computing all
chunks takes a while, so the work is saved in shards of SHARD chunks: an interrupted run resumes
from the first missing shard.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np

MODEL = "BAAI/bge-m3"
RERANKER = "BAAI/bge-reranker-v2-m3"  # multilingual cross-encoder from the same family
DIM = 1024
SHARD = 4096
MAX_TOKENS = 512  # chunks are at most ~300 words; longer inputs only slow the model down


def load_model():
    import torch
    from sentence_transformers import SentenceTransformer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(MODEL, device=device)
    model.max_seq_length = MAX_TOKENS
    if device == "mps":
        model.half()
    return model


def load_reranker():
    """A scorer for search.rerank: reads each (question, passage) pair and returns its relevance."""
    import torch
    from sentence_transformers import CrossEncoder

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = CrossEncoder(RERANKER, device=device, max_length=MAX_TOKENS)
    if device == "mps":
        model.model.half()

    def scorer(query: str, passages: list[str]) -> list[float]:
        return model.predict([(query, p) for p in passages], batch_size=8).tolist()

    return scorer


def encode(model, texts: list[str], batch_size: int = 8) -> np.ndarray:
    vectors = model.encode(texts, batch_size=batch_size, normalize_embeddings=True, convert_to_numpy=True)
    return vectors.astype(np.float32)


def _texts(chunks: Path) -> Iterator[str]:
    with chunks.open(encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            # The heading tells the model what the passage is about when the text alone doesn't.
            yield f"{c['entry_title']} — {c['heading']}\n{c['text']}"


def embed_all(chunks: Path, out_dir: Path, log: Callable[[str], None] = print) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = list(_texts(chunks))
    shards = range(0, len(texts), SHARD)
    model = None
    for n, start in enumerate(shards):
        path = out_dir / f"{n:05d}.npy"
        if path.exists():
            continue
        model = model or load_model()
        batch = texts[start : start + SHARD]
        # Similar lengths in one batch waste less padding: sort, encode, put back in order.
        order = sorted(range(len(batch)), key=lambda i: len(batch[i]))
        vectors = encode(model, [batch[i] for i in order])
        shard = np.empty_like(vectors)
        shard[order] = vectors
        np.save(path.with_suffix(".part.npy"), shard)
        path.with_suffix(".part.npy").rename(path)
        log(f"shard {n + 1}/{len(shards)}: chunks {start}-{start + len(batch) - 1}")


def load_all(out_dir: Path) -> np.ndarray:
    return np.concatenate([np.load(p) for p in sorted(out_dir.glob("[0-9]*.npy")) if ".part" not in p.name])
