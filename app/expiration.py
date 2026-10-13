"""Expiration policy. The brownfield starter replaces this with documented stubs."""

from datetime import datetime, timezone

from app.errors import ServiceError


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    # SQLite does not preserve datetime timezone information on round-trip.
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def normalize_expiration(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ServiceError(422, "invalid_expiration", "expiresAt must include a timezone")
    normalized = as_utc(value)
    if normalized <= utc_now():
        raise ServiceError(422, "invalid_expiration", "expiresAt must be in the future")
    return normalized


def check_not_expired(value: datetime | None) -> None:
    if value is not None and as_utc(value) <= utc_now():
        raise ServiceError(410, "expired", "This short link has expired")
