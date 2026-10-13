"""Start a real Uvicorn child, verify it over TCP, and shut down that owned child."""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.smoke import verify


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/live-server.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = os.environ.copy()
        env.update(
            {
                "DATABASE_URL": f"sqlite:///{directory}/links.db",
                "AGENT_DATA_DIR": str(Path(directory) / "agent"),
                "URL_DNS_CHECK": "false",
            }
        )
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            with httpx.Client(trust_env=False, timeout=1) as client:
                for _ in range(100):
                    if child.poll() is not None:
                        raise RuntimeError("Uvicorn stopped before verification")
                    try:
                        if client.get(base + "/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Server readiness timed out")
            result = {**verify(base), "real_uvicorn_tcp": True, "dns_check_for_smoke": False}
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
        finally:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


if __name__ == "__main__":
    main()
