import json
import shutil
from pathlib import Path

from orchestration.policies import WorkspacePolicy


class SnapshotManager:
    def __init__(self, workspace: Path, snapshot_dir: Path):
        self.policy = WorkspacePolicy(workspace)
        self.root = snapshot_dir
        self.manifest = self.root / "manifest.json"

    def create(self):
        if self.manifest.exists():
            return  # Stable baseline makes replay/idempotency safe.
        self.root.mkdir(parents=True, exist_ok=True)
        paths = []
        for source in sorted(self.policy.workspace.rglob("*")):
            if source.is_file() and source.suffix in {".py", ".md"}:
                relative = source.relative_to(self.policy.workspace).as_posix()
                self.policy.path(relative)
                backup = self.root / "files" / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, backup)
                paths.append(relative)
        self.manifest.write_text(json.dumps(paths, indent=2), encoding="utf-8")

    def restore(self) -> list[str]:
        if not self.manifest.exists():
            return []
        original = set(json.loads(self.manifest.read_text(encoding="utf-8")))
        changed = []
        for source in self.policy.workspace.rglob("*"):
            if source.is_file() and source.suffix in {".py", ".md"}:
                relative = source.relative_to(self.policy.workspace).as_posix()
                self.policy.path(relative)
                if relative not in original:
                    source.unlink()
                    changed.append(relative)
        for relative in original:
            target = self.policy.path(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.root / "files" / relative, target)
            changed.append(relative)
        return sorted(changed)
