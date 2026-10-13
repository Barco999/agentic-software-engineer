from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def redact(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]"
            if re.search(
                r"(?i)(api.?key|secret|password|authorization|access.?token|refresh.?token)", k
            )
            else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(Bearer\s+)\S+", r"\1[REDACTED]", value)
        value = re.sub(r"(sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{12,})", "[REDACTED]", value)
        value = re.sub(
            r"(?i)((?:api[_-]?key|password|secret)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", value
        )
        value = re.sub(r"(?:/workspace/|/tmp/|[A-Z]:\\)[^\s\"']+", "[PRIVATE_PATH]", value)
    return value


class AgentStore:
    """Separate durable run summaries and hash-chained audit events.

    Hash chaining detects casual edits; it is not external signing or immutable storage.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "audit.db"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL, data TEXT NOT NULL,
                    previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_events_run ON events(run_id, id);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA busy_timeout=15000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_run(self, state: dict, status: str | None = None, pending_gate: str | None = None):
        public = {
            k: state.get(k)
            for k in (
                "run_id",
                "scenario",
                "mode",
                "revision",
                "started_at",
                "finished_at",
                "repair_count",
                "changed_files",
                "stop_reason",
            )
        }
        public["status"] = status or state.get("status", "running")
        public["pending_gate"] = pending_gate
        public["tasks"] = [{"id": t["id"], "status": t["status"]} for t in state.get("tasks", [])]
        public["validation"] = {
            k: state.get("validation", {}).get(k)
            for k in ("passed", "failed", "skipped", "return_code", "duration_ms")
        }
        public["duration_ms"] = state.get("duration_ms")
        public = redact(public)
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs(run_id,data) VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET data=excluded.data",
                (state["run_id"], json.dumps(public)),
            )

    def public_run(self, run_id: str):
        with self.connect() as db:
            row = db.execute("SELECT data FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_runs(self):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM runs ORDER BY rowid DESC LIMIT 100").fetchall()
        return [json.loads(row[0]) for row in rows]

    def record(
        self,
        run_id: str,
        revision: int,
        agent: str,
        action: str,
        status: str,
        duration_ms: float = 0,
        retry_count: int = 0,
        **details,
    ):
        data = redact(
            {
                "run_id": run_id,
                "revision": revision,
                "timestamp": utc_iso(),
                "agent": agent,
                "action": action,
                "status": status,
                "duration_ms": round(duration_ms, 3),
                "retry_count": retry_count,
                "details": details,
            }
        )
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT event_hash FROM events WHERE run_id=? ORDER BY id DESC LIMIT 1", (run_id,)
            ).fetchone()
            previous = row[0] if row else "0" * 64
            digest = hashlib.sha256((previous + serialized).encode()).hexdigest()
            db.execute(
                "INSERT INTO events(run_id,data,previous_hash,event_hash) VALUES(?,?,?,?)",
                (run_id, serialized, previous, digest),
            )
        return data

    def audit_events(self, run_id: str):
        with self.connect() as db:
            rows = db.execute(
                "SELECT data,previous_hash,event_hash FROM events WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
        return [
            {**json.loads(row[0]), "previous_hash": row[1], "event_hash": row[2]} for row in rows
        ]

    def metrics(self):
        runs = self.list_runs()
        with self.connect() as db:
            events = [json.loads(row[0]) for row in db.execute("SELECT data FROM events")]
        terminal = [r for r in runs if r["status"] in {"completed", "safe_stopped", "rejected"}]
        durations = [r["duration_ms"] for r in terminal if r.get("duration_ms") is not None]
        recoveries, failures = [], {}
        for event in events:
            if event["action"] == "pytest":
                run_id = event["run_id"]
                if event["status"] == "failed":
                    failures.setdefault(run_id, event["timestamp"])
                elif event["status"] == "passed" and run_id in failures:
                    before = datetime.fromisoformat(failures.pop(run_id))
                    after = datetime.fromisoformat(event["timestamp"])
                    recoveries.append((after - before).total_seconds() * 1000)
        validation = [e for e in events if e["action"] == "pytest"]
        return {
            "observed_runs": len(runs),
            "terminal_runs": len(terminal),
            "success_rate": sum(r["status"] == "completed" for r in terminal) / len(terminal)
            if terminal
            else None,
            "repair_attempts": sum(e["action"] == "repair_applied" for e in events),
            "rollback_count": sum(e["action"] == "rollback" for e in events),
            "approval_decisions": sum(e["action"] == "approval_decision" for e in events),
            "validation_pass_rate": sum(e["status"] == "passed" for e in validation)
            / len(validation)
            if validation
            else None,
            "average_end_to_end_latency_ms": sum(durations) / len(durations) if durations else None,
            "mttr_ms": sum(recoveries) / len(recoveries) if recoveries else None,
            "recovery_samples": len(recoveries),
            "provider_retry_count": sum(e["action"] == "provider_retry" for e in events),
            "stage_durations_ms": [
                {"run_id": e["run_id"], "stage": e["agent"], "duration_ms": e["duration_ms"]}
                for e in events
                if e["action"] == "stage_exit"
            ],
        }
