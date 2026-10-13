from __future__ import annotations

import hashlib
import json
from pathlib import Path

from orchestration.state import ChangeProposal


class PolicyViolation(ValueError):
    pass


def content_hash(value) -> str:
    serialized = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


class WorkspacePolicy:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def path(self, relative: str) -> Path:
        rel = Path(relative)
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or not rel.parts
            or rel.parts[0] not in {"app", "tests", "docs"}
        ):
            raise PolicyViolation("Path is outside the allowlisted workspace")
        target = self.workspace / rel
        if not target.resolve().is_relative_to(self.workspace):
            raise PolicyViolation("Path or symlink escapes the workspace")
        current = target
        while current != self.workspace:
            if current.is_symlink():
                raise PolicyViolation("Symlinks are not allowed in a change workspace")
            current = current.parent
        if target.suffix not in {".py", ".md"}:
            raise PolicyViolation("Only approved source, tests, and Markdown files may change")
        return target

    def write(self, relative: str, contents: str):
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(contents, encoding="utf-8")
        temp.replace(target)


def validate_generated_files(files, workspace: Path | None = None) -> None:
    """Restrict model file proposals to reviewable, bounded application sources."""
    if not 1 <= len(files) <= 12:
        raise PolicyViolation("Custom generation must contain 1-12 files")
    seen = set()
    for file in files:
        name = file.path
        if (name in seen or "\\" in name or name.startswith("/") or
                any(segment.startswith(".") for segment in name.split("/")) or
                name.lower().endswith(("con.py", "nul.py"))):
            raise PolicyViolation("Duplicate or unsafe proposed filename")
        seen.add(name)
        if not (name.startswith("app/") or name.startswith("tests/") or name.startswith("docs/")):
            raise PolicyViolation("Generated path outside application allowlist")
        if not name.endswith((".py", ".md")):
            raise PolicyViolation("Generated file extension is not approved")
        if len(file.content.encode("utf-8")) > 30000:
            raise PolicyViolation("Generated file exceeds size limit")
        if workspace is not None:
            WorkspacePolicy(workspace).path(name)
        if name.endswith(".py"):
            import ast
            try:
                ast.parse(file.content, filename=name)
            except SyntaxError as exc:
                raise PolicyViolation(f"Generated Python file has invalid syntax: {name}") from exc


def validate_proposal(scenario: str, proposal: dict, *, custom_generation: bool = False) -> ChangeProposal:
    parsed = ChangeProposal.model_validate(proposal)
    allowed = {
        "greenfield": {"bootstrap_reference"},
        "brownfield": {"implement_expiration"},
        "ambiguous": {"set_creation_limit"},
    }[scenario]
    if custom_generation and scenario == "greenfield":
        allowed = {"generate_files"}
    if any(operation.kind not in allowed for operation in parsed.operations):
        raise PolicyViolation("Proposed operation is not authorized for this scenario")
    if any(
        operation.kind == "set_creation_limit" and operation.value is None
        for operation in parsed.operations
    ):
        raise PolicyViolation("A creation-limit change must supply a positive bounded value")
    for operation in parsed.operations:
        if operation.kind == "generate_files":
            validate_generated_files(operation.files)
        elif operation.files:
            raise PolicyViolation("Predefined operations cannot include generated files")
    return parsed
