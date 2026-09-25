from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api import cache
from api.db_models import ApiKey
from api.deps import get_api_key
from api.llm.deepseek import synthesize_answer
from api.models.search import SearchResponse
from api.providers.base import ProviderUnavailableError

router = APIRouter()


@router.get("/v1/search", response_model=SearchResponse)
async def search(
    request: Request,
    response: Response,
    q: str,
    max_results: int = 10,
    categories: str | None = None,
    expand: bool = False,
    include_answer: bool = False,
    api_key: ApiKey = Depends(get_api_key),
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="q must not be empty")
    max_results = max(1, min(50, max_results))

    cached = cache.get(q, max_results, categories, expand, include_answer)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    provider = request.app.state.searxng_provider
    try:
        if expand:
            extra_queries = [f"{q} news", f"{q} latest"]
            result = await provider.search_expanded(
                q, max_results=max_results, categories=categories, extra_queries=extra_queries
            )
        else:
            result = await provider.search(q, max_results=max_results, categories=categories)
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if include_answer:
        llm_answer = await synthesize_answer(q, result.results, request.app.state.http_client)
        if llm_answer is not None:
            result.answer = llm_answer

    cache.set(q, max_results, result, categories, expand, include_answer)
    response.headers["X-Cache"] = "MISS"
    return result
