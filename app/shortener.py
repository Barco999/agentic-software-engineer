import secrets

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ServiceError
from app.expiration import check_not_expired, normalize_expiration, utc_now
from app.models import ShortURL
from app.schemas import CreateURL
from app.security import URLSafetyPolicy

RESERVED = {"health", "docs", "redoc", "openapi", "api", "favicon", "robots"}


def generate_code() -> str:
    return "".join(
        secrets.choice("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        for _ in range(7)
    )


class URLService:
    def __init__(self, session: Session, safety: URLSafetyPolicy):
        self.session = session
        self.safety = safety

    def create(self, request: CreateURL) -> ShortURL:
        destination = self.safety.validate(request.url)
        expiry = normalize_expiration(request.expires_at)
        if request.custom_code and request.custom_code.lower() in RESERVED:
            raise ServiceError(422, "reserved_code", "This customCode is reserved")
        for _ in range(1 if request.custom_code else 5):
            link = ShortURL(
                short_code=request.custom_code or generate_code(),
                original_url=destination,
                created_at=utc_now(),
                expires_at=expiry,
                total_clicks=0,
            )
            self.session.add(link)
            try:
                self.session.commit()
                return link
            except IntegrityError:
                self.session.rollback()
                if request.custom_code:
                    raise ServiceError(
                        409, "code_conflict", "This customCode is already in use"
                    ) from None
        raise ServiceError(
            503, "allocation_failed", "Unique-code allocation exhausted its retry budget"
        )

    def get(self, short_code: str) -> ShortURL:
        link = self.session.get(ShortURL, short_code)
        if link is None:
            raise ServiceError(404, "not_found", "Short link does not exist")
        return link

    def resolve(self, short_code: str) -> str:
        link = self.get(short_code)
        check_not_expired(link.expires_at)
        destination = self.safety.validate(link.original_url)
        self.session.execute(
            update(ShortURL)
            .where(ShortURL.short_code == short_code)
            .values(total_clicks=ShortURL.total_clicks + 1, last_accessed_at=utc_now())
        )
        self.session.commit()
        return destination
