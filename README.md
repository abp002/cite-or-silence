# cite-or-silence

Ask a philosophy question, get an answer built only from the
[Stanford Encyclopedia of Philosophy](https://plato.stanford.edu/). Every sentence links to the exact
section it comes from, every citation is checked by machine, and if the SEP doesn't cover the
question, the answer is **"I don't know."** Questions can be asked in Spanish; the SEP is in English.

> Work in progress. Numbers will land here once the evaluation runs.

## What gets measured

| Metric | Question it answers |
|---|---|
| Recall@5 | Did retrieval find the right section? |
| Citation precision | Does each citation support its sentence? |
| Faithfulness | Does the answer stay inside what it cites? |
| Refusal accuracy | Does it say "I don't know" when it should? |

The headline is a comparison: the same model without retrieval versus with retrieval and citation
checking.

## Pipeline

1. **Fetch** every SEP entry, one request every 5 seconds (as the SEP's robots.txt asks).
2. **Chunk** by section (§1, §2.3…) and paragraph; each chunk keeps a link to its section.
3. **Retrieve** with multilingual embeddings plus BM25, stored in DuckDB.
4. **Answer and verify**: each sentence cites a chunk; a second pass checks the quote exists and
   supports the sentence. Sentences that fail are dropped.
5. **Evaluate** on ~100 questions written before the retrieval system existed.

## Running it

```bash
uv sync
uv run cite-or-silence fetch      # ~2.5 h, once
uv run cite-or-silence chunk
uv run pytest
```

## About the SEP text

The SEP allows crawling entries for indexing but not redistributing them. This repository contains
no SEP text: the corpus, chunks and index are built locally on your machine and never committed.
Please support the SEP: https://plato.stanford.edu/support/

## License

Code: MIT. SEP entries remain under the SEP's own terms.
