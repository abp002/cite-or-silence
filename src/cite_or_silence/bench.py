"""The headline comparison: the same model with no retrieval, with retrieval, and with retrieval
plus verification, over the whole question set. Scoring rules were fixed before the first run.

Three arms per question:
- bare: the model alone, from memory;
- rag: the model with the ten retrieved passages, before verification;
- verified: what survives verification (silence if nothing does).
All three may return an empty list when they don't know, so silence is open to every arm.

A judge sees the arms under shuffled letters, so it cannot favour one, and grades:
- none: did the arm abstain (an empty answer abstains without asking the judge);
- false_premise: did the arm reject the false premise;
- single / multi: each sentence against one reference shared by all arms (the gold sections plus
  the retrieved passages): supported, contradicted, or unbacked (the reference says nothing).
The judge is the same model that answers; the README says so.

Results go to data/bench/<provider>/<qid>.json (gitignored: they hold SEP quotes) and the run
resumes from the questions already there.
"""

import json
import random
from collections.abc import Callable
from pathlib import Path

import duckdb

from cite_or_silence import evaluate
from cite_or_silence.answer import Passage, answer
from cite_or_silence.provider import Provider

ARMS = ("bare", "rag", "verified")
LABELS = ("supported", "contradicted", "unbacked")

BARE_SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "items": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
        }
    },
    "required": ["sentences"],
    "additionalProperties": False,
}


def bare_prompt(question: str) -> str:
    return (
        "Answer the philosophy question from what you know, in the language of the question, as a "
        "list of short sentences. If you do not know, or what the question asks about does not exist, "
        "return an empty list. If the question rests on a false premise, correct it.\n\n"
        f"QUESTION: {question}"
    )


def gold_text(con: duckdb.DuckDBPyConnection, gold: list[dict]) -> list[Passage]:
    """Every chunk of each gold section and its subsections, in document order."""
    out = []
    for g in gold:
        number = con.execute(
            "SELECT any_value(section) FROM chunks WHERE entry = ? AND anchor = ?", [g["entry"], g["anchor"]]
        ).fetchone()[0]
        rows = con.execute(
            """SELECT id, entry, anchor, heading, text FROM chunks
               WHERE entry = ? AND (anchor = ? OR (? IS NOT NULL AND section LIKE ? || '.%'))
               ORDER BY rowid""",
            [g["entry"], g["anchor"], number, number],
        ).fetchall()
        out += [Passage(*r) for r in rows]
    return out


def letters(qid: str) -> dict[str, str]:
    """arm -> letter, shuffled per question but the same on every rerun."""
    shuffled = list(ARMS)
    random.Random(qid).shuffle(shuffled)
    return {arm: "ABC"[i] for i, arm in enumerate(shuffled)}


def _schema(item: dict) -> dict:
    return {"type": "object", "properties": item, "required": list(item), "additionalProperties": False}


def judge_request(q: dict, texts: dict[str, list[str]], reference: list[Passage]) -> tuple[str, dict]:
    """Prompt and schema for grading every arm of one question in one call."""
    to_letter = letters(q["id"])
    order = sorted(ARMS, key=lambda a: to_letter[a])
    answers = "\n\n".join(
        f"ANSWER {to_letter[a]}:\n" + ("\n".join(f"{to_letter[a]}{n}. {t}" for n, t in enumerate(texts[a], 1)) or "(empty)")
        for a in order
    )
    if q["type"] == "none":
        task = ("The question asks about something that does not exist or that the encyclopedia does not "
                "cover. For each answer, 'abstains' is true if it declines, says it does not know, or says "
                "the thing does not exist, without inventing content about it.")  # fmt: skip
        item = {"answer": {"type": "string", "enum": list("ABC")}, "abstains": {"type": "boolean"}}
        return f"{task}\n\nQUESTION: {q['question']}\n\n{answers}", _schema({"grades": {"type": "array", "items": _schema(item)}})
    ref = "\n\n".join(f"[{p.entry} — {p.heading}]\n{p.text}" for p in reference)
    if q["type"] == "false_premise":
        task = ("The question rests on a false premise; the reference shows what is true. For each answer, "
                "'corrects' is true if it explicitly rejects the false premise.")  # fmt: skip
        item = {"answer": {"type": "string", "enum": list("ABC")}, "corrects": {"type": "boolean"}}
    else:
        task = ("Grade every numbered sentence of every answer against the REFERENCE only, not your own "
                "knowledge: 'supported' if the reference states or directly implies it, 'contradicted' if the "
                "reference says otherwise, 'unbacked' if the reference does not settle it.")  # fmt: skip
        ids = [f"{to_letter[a]}{n}" for a in order for n in range(1, len(texts[a]) + 1)]
        item = {"sentence": {"type": "string", "enum": ids or ["none"]}, "label": {"type": "string", "enum": list(LABELS)}}
    return (f"{task}\n\nREFERENCE\n\n{ref}\n\nQUESTION: {q['question']}\n\n{answers}",
            _schema({"grades": {"type": "array", "items": _schema(item)}}))  # fmt: skip


def apply_grades(q: dict, texts: dict[str, list[str]], grades: list[dict]) -> dict[str, dict]:
    """Judge output -> per-arm scores. Ids the judge skips count against the arm."""
    to_arm = {letter: arm for arm, letter in letters(q["id"]).items()}
    scores: dict[str, dict] = {}
    if q["type"] in ("none", "false_premise"):
        key = "abstains" if q["type"] == "none" else "corrects"
        verdicts = {to_arm.get(g["answer"]): g[key] for g in grades}
        for arm in ARMS:
            silent = not texts[arm]
            # an empty answer abstains on a 'none' question and corrects nothing on a false premise
            ok = silent if q["type"] == "none" and silent else bool(verdicts.get(arm, False))
            scores[arm] = {"silent": silent, key: ok}
        return scores
    labels: dict[tuple[str, int], str] = {}
    for g in grades:
        sid = g["sentence"]
        if sid[:1] in to_arm and sid[1:].isdigit():
            labels[to_arm[sid[0]], int(sid[1:])] = g["label"]
    for arm in ARMS:
        counts = dict.fromkeys(LABELS, 0)
        for n in range(1, len(texts[arm]) + 1):
            counts[labels.get((arm, n), "unbacked")] += 1
        scores[arm] = {"silent": not texts[arm], "sentences": len(texts[arm]), **counts}
    return scores


def run_one(con, q: dict, retrieve: Callable[[str], list[Passage]], model: Provider) -> dict:
    passages = retrieve(q["question"])
    bare = [s["text"] for s in model.complete(bare_prompt(q["question"]), BARE_SCHEMA)["sentences"]]
    result = answer(q["question"], passages, model, model)
    texts = {"bare": bare, "rag": [s.text for s in result.sentences], "verified": [s.text for s in result.kept]}
    reference = gold_text(con, q["gold"]) + passages if q["gold"] else []
    if q["type"] == "none" and not any(texts.values()):
        grades = []  # nothing to judge: every arm abstained
    else:
        prompt, schema = judge_request(q, texts, reference)
        grades = model.complete(prompt, schema)["grades"]
    scores = apply_grades(q, texts, grades)
    cited = [result.passages[s.source - 1] for s in result.kept]
    if q["gold"]:
        gold = [evaluate.Section(g["entry"], g["anchor"], _number(con, g)) for g in q["gold"]]
        got = [evaluate.Section(p.entry, p.anchor, _number(con, {"entry": p.entry, "anchor": p.anchor})) for p in cited]
        scores["verified"]["gold_cited"] = evaluate.recall(gold, got)
    return {
        "id": q["id"], "type": q["type"], "question": q["question"], "provider": model.name,
        "texts": texts, "scores": scores, "grades": grades,
        "sentences": [s.__dict__ for s in result.sentences], "passages": [p.id for p in passages],
    }  # fmt: skip


def _number(con, g: dict) -> str | None:
    return con.execute(
        "SELECT any_value(section) FROM chunks WHERE entry = ? AND anchor = ?", [g["entry"], g["anchor"]]
    ).fetchone()[0]


def report(results: list[dict]) -> str:
    def share(xs):
        return f"{sum(xs) / len(xs):.2f}" if xs else "-"

    lines = [f"{'':<34}" + "".join(f"{a:>10}" for a in ARMS)]

    def row(label, values):
        lines.append(f"{label:<34}" + "".join(f"{v:>10}" for v in values))

    by = {t: [r for r in results if r["type"] == t] for t in ("none", "false_premise", "single", "multi")}
    row(f"none: abstains (n={len(by['none'])})", [share([r["scores"][a]["abstains"] for r in by["none"]]) for a in ARMS])
    fp = by["false_premise"]
    row(f"false premise: corrects (n={len(fp)})", [share([r["scores"][a]["corrects"] for r in fp]) for a in ARMS])
    answerable = by["single"] + by["multi"]
    row(f"answerable: silent (n={len(answerable)})", [share([r["scores"][a]["silent"] for r in answerable]) for a in ARMS])
    for label in LABELS:
        values = []
        for a in ARMS:
            total = sum(r["scores"][a]["sentences"] for r in answerable)
            values.append(f"{sum(r['scores'][a][label] for r in answerable) / total:.2f}" if total else "-")
        row(f"  sentences {label}", values)
    row("  sentences per answer", [f"{sum(r['scores'][a]['sentences'] for r in answerable) / max(len(answerable), 1):.1f}" for a in ARMS])
    lines.append(f"\ngold section cited (verified): {share([r['scores']['verified']['gold_cited'] for r in answerable])}")
    return "\n".join(lines)


def run(con, questions: list[dict], retrieve, model: Provider, out_dir: Path, limit: int | None = None, log=print) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = [q for q in questions if not (out_dir / f"{q['id']}.json").exists()][:limit]
    for n, q in enumerate(todo, 1):
        try:
            result = run_one(con, q, retrieve, model)
        except Exception as e:  # one failed call should not stop a run of hundreds; rerun picks it up
            log(f"[{n}/{len(todo)}] {q['id']} FAILED: {e}")
            continue
        (out_dir / f"{q['id']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
        log(f"[{n}/{len(todo)}] {q['id']} done")
    return [json.loads(p.read_text()) for p in sorted(out_dir.glob("*.json"))]
