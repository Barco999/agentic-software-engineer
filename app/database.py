from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def database(url: str):
    if not url.startswith("sqlite:"):
        raise ValueError("This prototype supports SQLite database URLs only")
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    options = {"connect_args": {"check_same_thread": False, "timeout": 10}}
    if ":memory:" in url:
        options["poolclass"] = StaticPool
    engine = create_engine(url, **options)

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection, connection_record):
        dbapi_connection.execute("PRAGMA busy_timeout=10000")
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine, sessionmaker(bind=engine, expire_on_commit=False)
