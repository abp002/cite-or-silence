"""The fixture mimics SEP markup with invented text: no SEP content lives in this repo."""

from cite_or_silence.chunk import MAX_WORDS, MIN_WORDS, chunk_entry, parse_entry, section_chunks, split_heading
from cite_or_silence.fetch import entry_slugs


def words(n: int, word: str = "lorem") -> str:
    return " ".join([word] * n)


ENTRY = f"""
<html><body><div id="aueditable">
<h1>Imaginary Ethics</h1>
<div id="preamble"><p>{words(70, "intro")}</p></div>
<div id="toc"><ul><li><a href="#One">1. First Things</a></li></ul></div>
<div id="main-text">
<h2 id="One">1. First Things</h2>
<p>{words(70, "alpha")}<sup>[<a href="notes.html#1">1</a>]</sup></p>
<h3 id="OneTwo">1.2 A Subsection</h3>
<ul><li><p>{words(30, "nested")}</p></li></ul>
<p>{words(40, "beta")}</p>
<h2 id="Two">2. Second Things</h2>
<p>{words(10, "tiny")}</p>
</div>
<div id="bibliography"><h2 id="Bib">Bibliography</h2><p>{words(80, "biblio")}</p></div>
</div></body></html>
"""


def test_heading_number_is_split_from_title():
    assert split_heading("4.1 The  Humanity\nFormula") == ("4.1", "The Humanity Formula")
    assert split_heading("4. Categorical Imperatives") == ("4", "Categorical Imperatives")
    assert split_heading("Bibliography") == (None, "Bibliography")


def test_sections_keep_number_anchor_and_skip_toc_and_bibliography():
    title, sections = parse_entry(ENTRY)
    assert title == "Imaginary Ethics"
    assert [(s.number, s.anchor) for s in sections] == [(None, None), ("1", "One"), ("1.2", "OneTwo"), ("2", "Two")]


def test_nested_paragraph_is_read_once_and_footnotes_dropped():
    _, sections = parse_entry(ENTRY)
    sub = sections[2]
    assert sub.paragraphs == [words(30, "nested"), words(40, "beta")]
    assert "[1]" not in sections[1].paragraphs[0]


def test_chunk_ids_and_urls_point_to_the_section():
    chunks = chunk_entry("imaginary-ethics", ENTRY)
    assert [c.id for c in chunks] == [
        "imaginary-ethics#preamble:0",
        "imaginary-ethics#One:0",
        "imaginary-ethics#OneTwo:0",
        "imaginary-ethics#Two:0",
    ]
    assert chunks[0].url == "https://plato.stanford.edu/entries/imaginary-ethics/"
    assert chunks[2].url == "https://plato.stanford.edu/entries/imaginary-ethics/#OneTwo"
    assert chunks[2].section == "1.2"


def test_short_paragraphs_merge_within_a_section():
    assert section_chunks([words(20), words(20), words(30)]) == [words(70)]


def test_short_tail_joins_previous_chunk():
    assert section_chunks([words(MIN_WORDS), words(5)]) == [words(MIN_WORDS + 5)]


def test_long_paragraph_splits_on_sentences_without_losing_text():
    sentence = words(49) + " end."
    paragraph = " ".join([sentence.capitalize()] * 10)  # 500 words
    pieces = section_chunks([paragraph])
    assert len(pieces) > 1
    assert all(len(p.split()) <= MAX_WORDS for p in pieces)
    assert " ".join(pieces) == paragraph


def test_entry_slugs_dedupe_in_order():
    html = '<a href="entries/kant/">x</a><a href="entries/abduction/">y</a><a href="entries/kant/#2">z</a>'
    assert entry_slugs(html) == ["kant", "abduction"]
