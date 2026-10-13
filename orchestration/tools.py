"""Small trusted tool vocabulary. Models never supply a command, path, or executable code."""

import hashlib
from pathlib import Path

from orchestration.policies import WorkspacePolicy, validate_proposal, validate_generated_files

EXPIRATION_STARTER = '''"""Brownfield starter: expiration is not implemented yet."""
from datetime import datetime, timezone

def utc_now():
    return datetime.now(timezone.utc)

def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def normalize_expiration(value):
    return None

def check_not_expired(value):
    return None
'''

EXPIRATION_TESTS = """from datetime import timedelta
import pytest
from app.errors import ServiceError
from app.expiration import utc_now
from app.models import ShortURL
from app.schemas import CreateURL

def test_future_expiration_is_persisted(service):
    expiry = utc_now() + timedelta(hours=1)
    link = service.create(CreateURL(url="https://example.com/future", expires_at=expiry))
    assert link.expires_at is not None

def test_expired_link_returns_410_and_does_not_count_click(service):
    link = service.create(CreateURL(url="https://example.com/old"))
    row = service.session.get(ShortURL, link.short_code)
    row.expires_at = utc_now() - timedelta(days=1)
    service.session.commit()
    with pytest.raises(ServiceError) as exc:
        service.resolve(link.short_code)
    assert exc.value.status == 410
    assert service.get(link.short_code).total_clicks == 0

def test_past_expiration_rejected(service):
    with pytest.raises(ServiceError) as exc:
        service.create(CreateURL(url="https://example.com/past", expires_at=utc_now()-timedelta(days=1)))
    assert exc.value.status == 422
"""


def copy_reference(workspace: Path, reference: Path) -> list[str]:
    policy = WorkspacePolicy(workspace)
    written = []
    for source in sorted((reference / "app").rglob("*.py")):
        relative = source.relative_to(reference).as_posix()
        policy.write(relative, source.read_text(encoding="utf-8"))
        written.append(relative)
    for source in sorted((reference / "tests/workspace").glob("*.py")):
        relative = "tests/" + source.name
        policy.write(relative, source.read_text(encoding="utf-8"))
        written.append(relative)
    return written


def prepare_workspace(scenario: str, workspace: Path, reference: Path):
    workspace.mkdir(parents=True, exist_ok=True)
    policy = WorkspacePolicy(workspace)
    if scenario != "greenfield":
        copy_reference(workspace, reference)
    if scenario == "brownfield":
        policy.write("app/expiration.py", EXPIRATION_STARTER)
    if scenario == "ambiguous":
        policy.write("app/features.py", "CREATION_RATE_LIMIT = 60\n")


def apply_proposal(
    scenario: str,
    workspace: Path,
    reference: Path,
    proposal: dict,
    fault_mode: str = "",
    repair_count: int = 0,
    custom_generation: bool = False,
) -> list[dict]:
    parsed = validate_proposal(scenario, proposal, custom_generation=custom_generation)
    policy = WorkspacePolicy(workspace)
    paths = []
    for operation in parsed.operations:
        if operation.kind == "generate_files":
            validate_generated_files(operation.files, workspace)
            # File contents are immutable in the approved proposal artifact.
            # Never execute them from this method.
            for file in operation.files:
                policy.write(file.path, file.content)
                paths.append(file.path)
        elif operation.kind == "bootstrap_reference":
            paths.extend(copy_reference(workspace, reference))
        elif operation.kind == "implement_expiration":
            source = (reference / "app/expiration.py").read_text(encoding="utf-8")
            faulty = fault_mode == "always_fail" or (
                fault_mode == "fail_once" and repair_count == 0
            )
            if faulty:
                # Deliberately materialize a trusted bug to exercise real repair routing.
                source = source.replace(
                    'raise ServiceError(410, "expired", "This short link has expired")',
                    "return  # injected trusted regression: expiration check omitted",
                )
            policy.write("app/expiration.py", source)
            policy.write("tests/test_generated_expiration.py", EXPIRATION_TESTS)
            paths.extend(["app/expiration.py", "tests/test_generated_expiration.py"])
        elif operation.kind == "set_creation_limit":
            policy.write("app/features.py", f"CREATION_RATE_LIMIT = {operation.value}\n")
            test = (
                "from app.features import CREATION_RATE_LIMIT\n"
                "from app.security import RateLimiter\n\n"
                "def test_reviewed_creation_limit_is_enforced():\n"
                f"    assert CREATION_RATE_LIMIT == {operation.value}\n"
                "    limiter = RateLimiter(CREATION_RATE_LIMIT)\n"
                "    for _ in range(CREATION_RATE_LIMIT):\n"
                "        assert limiter.allow('demo', 120)\n"
                "    assert not limiter.allow('demo', 120)\n"
            )
            policy.write("tests/test_generated_policy.py", test)
            paths.extend(["app/features.py", "tests/test_generated_policy.py"])
    return [
        {
            "path": path,
            "sha256": hashlib.sha256(policy.path(path).read_bytes()).hexdigest(),
            "source": "human_approved_model_file" if custom_generation else "reviewed_operation_compiler",
        }
        for path in sorted(set(paths))
    ]
