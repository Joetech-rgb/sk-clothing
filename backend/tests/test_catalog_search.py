import pytest

from apps.catalog.search import MAX_PAGE_SIZE, MAX_QUERY_CHARS, SearchRequest, normalise_query


def test_queries_are_trimmed_and_spaces_collapsed():
    assert normalise_query("  kente   shirt \t men ") == "kente shirt men"


def test_control_characters_are_removed():
    assert normalise_query("kente\x00shirt\x1b[31m") == "kente shirt [31m"
    assert normalise_query("line1\nline2") == "line1 line2"


def test_queries_are_capped_in_length():
    assert len(normalise_query("a" * 5000)) == MAX_QUERY_CHARS
    assert normalise_query("") == "" and normalise_query("   ") == ""


def test_requests_are_validated():
    assert SearchRequest("shirt").limit == 24
    for bad in (0, -1, MAX_PAGE_SIZE + 1):
        with pytest.raises(ValueError):
            SearchRequest("shirt", limit=bad)
    with pytest.raises(ValueError):
        SearchRequest("shirt", sort="random")
