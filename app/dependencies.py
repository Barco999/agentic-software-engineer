from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.shortener import URLService


def get_db(request: Request) -> Generator[Session, None, None]:
    with request.app.state.session_factory() as session:
        yield session


def get_service(request: Request, db: Session = Depends(get_db)) -> URLService:
    return URLService(db, request.app.state.safety)
