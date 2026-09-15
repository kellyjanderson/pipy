from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class NodeStatus(StrEnum):
    ALIVE = "alive"
    SUSPECT = "suspect"
    DEAD = "dead"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class WorkStatus(StrEnum):
    AVAILABLE = "available"
    LEASED = "leased"
    COMPLETE = "complete"


@dataclass(slots=True)
class Member:
    node_id: str
    public_key: str
    host: str
    port: int
    hostname: str
    joined_at: float
    last_seen: float
    status: str = NodeStatus.ALIVE
    capacity: float = 1.0

    @property
    def display_name(self) -> str:
        from .names import node_name

        return node_name(self.public_key)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Job:
    job_id: str
    kind: str
    parameters: dict[str, Any]
    created_at: float
    status: str = JobStatus.PENDING
    submitted_by: str | None = None
    result: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorkUnit:
    work_id: str
    job_id: str
    ordinal: int
    payload: dict[str, Any]
    status: str = WorkStatus.AVAILABLE
    lease_owner: str | None = None
    lease_until: float | None = None
    result: dict[str, Any] | None = None
    result_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ClusterSnapshot:
    cluster_id: str
    epoch: int
    leader_id: str | None
    members: list[dict[str, Any]] = field(default_factory=list)
    jobs: list[dict[str, Any]] = field(default_factory=list)
    work: list[dict[str, Any]] = field(default_factory=list)
    enrollments: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
