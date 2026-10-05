from cite_or_silence.questions import check

ENTRY = '<h1>X</h1><div id="main-text"><h2 id="One">1. One</h2><p>text</p></div>'


def q(qid, type_, gold):
    return {"id": qid, "type": type_, "question": "?", "gold": gold}


def test_ready_set_has_no_problems(tmp_path):
    (tmp_path / "x.html").write_text(ENTRY)
    (tmp_path / "y.html").write_text(ENTRY)
    good = [
        q("s1", "single", [{"entry": "x", "anchor": "One"}]),
        q("m1", "multi", [{"entry": "x", "anchor": "One"}, {"entry": "y", "anchor": "One"}]),
        q("n1", "none", []),
    ]
    assert check(good, tmp_path) == []


def test_each_broken_rule_is_reported(tmp_path):
    (tmp_path / "x.html").write_text(ENTRY)
    bad = [
        q("s1", "single", [{"entry": "x", "anchor": "Nope"}]),
        q("s1", "single", [{"entry": "x", "anchor": None}]),
        q("m1", "multi", [{"entry": "x", "anchor": "One"}, {"entry": "x", "anchor": "One"}]),
        q("n1", "none", [{"entry": "x", "anchor": "One"}]),
        q("f1", "false_premise", [{"entry": "missing", "anchor": "One"}]),
    ]
    assert check(bad, tmp_path) == [
        "s1: anchor Nope not found in x",
        "s1: duplicate id",
        "s1: no anchor chosen in x",
        "m1: 'multi' needs at least two entries",
        "n1: only 'none' questions have no gold",
        "f1: entry missing not downloaded",
    ]
