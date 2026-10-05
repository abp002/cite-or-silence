from cite_or_silence.evaluate import Section, by_type, covers, entry_recall, recall


def s(entry, anchor, number):
    return Section(entry, anchor, number)


def test_subsection_covers_its_section_but_not_lookalike_numbers():
    gold = s("x", "Three", "3")
    assert covers(gold, s("x", "ThreeTwo", "3.2"))
    assert not covers(gold, s("x", "ThirtyOne", "31.1"))
    assert not covers(gold, s("y", "ThreeTwo", "3.2"))  # same numbering, other entry


def test_preamble_is_only_covered_by_the_preamble():
    gold = s("x", "preamble", None)
    assert covers(gold, s("x", "preamble", None))
    assert not covers(gold, s("x", "One", "1"))


def test_recall_counts_gold_sections_found():
    gold = [s("x", "One", "1"), s("y", "Two", "2")]
    retrieved = [s("x", "OneOne", "1.1"), s("y", "Five", "5"), s("x", "One", "1")]
    assert recall(gold, retrieved) == 0.5
    assert entry_recall(gold, retrieved) == 1.0


def test_by_type_adds_an_overall_row():
    assert by_type([("single", 1.0), ("multi", 0.5), ("single", 0.0)]) == {
        "single": (2, 0.5),
        "multi": (1, 0.5),
        "all": (3, 0.5),
    }
