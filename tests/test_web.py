import json
import re

from cite_or_silence.answer import Passage
from cite_or_silence.web import EXAMPLES, Retrieval, Session, export, steps

# Invented passages: nothing from the SEP goes into tests.
PASSAGES = [
    Passage("keepers#doubt:0", "keepers", "doubt", "Doubt", "The lighthouse keeper argued that “every storm teaches patience” to those who wait."),
    Passage("gardens#frost:0", "gardens", "frost", "Frost", "Gardeners in the valley believed that frost was a messenger of the northern hills."),
]
LEFT_OUT = Passage("keepers#lamp:0", "keepers", "lamp", "Lamp", "The lamp was trimmed at dusk by whoever kept the tower.")


def found(question=""):
    """The search for any question: three candidates, the second left out by the cap."""
    candidates = [(PASSAGES[0], 0.71, "kept"), (LEFT_OUT, 0.66, "capped"), (PASSAGES[1], 0.6123, "kept")]
    return Retrieval(PASSAGES, [0.5] * 1024, candidates)


class Model:
    """Drafts the sentences it is given and, as judge, backs only the claims it is told to."""

    name = "fake"

    def __init__(self, sentences, backed=()):
        self.sentences, self.backed, self.judged = sentences, set(backed), 0

    def complete(self, prompt, schema):
        if "verdicts" not in schema["properties"]:
            return {"sentences": self.sentences}
        self.judged += 1
        numbers = [int(line[1:-1]) for line in prompt.splitlines() if line.startswith("[") and line.endswith("]")]
        return {"verdicts": [{"n": n, "supported": n in self.backed} for n in numbers]}


def run(model):
    return list(steps("¿Qué enseñan las tormentas?", found, model, lambda p: {"title": p.entry}))


def test_the_page_learns_which_sentences_survive_in_draft_order():
    model = Model(
        [
            {"text": "Las tormentas enseñan paciencia.", "source": 1, "quote": 'argued that "every storm teaches patience" to those who wait'},
            {"text": "La escarcha anuncia la primavera.", "source": 2, "quote": "frost was a messenger of the northern hills"},
            {"text": "El farero inventó el faro.", "source": 1, "quote": "the keeper built the first lighthouse himself"},
        ],
        backed={1},
    )
    events = dict(run(model))
    assert [name for name, _ in run(Model([]))] == ["pool", "passages", "draft", "verdicts", "done"]
    assert events["passages"] == {"passages": [{"title": "keepers"}, {"title": "gardens"}]}
    assert [s["text"] for s in events["draft"]["sentences"]] == [
        "Las tormentas enseñan paciencia.",
        "La escarcha anuncia la primavera.",
        "El farero inventó el faro.",
    ]
    assert events["verdicts"] == {
        "dropped": [None, "quote does not support the sentence", "quote not found in the cited passage"]
    }
    assert events["done"] == {"silent": False}


def test_an_empty_draft_is_silence_without_asking_the_judge():
    model = Model([])
    events = dict(run(model))
    assert events["draft"] == {"sentences": []}
    assert events["done"] == {"silent": True}
    assert model.judged == 0


def test_silence_when_every_sentence_is_struck():
    model = Model([{"text": "La escarcha anuncia la primavera.", "source": 2, "quote": "frost was a messenger of the northern hills"}])
    assert dict(run(model))["done"] == {"silent": True}


def test_the_pool_shows_every_candidate_its_similarity_and_fate():
    pool = dict(run(Model([])))["pool"]
    assert pool["dims"] == 1024 and len(pool["head"]) == 48 and pool["cap"] == 2
    assert pool["candidates"] == [
        {"title": "keepers", "score": 0.71, "fate": "kept"},
        {"title": "keepers", "score": 0.66, "fate": "capped"},
        {"title": "gardens", "score": 0.612, "fate": "kept"},
    ]


def test_an_answer_saved_without_its_pool_gets_one_on_replay_without_the_model(tmp_path):
    saved = tmp_path / "answers.json"
    old = [["passages", {"passages": [{"title": "keepers"}, {"title": "gardens"}]}], ["draft", {"sentences": []}], ["verdicts", {"dropped": []}], ["done", {"silent": True}]]
    saved.write_text(json.dumps({"¿Qué enseñan las tormentas?": old}))

    class Unreachable:
        name = "unreachable"

        def complete(self, prompt, schema):
            raise AssertionError("only the search should run again")

    replayed = list(Session(found, Unreachable(), lambda p: {"title": p.entry}, saved).ask("¿Qué enseñan las tormentas?"))
    assert [name for name, _ in replayed] == ["pool", "passages", "draft", "verdicts", "done"]
    assert replayed[1:] == [tuple(e) for e in old]
    assert [name for name, _ in json.loads(saved.read_text())["¿Qué enseñan las tormentas?"]][0] == "pool"


def test_a_saved_answer_replays_in_a_new_session_without_the_model(tmp_path):
    saved = tmp_path / "answers.json"
    first = Model([{"text": "Las tormentas enseñan paciencia.", "source": 1, "quote": 'argued that "every storm teaches patience" to those who wait'}], backed={1})
    asked = list(Session(found, first, lambda p: {"title": p.entry}, saved).ask("¿Qué  enseñan las tormentas?"))

    class Unreachable:
        name = "unreachable"

        def complete(self, prompt, schema):
            raise AssertionError("the saved answer should have been replayed")

    again = Session(lambda q: [], Unreachable(), lambda p: {}, saved)
    assert list(again.ask("¿Qué enseñan las tormentas?")) == asked


def test_the_public_demo_publishes_no_quote_and_fills_every_placeholder(tmp_path):
    quote = 'argued that "every storm teaches patience" to those who wait'
    model = Model([{"text": "Las tormentas enseñan paciencia.", "source": 1, "quote": quote}], backed={1})
    describe = lambda p: {"title": p.entry, "url": f"https://plato.stanford.edu/entries/{p.entry}/#{p.anchor}"}
    session = Session(found, model, describe)
    n = export(session, tmp_path / "site", {"MODEL": "fake", "ENTRIES": "2", "PASSAGES": "2"})

    assert n == sum(len(qs) for qs in EXAMPLES.values())
    published = "".join(f.read_text() for f in (tmp_path / "site").rglob("*") if f.is_file())
    assert "every storm teaches patience" not in published
    for passage in [*PASSAGES, LEFT_OUT]:
        assert passage.text not in published
    page = (tmp_path / "site" / "index.html").read_text()
    assert 'data-mode="public"' in page
    assert re.search(r"__[A-Z]+__", page) is None
    answers = json.loads((tmp_path / "site" / "answers.json").read_text())
    draft = dict(answers[EXAMPLES["es"][0]])["draft"]
    assert draft == {"sentences": [{"text": "Las tormentas enseñan paciencia.", "source": 1}]}
