import json

import pytest

from cite_or_silence.query import rewrite


class Echo:
    name = "echo"

    def __init__(self, drop: int = 0):
        self.calls, self.drop = [], drop

    def complete(self, prompt, schema):
        asked = [line.split(". ", 1)[1] for line in prompt.split("\n\n")[-1].splitlines()]
        self.calls.append(asked)
        return {"translations": [f"EN {q}" for q in asked][: len(asked) - self.drop]}


def test_only_questions_missing_from_the_cache_reach_the_model(tmp_path):
    cache = tmp_path / "t.json"
    cache.write_text(json.dumps({"¿uno?": "one?"}))
    model = Echo()
    assert rewrite(["¿uno?", "¿dos?", "¿uno?"], model, cache) == ["one?", "EN ¿dos?", "one?"]
    assert model.calls == [["¿dos?"]]
    assert json.loads(cache.read_text())["¿dos?"] == "EN ¿dos?"


def test_a_short_batch_fails_instead_of_pairing_questions_with_the_wrong_translation():
    with pytest.raises(RuntimeError):
        rewrite(["¿uno?", "¿dos?"], Echo(drop=1))
