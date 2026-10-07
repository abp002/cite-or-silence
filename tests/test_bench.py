from cite_or_silence.bench import ARMS, apply_grades, judge_request, letters


def q(qtype, qid="x1"):
    return {"id": qid, "type": qtype, "question": "¿?", "gold": []}


def test_letters_are_shuffled_but_stable():
    assert letters("s01") == letters("s01")
    assert sorted(letters("s01").values()) == ["A", "B", "C"]
    assert len({tuple(letters(f"s{n:02d}").items()) for n in range(20)}) > 1  # not always the same order


def test_none_question_empty_answer_abstains_and_judge_decides_the_rest():
    texts = {"bare": ["Valcárcel defendía el ser liminal."], "rag": ["No consta."], "verified": []}
    L = letters("x1")
    grades = [{"answer": L["bare"], "abstains": False}, {"answer": L["rag"], "abstains": True}]
    s = apply_grades(q("none"), texts, grades)
    assert (s["bare"]["abstains"], s["rag"]["abstains"], s["verified"]["abstains"]) == (False, True, True)


def test_false_premise_silence_corrects_nothing():
    texts = {"bare": ["Kant no era utilitarista."], "rag": [], "verified": []}
    s = apply_grades(q("false_premise"), texts, [{"answer": letters("x1")["bare"], "corrects": True}])
    assert [s[a]["corrects"] for a in ARMS] == [True, False, False]
    assert s["rag"]["silent"]


def test_sentence_labels_map_back_to_their_arm_and_ungraded_ones_count_as_unbacked():
    texts = {"bare": ["uno", "dos"], "rag": ["tres"], "verified": []}
    L = letters("x1")
    grades = [
        {"sentence": f"{L['bare']}1", "label": "supported"},
        {"sentence": f"{L['bare']}2", "label": "contradicted"},
    ]  # the rag sentence was skipped by the judge
    s = apply_grades(q("single"), texts, grades)
    assert s["bare"] == {"silent": False, "sentences": 2, "supported": 1, "contradicted": 1, "unbacked": 0}
    assert s["rag"]["unbacked"] == 1 and s["verified"]["silent"]


def test_judge_only_sees_letters_never_arm_names():
    texts = {"bare": ["uno"], "rag": ["dos"], "verified": ["dos"]}
    prompt, schema = judge_request(q("single"), texts, [])
    assert not any(arm in prompt for arm in ARMS)
    ids = schema["properties"]["grades"]["items"]["properties"]["sentence"]["enum"]
    assert sorted(ids) == ["A1", "B1", "C1"]
