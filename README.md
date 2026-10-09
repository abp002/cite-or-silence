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

## Checking the checker

The bench judge grades every answer sentence as supported, unbacked or contradicted by the SEP. Before
trusting its numbers, 100 of its grades were drawn (stratified by label, half from
codex:gpt-6-luna:low, half from ollama:qwen3:14b) and reviewed again, blind.

**A second model** (Claude Opus 5.5) agreed with 65 of 70 "supported" grades and 17 of 29
"unbacked" ones. Where they differ, the judge is the lenient one: it passes sentences that keep the
gist of a passage but drop who said it ("possible worlds are…" for what the passage gives as Leibniz's
view) or widen its scope ("contemporary feminists" for "pragmatist and continental feminists").

**A human without philosophy training** reviewed 20 of them and accepted 19, including five that
both the judge and the second model rejected.
Where a sentence came with a citation, the citation looked right, and it was: the model had found
the right passage and then stretched it when writing the sentence.

So showing the reader a citation is not enough: a correct quote under a sentence it does not support
reads as proof. That is what verification is for. Run on the 64 reviewed sentences that carried a
quote, the verification judge (codex:gpt-6-luna:low) dropped 4–5 of the 6 the second model found
unbacked and wrongly dropped 7 of 53 that both reviewers found supported.
A stricter verification prompt (also reject dropped attributions, widened scope, reversed
explanations) caught no more bad sentences and dropped 12 good ones, so it was not adopted.
`scripts/verifier_cases.py` reruns this check.

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
