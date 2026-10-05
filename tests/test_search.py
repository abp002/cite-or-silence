import numpy as np

from cite_or_silence.search import build_index, bm25, connect, dense, rrf, search


def test_rrf_rewards_agreement_over_a_single_top_spot():
    # b is second in both rankings; a and c are each first in only one.
    assert rrf([["a", "b"], ["c", "b"]])[0] == "b"


def test_rrf_scores_by_position_only():
    # a: 1/61 + 1/63 = 0.032266, b: 1/62 + 1/62 = 0.032258, c: 1/61, d: 1/63
    assert rrf([["a", "b", "d"], ["c", "b", "a"]]) == ["a", "b", "c", "d"]


def chunk(cid, heading, text):
    entry, rest = cid.split("#")
    return {"id": cid, "entry": entry, "section": "1", "heading": heading, "text": text}


def test_index_answers_both_kinds_of_search(tmp_path):
    # Invented text: nothing from the SEP goes into tests.
    chunks = [
        chunk("x#One:0", "Moons", "Lunar tides follow the moon around the planet."),
        chunk("x#Two:0", "Bread", "Bakers knead dough before it rises."),
        chunk("y#Three:0", "Rivers", "Water runs downhill towards the sea."),
    ]
    vectors = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)
    con = connect(tmp_path / "t.duckdb")
    build_index(con, chunks, vectors)

    assert dense(con, np.array([0.1, 0.9, 0.2]), 2) == ["x#Two:0", "y#Three:0"]
    assert bm25(con, "¿Qué hacen las tides?", 5) == ["x#One:0"]  # english stemming: tides -> tide
    assert search(con, "dough", np.array([0, 0, 1.0]), "hybrid", 2) == ["x#Two:0", "y#Three:0"]
