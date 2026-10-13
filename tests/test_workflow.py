import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from orchestration.gates import validate_dependencies
from orchestration.policies import PolicyViolation
from orchestration.service import WorkflowService
from tests.conftest import finish_run


def test_langgraph_pause_resume_and_persistent_checkpoint(workflow, settings):
    result = workflow.start("greenfield", offline=True)
    run_id = result["run"]["run_id"]
    assert result["pending"]["gate"] == "architecture"
    replacement_service = WorkflowService(settings)
    loaded, pending = replacement_service.state(run_id)
    assert loaded["artifacts"]["requirements"]
    assert pending["gate"] == "architecture"
    final = finish_run(replacement_service, result)
    assert final["run"]["status"] == "completed"
    state, _ = replacement_service.state(run_id)
    assert state["validation"]["passed"] > 0
    assert state["usage"][0]["inference_performed"] is False
    assert all(task["status"] == "completed" for task in state["tasks"])
    assert all(entry["approval_id"] for entry in state["artifacts"]["changes"])


def test_true_parallel_fanout_and_synchronization(workflow):
    result = finish_run(workflow, workflow.start("greenfield", offline=True))
    events = workflow.store.audit_events(result["run"]["run_id"])
    intervals = {}
    for role in ("implementation_plan", "test_design"):
        start = next(
            e["timestamp"] for e in events if e["agent"] == role and e["action"] == "stage_entry"
        )
        end = next(
            e["timestamp"] for e in events if e["agent"] == role and e["action"] == "stage_exit"
        )
        intervals[role] = (datetime.fromisoformat(start), datetime.fromisoformat(end))
    assert intervals["implementation_plan"][0] < intervals["test_design"][1]
    assert intervals["test_design"][0] < intervals["implementation_plan"][1]
    fanin = datetime.fromisoformat(next(e["timestamp"] for e in events if e["action"] == "fan_in"))
    assert fanin >= max(pair[1] for pair in intervals.values())


def test_rejection_prevents_changes(workflow):
    result = workflow.start("greenfield", offline=True)
    final = workflow.resume(
        result["run"]["run_id"], False, "reviewer", "Reject design", expected_gate="architecture"
    )
    assert final["run"]["status"] == "rejected"
    state, _ = workflow.state(final["run"]["run_id"])
    assert state["changed_files"] == []
    assert not list(Path(state["workspace"]).rglob("*.py"))


def test_release_rejection_restores_brownfield_starter(workflow):
    result = workflow.start("brownfield", offline=True)
    while result["pending"]["gate"] != "release":
        result = workflow.resume(result["run"]["run_id"], True, "reviewer", "Approve scoped change")
    result = workflow.resume(result["run"]["run_id"], False, "reviewer", "Reject release")
    state, _ = workflow.state(result["run"]["run_id"])
    assert state["rollback_done"]
    assert "return None" in (Path(state["workspace"]) / "app/expiration.py").read_text()
    assert not (Path(state["workspace"]) / "tests/test_generated_expiration.py").exists()


def test_real_failed_validation_routes_through_repair(workflow):
    final = finish_run(workflow, workflow.start("brownfield", offline=True, fault_mode="fail_once"))
    assert final["run"]["status"] == "completed"
    assert final["run"]["repair_count"] == 1
    events = workflow.store.audit_events(final["run"]["run_id"])
    outcomes = [e["status"] for e in events if e["action"] == "pytest"]
    assert outcomes == ["failed", "passed"]
    assert workflow.store.metrics()["recovery_samples"] == 1


def test_two_repairs_max_then_rollback_and_safe_stop(workflow):
    final = finish_run(
        workflow, workflow.start("brownfield", offline=True, fault_mode="always_fail")
    )
    assert final["run"]["status"] == "safe_stopped"
    assert final["run"]["repair_count"] == 2
    state, _ = workflow.state(final["run"]["run_id"])
    assert state["rollback_done"]
    assert "return None" in (Path(state["workspace"]) / "app/expiration.py").read_text()
    validations = [
        e for e in workflow.store.audit_events(final["run"]["run_id"]) if e["action"] == "pytest"
    ]
    assert len(validations) == 3
    assert all(e["status"] == "failed" for e in validations)


def test_ambiguous_clarification_replans_before_implementation(workflow):
    result = workflow.start("ambiguous", offline=True)
    assert result["pending"]["gate"] == "clarification"
    state, _ = workflow.state(result["run"]["run_id"])
    assert state["changed_files"] == []
    final = finish_run(workflow, result)
    assert final["run"]["status"] == "completed"
    assert final["run"]["revision"] == 2
    state, _ = workflow.state(final["run"]["run_id"])
    assert state["artifacts"]["requirements"]["open_questions"] == []
    assert "20" in (Path(state["workspace"]) / "app/features.py").read_text()


def test_architecture_revision_preserves_unaffected_requirement_history(workflow):
    result = finish_run(workflow, workflow.start("greenfield", offline=True))
    run_id = result["run"]["run_id"]
    before, _ = workflow.state(run_id)
    old_req = before["artifacts"]["requirements"]
    count_before = len(
        [
            e
            for e in workflow.store.audit_events(run_id)
            if e["agent"] == "requirements" and e["action"] == "stage_exit"
        ]
    )
    revised = workflow.revise(
        run_id,
        "architecture",
        "Require manual deployment and retain aggregate-only analytics",
        "reviewer",
        "Change architecture decision",
    )
    assert revised["pending"]["gate"] == "architecture"
    state, _ = workflow.state(run_id)
    assert state["artifacts"]["requirements"] == old_req
    assert state["tasks"][0]["status"] == "completed"
    final = finish_run(workflow, revised)
    assert final["run"]["status"] == "completed"
    assert final["run"]["revision"] == 2
    count_after = len(
        [
            e
            for e in workflow.store.audit_events(run_id)
            if e["agent"] == "requirements" and e["action"] == "stage_exit"
        ]
    )
    assert count_after == count_before


def test_missing_live_key_safe_stops_without_offline_fabrication(workflow):
    result = workflow.start("greenfield", offline=False)
    assert result["run"]["status"] == "safe_stopped"
    assert result["run"]["mode"] == "live-gemini"
    assert result["run"]["changed_files"] == []
    assert "missing" in result["run"]["stop_reason"]


def test_stale_approval_does_not_authorize_mutated_workspace(workflow):
    result = workflow.start("brownfield", offline=True)
    state, _ = workflow.state(result["run"]["run_id"])
    target = Path(state["workspace"]) / "app/features.py"
    target.write_text("CREATION_RATE_LIMIT = 99\n")
    final = workflow.resume(
        result["run"]["run_id"], True, "reviewer", "Approve previously reviewed hash"
    )
    assert final["run"]["status"] == "rejected"
    assert "stale" in final["run"]["stop_reason"]


def test_cycle_and_missing_dependencies_rejected(workflow):
    result = workflow.start("greenfield", offline=True)
    state, _ = workflow.state(result["run"]["run_id"])
    tasks = state["tasks"]
    tasks[0]["dependencies"] = ["RELEASE"]
    with pytest.raises(ValueError, match="cycle"):
        validate_dependencies(tasks)


def test_public_run_endpoints_do_not_expose_prompt_or_workspace(client, workflow):
    result = workflow.start("greenfield", offline=True)
    run_id = result["run"]["run_id"]
    response = client.get("/api/agent/runs/" + run_id)
    assert response.status_code == 200
    assert "requirement" not in response.json()
    assert "workspace" not in response.json()
    assert "/workspace/" not in client.get("/api/agent/runs/" + run_id + "/audit").text


def test_concurrent_operator_action_is_blocked(workflow):
    result = workflow.start("greenfield", offline=True)
    run_id = result["run"]["run_id"]
    with workflow.run_lock(run_id):
        with pytest.raises(ValueError, match="already executing"):
            workflow.resume(run_id, True, "reviewer", "Approve architecture")


def test_sensitive_requirement_is_not_checkpointed(workflow):
    with pytest.raises(ValueError, match="sensitive"):
        workflow.start("greenfield", offline=True, requirement="Use api_key=abcdef123456")


def test_nested_workspace_does_not_inherit_reference_pytest_config(settings):
    reference = Path(__file__).resolve().parents[1]
    nested_root = reference / "var"
    nested_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nested-pytest-", dir=nested_root) as folder:
        nested_settings = settings.model_copy(update={"agent_data_dir": Path(folder) / "agent"})
        service = WorkflowService(nested_settings, reference)
        result = finish_run(
            service, service.start("brownfield", offline=True, fault_mode="fail_once")
        )
        assert result["run"]["status"] == "completed"
        assert result["run"]["repair_count"] == 1


def test_unexpected_workspace_executable_is_not_trusted(workflow):
    result = workflow.start("greenfield", offline=True)
    while result["pending"]["gate"] != "release":
        result = workflow.resume(result["run"]["run_id"], True, "reviewer", "Reviewed fixture")
    state, _ = workflow.state(result["run"]["run_id"])
    (Path(state["workspace"]) / "tests/unexpected.py").write_text("unexpected = True\n")
    with workflow.runtime(True) as runtime:
        with pytest.raises(PolicyViolation, match="Untrusted executable"):
            runtime._verify_executables(state)
