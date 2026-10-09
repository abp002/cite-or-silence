# cite-or-silence

Ask a philosophy question, get an answer built only from the
[Stanford Encyclopedia of Philosophy](https://plato.stanford.edu/). Every sentence links to the exact
section it comes from, every citation is checked by machine, and if the SEP doesn't cover the
question, the answer is **"I don't know."** Questions can be asked in Spanish; the SEP is in English.

Without retrieval, a third of what a model says about philosophy is not in the SEP. With retrieval
and verification, almost nothing is (see [Results](#results), and [where it fails](#where-it-fails)).

## What gets measured

| Metric | Question it answers |
|---|---|
| Recall@5 | Did retrieval find the right section? |
| Citation precision | Does each citation support its sentence? |
| Faithfulness | Does the answer stay inside what it cites? |
| Refusal accuracy | Does it say "I don't know" when it should? |

The headline is a comparison: the same model without retrieval versus with retrieval and citation
checking.

## Results

101 questions written before the retrieval system existed: 81 answerable from the SEP (51 from one
entry, 30 needing several), 15 it does not cover and 5 resting on a false premise. Each model answers
three ways: **bare** (from memory), **rag** (from ten retrieved passages, before verification) and
**verified** (what survives the citation check). The judge is the same model that answers, grading
the three arms blind against the gold sections plus the retrieved passages.

| | codex:gpt-6-luna:low | | | ollama:qwen3:14b | | |
|---|---:|---:|---:|---:|---:|---:|
| | **bare** | **rag** | **verified** | **bare** | **rag** | **verified** |
| Sentences supported by the SEP | 66 % | 99 % | **100 %** | 59 % | 93 % | **96 %** |
| Sentences unbacked | 33 % | 1 % | **0 %** | 39 % | 5 % | **3 %** |
| Sentences contradicted | 1 % | 1 % | 0 % | 1 % | 1 % | 1 % |
| Answerable questions left silent | 0 % | 1 % | 7 % | 54 % | 1 % | 1 % |
| Not-in-the-SEP questions declined (15) | 80 % | 100 % | 100 % | 93 % | 100 % | 100 % |
| False premises corrected (5) | 5/5 | 1/5 | 0/5 | 0/5 | 0/5 | 0/5 |

Sentence shares are over answerable questions. The judge is lenient (next section), so the supported
rates are upper bounds; the gap between bare and verified is the finding, not the exact percentages.

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

## Where it fails

- **False premises.** A sentence such as "the premise is wrong" has no passage to quote, so
  verification drops it. Codex from memory corrected all 5 false premises; verified, it corrects none.
- **Spanish questions, English encyclopedia.** Retrieval puts a gold section in the top 5 for 51 % of
  questions (30 % when the answer spans several entries), though the right entry is there 80 % of
  the time. Verified answers cite the gold section in 30 % (codex) and 51 % (qwen) of questions:
  most answers are backed, but by a neighbouring section rather than the one the question was
  written for.
- **Silence has a cost.** The verifier drops about 1 in 8 sentences that reviewers found supported
  (see above), and verified codex answers nothing at all on 7 % of answerable questions.
- **The judge is the answering model**, and it lets through sentences that drop who holds a view or
  widen its scope. Numbers from a different judge may be lower across the board.
- **Small set.** 101 questions; the false-premise row rests on five.

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
