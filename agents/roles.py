import hashlib
from pathlib import Path

from orchestration.audit import redact


def inspect_repository(workspace: Path) -> dict:
    """Inspect actual allowlisted source, not an imagined repository."""
    sources, hashes, total = {}, {}, 0
    for path in sorted((workspace / "app").glob("**/*.py")):
        if path.is_symlink():
            raise ValueError("Repository inspection does not follow symlinks")
        relative = path.relative_to(workspace).as_posix()
        data = path.read_bytes()
        hashes[relative] = hashlib.sha256(data).hexdigest()
        snippet = data.decode("utf-8")[:5000]
        if total + len(snippet) <= 40000:
            sources[relative] = redact(snippet)
            total += len(snippet)
    return {
        "files": list(hashes),
        "hashes": hashes,
        "source_snippets": sources,
        "analysis_basis": "actual_workspace_bytes",
    }


class AgentSuite:
    """Each named role has its own schema/goal; transport and validation are centralized."""

    def __init__(self, client):
        self.client = client

    def run(self, role, schema, state):
        context = {
            key: state.get(key)
            for key in (
                "run_id",
                "scenario",
                "revision",
                "requirement",
                "custom_generation",
                "clarification",
                "architecture_hint",
                "artifacts",
                "decisions",
                "validation",
                "changed_files",
            )
        }
        artifact, usage = self.client.generate(role, schema, context)
        return artifact.model_dump(mode="json"), usage
