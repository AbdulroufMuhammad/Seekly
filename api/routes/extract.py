from fastapi import APIRouter, Depends, HTTPException, Request

from api.db_models import ApiKey
from api.deps import get_api_key
from api.extraction import FetchError, InvalidUrlError, NoContentError
from api.extraction import extract as extract_document
from api.models.document import Document

router = APIRouter()


@router.get("/v1/extract", response_model=Document)
async def extract(
    request: Request,
    url: str,
    query: str | None = None,
    max_passages: int | None = None,
    api_key: ApiKey = Depends(get_api_key),
):
    if not url.strip():
        raise HTTPException(status_code=400, detail="url must not be empty")

    client = request.app.state.http_client
    try:
        return await extract_document(url, client, query=query, max_passages=max_passages)
    except InvalidUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except NoContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
