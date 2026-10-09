from cite_or_silence.answer import Passage
from cite_or_silence.web import Session, steps

# Invented passages: nothing from the SEP goes into tests.
PASSAGES = [
    Passage("keepers#doubt:0", "keepers", "doubt", "Doubt", "The lighthouse keeper argued that “every storm teaches patience” to those who wait."),
    Passage("gardens#frost:0", "gardens", "frost", "Frost", "Gardeners in the valley believed that frost was a messenger of the northern hills."),
]


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
    return list(steps("¿Qué enseñan las tormentas?", lambda q: PASSAGES, model, lambda p: {"title": p.entry}))


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
    assert [name for name, _ in run(Model([]))] == ["passages", "draft", "verdicts", "done"]
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


def test_a_saved_answer_replays_in_a_new_session_without_the_model(tmp_path):
    saved = tmp_path / "answers.json"
    first = Model([{"text": "Las tormentas enseñan paciencia.", "source": 1, "quote": 'argued that "every storm teaches patience" to those who wait'}], backed={1})
    asked = list(Session(lambda q: PASSAGES, first, lambda p: {"title": p.entry}, saved).ask("¿Qué  enseñan las tormentas?"))

    class Unreachable:
        name = "unreachable"

        def complete(self, prompt, schema):
            raise AssertionError("the saved answer should have been replayed")

    again = Session(lambda q: [], Unreachable(), lambda p: {}, saved)
    assert list(again.ask("¿Qué enseñan las tormentas?")) == asked
