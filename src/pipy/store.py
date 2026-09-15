from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import ClusterSnapshot, Job, Member, WorkUnit


class StateStore:
    """Small durable state store. Methods are thread-safe and intentionally synchronous.

    The daemon calls them via ``asyncio.to_thread`` so SQLite never blocks the event loop.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._db:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS members (node_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS work (work_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS enrollment (token_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL);
                """
            )

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return default if row is None else json.loads(row[0])

    def set(self, key: str, value: Any) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, sort_keys=True)),
            )

    def put_member(self, member: Member) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO members(node_id,payload) VALUES(?,?) ON CONFLICT(node_id) DO UPDATE SET payload=excluded.payload",
                (member.node_id, json.dumps(member.to_dict(), sort_keys=True)),
            )

    def members(self) -> list[Member]:
        with self._lock:
            rows = self._db.execute("SELECT payload FROM members ORDER BY node_id").fetchall()
        return [Member(**json.loads(r[0])) for r in rows]

    def put_job(self, job: Job) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO jobs(job_id,payload) VALUES(?,?) ON CONFLICT(job_id) DO UPDATE SET payload=excluded.payload",
                (job.job_id, json.dumps(job.to_dict(), sort_keys=True)),
            )

    def jobs(self) -> list[Job]:
        with self._lock:
            rows = self._db.execute("SELECT payload FROM jobs ORDER BY rowid").fetchall()
        return [Job(**json.loads(r[0])) for r in rows]

    def job(self, job_id: str) -> Job | None:
        with self._lock:
            row = self._db.execute("SELECT payload FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return None if row is None else Job(**json.loads(row[0]))

    def put_work(self, unit: WorkUnit) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO work(work_id,job_id,ordinal,payload) VALUES(?,?,?,?) "
                "ON CONFLICT(work_id) DO UPDATE SET payload=excluded.payload, ordinal=excluded.ordinal, job_id=excluded.job_id",
                (unit.work_id, unit.job_id, unit.ordinal, json.dumps(unit.to_dict(), sort_keys=True)),
            )

    def work(self, job_id: str | None = None) -> list[WorkUnit]:
        sql = "SELECT payload FROM work"
        args: tuple[Any, ...] = ()
        if job_id is not None:
            sql += " WHERE job_id=?"
            args = (job_id,)
        sql += " ORDER BY ordinal"
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [WorkUnit(**json.loads(r[0])) for r in rows]

    def create_enrollment(self, token_id: str, token_hash: str, created_at: float) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO enrollment(token_id,token_hash,used,created_at) VALUES(?,?,0,?)", (token_id, token_hash, created_at))

    def put_enrollment(self, token_id: str, token_hash_value: str, used: bool, created_at: float) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO enrollment(token_id,token_hash,used,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(token_id) DO UPDATE SET token_hash=excluded.token_hash, used=excluded.used, created_at=excluded.created_at",
                (token_id, token_hash_value, int(used), created_at),
            )

    def enrollments(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT token_id,token_hash,used,created_at FROM enrollment ORDER BY created_at").fetchall()
        return [{"token_id": r["token_id"], "token_hash": r["token_hash"], "used": bool(r["used"]), "created_at": r["created_at"]} for r in rows]

    def consume_enrollment(self, token_id: str, expected_hash: str) -> bool:
        with self._lock, self._db:
            row = self._db.execute("SELECT token_hash,used FROM enrollment WHERE token_id=?", (token_id,)).fetchone()
            if row is None or row["used"] or row["token_hash"] != expected_hash:
                return False
            self._db.execute("UPDATE enrollment SET used=1 WHERE token_id=?", (token_id,))
            return True

    def snapshot(self) -> ClusterSnapshot:
        return ClusterSnapshot(
            cluster_id=self.get("cluster_id", ""),
            epoch=int(self.get("epoch", 0)),
            leader_id=self.get("leader_id"),
            members=[m.to_dict() for m in self.members()],
            jobs=[j.to_dict() for j in self.jobs()],
            work=[w.to_dict() for w in self.work()],
            enrollments=self.enrollments(),
        )

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.set("cluster_id", snapshot["cluster_id"])
        self.set("epoch", int(snapshot["epoch"]))
        self.set("leader_id", snapshot.get("leader_id"))
        for raw in snapshot.get("members", []):
            self.put_member(Member(**raw))
        for raw in snapshot.get("jobs", []):
            self.put_job(Job(**raw))
        for raw in snapshot.get("work", []):
            self.put_work(WorkUnit(**raw))
        for raw in snapshot.get("enrollments", []):
            self.put_enrollment(str(raw["token_id"]), str(raw["token_hash"]), bool(raw.get("used", False)), float(raw["created_at"]))
