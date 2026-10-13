from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.dependencies import get_service
from app.expiration import as_utc
from app.schemas import CreateURL, URLResponse
from app.shortener import URLService

router = APIRouter()
redirect_router = APIRouter()


@router.post(
    "/api/urls",
    response_model=URLResponse,
    status_code=201,
    responses={
        409: {"description": "Custom code conflict"},
        429: {"description": "Creation rate limit exceeded"},
        503: {"description": "Storage or allocation unavailable"},
    },
)
def create_url(body: CreateURL, request: Request, service: URLService = Depends(get_service)):
    link = service.create(body)
    return URLResponse(
        short_code=link.short_code,
        short_url=f"{request.app.state.settings.app_base_url}/{link.short_code}",
        original_url=link.original_url,
        created_at=as_utc(link.created_at),
        expires_at=as_utc(link.expires_at) if link.expires_at else None,
    )


@redirect_router.get(
    "/{short_code}",
    response_class=RedirectResponse,
    status_code=307,
    responses={
        404: {"description": "Link not found"},
        410: {"description": "Link expired"},
        422: {"description": "Unsafe destination"},
    },
)
def redirect_url(short_code: str, service: URLService = Depends(get_service)):
    return RedirectResponse(
        service.resolve(short_code), status_code=307, headers={"Cache-Control": "no-store"}
    )
