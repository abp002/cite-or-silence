from cite_or_silence.answer import Answer, Passage
from cite_or_silence.verify import SILENCE, Sentence, quote_in, verify

# Invented passages: nothing from the SEP goes into tests.
PASSAGES = [
    "The lighthouse keeper argued that “every storm teaches patience” to those who wait.",
    "Gardeners in the valley believed that frost was a messenger of the northern hills.",
]


class Judge:
    """Says yes to the claims it is told to, and records what it was asked."""

    name = "fake"

    def __init__(self, yes=()):
        self.yes, self.prompts = set(yes), []

    def complete(self, prompt, schema):
        self.prompts.append(prompt)
        numbers = [int(line[1:-1]) for line in prompt.splitlines() if line.startswith("[") and line.endswith("]")]
        return {"verdicts": [{"n": n, "supported": n in self.yes} for n in numbers]}


def test_quote_survives_typographic_differences():
    assert quote_in('argued that "every storm teaches patience" to those', PASSAGES[0])
    assert quote_in("The  lighthouse keeper ARGUED that", PASSAGES[0])


def test_quote_must_be_in_the_passage_and_long_enough():
    assert not quote_in("every storm teaches courage to those", PASSAGES[0])  # paraphrase
    assert not quote_in("argued that ... to those who wait", PASSAGES[0])  # ellipsis
    assert not quote_in("lighthouse keeper", PASSAGES[0])  # too short to back a claim


def test_each_check_drops_its_own_sentence():
    sentences = [
        Sentence("El farero pedía paciencia.", 1, "every storm teaches patience” to those who wait"),
        Sentence("La escarcha venía del norte.", 2, "frost was a messenger of the southern sea"),
        Sentence("Citaba un pasaje inexistente.", 3, "every storm teaches patience to those"),
        Sentence("Los jardineros temían al sol.", 2, "believed that frost was a messenger"),
    ]
    judge = Judge(yes={1})
    verify(sentences, PASSAGES, judge)
    assert [s.dropped for s in sentences] == [
        None,
        "quote not found in the cited passage",
        "cites a passage that was not given",
        "quote does not support the sentence",
    ]
    # only sentences with a real quote reach the judge, in one call
    assert len(judge.prompts) == 1 and "[1]" in judge.prompts[0] and "[4]" in judge.prompts[0]
    assert "[2]" not in judge.prompts[0]


def test_nothing_left_means_silence_and_the_judge_is_not_called():
    judge = Judge()
    sentences = verify([Sentence("Inventado.", 1, "the keeper sailed to the moon at night")], PASSAGES, judge)
    passages = [Passage("x#a:0", "x", "a", "A", PASSAGES[0])]
    assert judge.prompts == []
    assert Answer("¿?", passages, sentences).render() == SILENCE


def test_render_links_only_the_cited_passages():
    passages = [Passage("x#preamble:0", "x", "preamble", "Preamble", PASSAGES[0]),
                Passage("y#Fro:0", "y", "Fro", "Frost", PASSAGES[1])]
    answer = Answer("¿?", passages, [Sentence("La escarcha es mensajera.", 2, "frost was a messenger of the")])
    assert answer.render() == "La escarcha es mensajera. [2]\n\n[2] https://plato.stanford.edu/entries/y/#Fro"
