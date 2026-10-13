from fastapi import APIRouter, Depends

from app.dependencies import get_service
from app.expiration import as_utc
from app.schemas import AnalyticsResponse
from app.shortener import URLService

router = APIRouter()


@router.get("/api/urls/{short_code}/analytics", response_model=AnalyticsResponse)
def analytics(short_code: str, service: URLService = Depends(get_service)):
    link = service.get(short_code)
    return AnalyticsResponse(
        short_code=link.short_code,
        total_clicks=link.total_clicks,
        created_at=as_utc(link.created_at),
        last_accessed_at=as_utc(link.last_accessed_at) if link.last_accessed_at else None,
    )
