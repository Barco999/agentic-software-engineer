from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class CreateURL(APIModel):
    url: str = Field(min_length=1, max_length=2048)
    custom_code: str | None = Field(
        default=None, alias="customCode", pattern=r"^[A-Za-z0-9_-]{3,32}$"
    )
    expires_at: datetime | None = Field(default=None, alias="expiresAt")


class URLResponse(APIModel):
    short_code: str = Field(alias="shortCode")
    short_url: str = Field(alias="shortUrl")
    original_url: str = Field(alias="originalUrl")
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")


class AnalyticsResponse(APIModel):
    short_code: str = Field(alias="shortCode")
    total_clicks: int = Field(alias="totalClicks")
    created_at: datetime = Field(alias="createdAt")
    last_accessed_at: datetime | None = Field(default=None, alias="lastAccessedAt")
