import pytest

from app.database import Base, database
from app.security import URLSafetyPolicy
from app.shortener import URLService


@pytest.fixture
def service(tmp_path):
    engine, factory = database(f"sqlite:///{tmp_path / 'links.db'}")
    Base.metadata.create_all(engine)
    with factory() as session:
        yield URLService(session, URLSafetyPolicy(dns_check=False))
    engine.dispose()
