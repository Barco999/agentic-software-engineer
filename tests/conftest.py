from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import URLSafetyPolicy
from orchestration.service import WorkflowService


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        agent_data_dir=tmp_path / "agent",
        dns_check=False,
    )


@pytest.fixture
def application(settings):
    return create_app(settings, URLSafetyPolicy(dns_check=False))


@pytest.fixture
def client(application):
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def workflow(settings):
    return WorkflowService(settings, Path(__file__).resolve().parents[1])


def finish_run(service, result):
    for _ in range(12):
        if result["pending"] is None:
            return result
        result = service.resume(
            result["run"]["run_id"],
            True,
            "pytest_operator",
            "Reviewed controlled test fixture",
            clarification="Use public destinations and 20 requests per minute; aggregate analytics only.",
            expected_gate=result["pending"]["gate"],
        )
    raise AssertionError("Workflow exceeded the expected number of approval gates")
