"""Regression: "sort of"/"kind of" as nouns are not speech fillers (sweep 02:35 IST)."""
from backend.project_copy import _FILLERS
from backend.project_copy import looks_like_raw_transcript as copy_raw
from backend.project_enrich import _FILLER_RE
from backend.project_planner import _looks_like_raw_prose, looks_like_raw_transcript

TOPO = ("A topological sort of the graph lets us traverse nodes in forward order. "
        "We'll write a helper to collect nodes for later backprop.")


def test_noun_sort_of_is_not_filler():
    assert not _looks_like_raw_prose(TOPO)
    assert not looks_like_raw_transcript(TOPO)
    assert not copy_raw(TOPO)
    assert not _looks_like_raw_prose("What kind of data does a Value node hold? Each kind of op has a backward rule.")
    assert _FILLERS.findall("a merge sort of the list and a different kind of node") == []
    assert "topological sort of the graph" in _FILLER_RE.sub("", TOPO)


def test_hedge_sort_of_is_still_filler():
    assert _looks_like_raw_prose("so it's sort of like a list of numbers and we add them up.")
    assert _looks_like_raw_prose("We kind of just multiply the gradients together here.")
    assert len(_FILLERS.findall("it's kind of neat and we sort of add them")) == 2
