from pathlib import Path

import pytest

import app.shortener
from app.errors import ServiceError
from app.schemas import CreateURL


def test_imported_domain_is_from_current_workspace():
    assert Path(app.shortener.__file__).resolve().parents[1] == Path.cwd().resolve()


def test_link_creation_redirect_and_analytics(service):
    link = service.create(CreateURL(url="https://example.com/article"))
    assert service.resolve(link.short_code) == "https://example.com/article"
    service.session.expire_all()
    assert service.get(link.short_code).total_clicks == 1


def test_custom_code_collision(service):
    service.create(CreateURL(url="https://example.com", custom_code="stable"))
    with pytest.raises(ServiceError) as exc:
        service.create(CreateURL(url="https://example.org", custom_code="stable"))
    assert exc.value.status == 409


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost/a", "http://10.0.0.1/a"])
def test_public_destination_policy(service, url):
    with pytest.raises(ServiceError):
        service.create(CreateURL(url=url))
