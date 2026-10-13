import hashlib
import json

import pytest

from app.errors import ServiceError
from app.security import URLSafetyPolicy
from orchestration.audit import AgentStore, redact
from orchestration.policies import PolicyViolation, WorkspacePolicy, validate_proposal
from orchestration.rollback import SnapshotManager


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "ftp://example.com",
        "file:///tmp/a",
        "http://localhost/a",
        "http://10.0.0.1/a",
        "http://127.0.0.1",
        "http://169.254.169.254",
        "http://[::1]/",
        "https://user:password@example.com",
        "http://2130706433",
        "http://0177.0.0.1",
        "http://example.com:8080",
        "https://example.com/\r\nX-Test:bad",
    ],
)
def test_unsafe_targets_rejected(url):
    with pytest.raises(ServiceError):
        URLSafetyPolicy(False).validate(url)


def test_dns_private_or_mixed_answer_rejected():
    policy = URLSafetyPolicy(True, resolver=lambda host: ["93.184.216.34", "10.0.0.1"])
    with pytest.raises(ServiceError):
        policy.validate("https://example.com")


def test_global_ipv6_allowed():
    assert URLSafetyPolicy(False).validate("https://[2606:4700:4700::1111]/")


def test_workspace_traversal_and_symlink_rejected(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy = WorkspacePolicy(workspace)
    for path in ("../outside.py", "/tmp/outside.py", ".env", "app/../../x.py"):
        with pytest.raises(PolicyViolation):
            policy.write(path, "unsafe")
    try:
        (workspace / "app").symlink_to(tmp_path / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("This platform/account cannot create a symlink for this subcase")
    with pytest.raises(PolicyViolation):
        policy.write("app/a.py", "unsafe")


def test_model_cannot_request_shell_or_destructive_operation():
    with pytest.raises(ValueError):
        validate_proposal(
            "brownfield",
            {
                "operations": [{"kind": "shell", "rationale": "run command"}],
                "requirement_ids": ["REQ"],
                "decision_ids": [],
                "summary": "bad",
            },
        )


def test_snapshot_restores_modified_and_removes_created_files(tmp_path):
    policy = WorkspacePolicy(tmp_path / "workspace")
    policy.write("app/original.py", "value = 1\n")
    snapshots = SnapshotManager(policy.workspace, tmp_path / "snapshot")
    snapshots.create()
    policy.write("app/original.py", "value = 2\n")
    policy.write("tests/new.py", "new = True\n")
    snapshots.restore()
    assert policy.path("app/original.py").read_text() == "value = 1\n"
    assert not policy.path("tests/new.py").exists()


def test_redaction_and_audit_integrity(tmp_path):
    assert redact({"api_key": "secret", "command_key": "pytest_workspace"}) == {
        "api_key": "[REDACTED]",
        "command_key": "pytest_workspace",
    }
    store = AgentStore(tmp_path)
    for index in range(3):
        store.record("test", 1, "test", "action", "passed", index=index)
    previous = "0" * 64
    for event in store.audit_events("test"):
        digest, prior = event.pop("event_hash"), event.pop("previous_hash")
        assert prior == previous
        assert (
            digest
            == hashlib.sha256(
                (previous + json.dumps(event, sort_keys=True, separators=(",", ":"))).encode()
            ).hexdigest()
        )
        previous = digest
