"""Package source and verification exports, never credentials or runtime state."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "var",
    "dist",
}
REQUIRED_FILES = {
    "README.md",
    "requirements.txt",
    "requirements.lock.txt",
    ".env.example",
    "app/main.py",
    "orchestration/graph.py",
    "docs/coverage-matrix.md",
    "evidence/verification.json",
    "evidence/test-results.xml",
    "evidence/scenario-summary.json",
}


def include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
        return False
    if path.is_symlink() or not path.is_file():
        return False
    name = path.name
    if name.startswith(".env") and name != ".env.example":
        return False
    if path.suffix.lower() in {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".zip"}:
        return False
    return not name.endswith((".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT.parent / "Agentic-URL-Shortener-Complete.zip"
    )
    target = parser.parse_args().output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    prefix = ROOT.name
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if include(path):
                archive.write(path, f"{prefix}/{path.relative_to(ROOT).as_posix()}")
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive integrity check failed")
        names = {name.removeprefix(f"{prefix}/") for name in archive.namelist()}
        missing = REQUIRED_FILES - names
        if missing:
            raise RuntimeError(f"Missing required submission files: {sorted(missing)}")
        count = len(names)
    print(f"Created {target.name}: {count} files, {target.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
