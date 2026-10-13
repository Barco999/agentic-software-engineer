import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from orchestration.audit import redact


def run_trusted_pytest(workspace: Path, report_dir: Path, timeout: int) -> dict:
    """One fixed command against trusted repository/operation-compiler tests.

    A copied workspace and timeout are not an OS security sandbox. Free-form model
    code is not supported and is never sent to this execution path.
    """
    report_dir.mkdir(parents=True, exist_ok=True)
    junit = report_dir / "pytest.xml"
    # Do not inherit a parent project's pythonpath/addopts/conftest and import
    # its reference app instead of the source under validation.
    isolated_config = report_dir / "pytest-isolated.ini"
    isolated_config.write_text("[pytest]\naddopts =\n", encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(isolated_config),
        "--rootdir",
        str(workspace),
        "--confcutdir",
        str(workspace),
        "tests",
        "-q",
        "-p",
        "no:cacheprovider",
        f"--junitxml={junit}",
    ]
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP"}
    }
    env.update(
        {"PYTHONPATH": str(workspace), "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    )
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = redact((result.stdout + result.stderr)[-16000:])
        code = result.returncode
    except subprocess.TimeoutExpired:
        code, output = 124, "Trusted Pytest command exceeded its timeout"
    report = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
        "return_code": code,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
        "command_key": "pytest_workspace",
        "output": output,
    }
    if junit.exists():
        root = ET.parse(junit).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        total = sum(int(s.get("tests", 0)) for s in suites)
        report["failed"] = sum(int(s.get("failures", 0)) for s in suites)
        report["errors"] = sum(int(s.get("errors", 0)) for s in suites)
        report["skipped"] = sum(int(s.get("skipped", 0)) for s in suites)
        report["passed"] = total - report["failed"] - report["errors"] - report["skipped"]
    report["success"] = code == 0 and report["passed"] > 0
    (report_dir / "pytest-output.txt").write_text(output, encoding="utf-8")
    return report


def inspect_generated_sources(workspace: Path, report_dir: Path) -> dict:
    """Syntax-only verification. Intentionally does NOT execute untrusted model code."""
    import ast
    import hashlib
    started = time.monotonic()
    report_dir.mkdir(parents=True, exist_ok=True)
    scanned, failures = [], []
    for folder in ('app', 'tests'):
        for path in sorted((workspace / folder).rglob('*.py')):
            if path.is_symlink() or not path.resolve().is_relative_to(workspace.resolve()):
                failures.append('Symlink or unsafe path')
                continue
            try:
                ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
                scanned.append({'path': path.relative_to(workspace).as_posix(),
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
            except (SyntaxError, UnicodeError) as exc:
                failures.append(f'{path.name}: {type(exc).__name__}')
    report = {
        'passed': len(scanned), 'failed': len(failures), 'skipped': 0, 'errors': 0,
        'return_code': 0 if scanned and not failures else 1,
        'duration_ms': round((time.monotonic() - started) * 1000, 2),
        'command_key': 'static_generated',
        'checks': scanned, 'output': '\n'.join(failures) or 'Python syntax checks only; tests NOT executed.',
        'success': bool(scanned) and not failures,
        'runtime_tests_executed': False,
        'requires_manual_sandbox_test': True,
    }
    (report_dir / 'static-validation.json').write_text(__import__('json').dumps(report, indent=2), encoding='utf-8')
    return report
