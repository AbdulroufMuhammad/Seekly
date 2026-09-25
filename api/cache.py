import hashlib
import time

from api.config import CACHE_TTL_SECONDS
from api.models.search import SearchResponse

_store: dict[str, tuple[float, SearchResponse]] = {}


def _key(query: str, max_results: int, categories: str | None, expand: bool, include_answer: bool) -> str:
    return hashlib.sha256(
        f"{query}:{max_results}:{categories or ''}:{expand}:{include_answer}".encode()
    ).hexdigest()


def get(
    query: str,
    max_results: int,
    categories: str | None = None,
    expand: bool = False,
    include_answer: bool = False,
) -> SearchResponse | None:
    entry = _store.get(_key(query, max_results, categories, expand, include_answer))
    if entry is None:
        return None
    expires_at, response = entry
    if time.monotonic() > expires_at:
        return None
    return response


def set(
    query: str,
    max_results: int,
    response: SearchResponse,
    categories: str | None = None,
    expand: bool = False,
    include_answer: bool = False,
) -> None:
    key = _key(query, max_results, categories, expand, include_answer)
    _store[key] = (time.monotonic() + CACHE_TTL_SECONDS, response)
