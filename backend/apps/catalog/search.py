"""The search interface (CLAUDE.md section 6). Pure Python.

Phase 1A implements it with PostgreSQL full-text search and trigram matching. Phase 1B replaces it
with Meilisearch. Everything else calls SearchService only, so the swap changes no caller.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

MAX_QUERY_CHARS = 100
MAX_PAGE_SIZE = 50

SORTS = frozenset({"relevance", "newest", "price_low", "price_high"})


@dataclass(frozen=True)
class SearchRequest:
    query: str
    category_id: int | None = None
    sort: str = "relevance"
    limit: int = 24
    cursor: str | None = None  # opaque; returned by the previous page

    def __post_init__(self) -> None:
        if self.sort not in SORTS:
            raise ValueError(f"unknown sort {self.sort!r}")
        if not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be 1 to {MAX_PAGE_SIZE}")


@dataclass(frozen=True)
class SearchPage:
    product_ids: Sequence[int]  # in result order
    next_cursor: str | None = None


class SearchService(Protocol):
    def search(self, request: SearchRequest) -> SearchPage: ...


def normalise_query(raw: str) -> str:
    """Trim, collapse spaces, drop control characters and cap the length, so a search box can
    never send a huge or hostile string to the database."""
    cleaned = "".join(ch if ch.isprintable() else " " for ch in raw)
    return " ".join(cleaned.split())[:MAX_QUERY_CHARS]
