"""Reproduce all local verification; never claim an unrun live-provider test."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestration.audit import redact  # noqa: E402


def main() -> int:
    evidence = ROOT / "evidence"
    evidence.mkdir(exist_ok=True)
    environment = os.environ.copy()
    environment["AGENT_DATA_DIR"] = str(ROOT / "var" / f"verification-{uuid.uuid4().hex}")
    python = sys.executable
    phases = [
        ("dependency_check", [python, "-m", "pip", "check"]),
        ("pytest", [python, "-m", "pytest", "-q", "--junitxml=evidence/test-results.xml"]),
        ("ruff", [python, "-m", "ruff", "check", "."]),
        ("format", [python, "-m", "ruff", "format", "--check", "."]),
        (
            "imports",
            [
                python,
                "-m",
                "compileall",
                "-q",
                "app",
                "agents",
                "llm",
                "orchestration",
                "scripts",
                "scenarios",
            ],
        ),
        ("openapi", [python, "scripts/export_openapi.py"]),
        ("uvicorn_tcp", [python, "scripts/verify_server.py"]),
        ("offline_scenarios", [python, "scripts/run_scenarios.py", "--offline"]),
    ]
    results = []
    for name, command in phases:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            return_code = completed.returncode
            output = completed.stdout + completed.stderr
        except subprocess.TimeoutExpired as exc:
            return_code = 124
            output = f"Verification timed out: {exc.cmd[1:]}"
        results.append(
            {
                "name": name,
                "command": ["python", *command[1:]],
                "return_code": return_code,
                "duration_seconds": round(time.monotonic() - started, 3),
                "output": redact(output[-10000:]),
            }
        )
        print(f"{'PASS' if return_code == 0 else 'FAIL'} {name}", flush=True)
        if return_code:
            print(redact(output[-10000:]), flush=True)
            break

    tests = {}
    report = evidence / "test-results.xml"
    if report.exists() and any(item["name"] == "pytest" for item in results):
        root = ET.parse(report).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
        tests = {
            key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        tests["passed"] = tests["tests"] - tests["failures"] - tests["errors"] - tests["skipped"]
    successful = len(results) == len(phases) and all(item["return_code"] == 0 for item in results)
    summary = {
        "all_phases_passed": successful,
        "python_version": sys.version.split()[0],
        "tests": tests,
        "phases": results,
        "live_llm_verified": False,
        "docker_build_verified": False,
        "render_deployed": False,
        "windows_execution_verified": False,
    }
    (evidence / "verification.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"all_phases_passed": successful, "tests": tests}), flush=True)
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
