from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Iterable


DigestFn = Callable[[bytes], bytes]


@dataclass(frozen=True, slots=True)
class StorageCandidate:
    """One writable storage target advertised by a PiPy node.

    ``failure_domain`` defaults to the node identity in callers. Multiple writers
    on the same Pi therefore do not count as independent durable replicas.

    ``weight`` is intentionally a stable integer, not a live free-space value.
    A value of 1000 is neutral. A faster or preferred storage class may use a
    larger value; a less-preferred class may use a smaller value. Eligibility
    changes when a writer becomes unhealthy or crosses a configured free-space
    threshold, but ordinary free-space fluctuations must not continuously
    perturb placement.
    """

    node_id: str
    writer_id: str = "sd"
    failure_domain: str | None = None
    weight: int = 1000
    healthy: bool = True
    writable: bool = True
    eligible: bool = True

    @property
    def domain(self) -> str:
        return self.failure_domain or self.node_id


@dataclass(frozen=True, slots=True)
class RankedStorageCandidate:
    candidate: StorageCandidate
    score: int


@dataclass(frozen=True, slots=True)
class PlacementPlan:
    artifact_id: str
    membership_epoch: int
    replica_count: int
    selected: tuple[StorageCandidate, ...]
    degraded: bool

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(candidate.node_id for candidate in self.selected)


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _canonical_key(artifact_id: str, candidate: StorageCandidate) -> bytes:
    """Return the protocol-defined rendezvous key.

    Length-prefixing prevents ambiguous concatenations. UTF-8 is the canonical
    encoding. The placement protocol never relies on Python's process-randomized
    ``hash()`` function, locale collation, object ordering, or floating point.
    """

    parts = (artifact_id, candidate.node_id, candidate.writer_id)
    encoded = [part.encode("utf-8") for part in parts]
    return b"".join(len(part).to_bytes(4, "big") + part for part in encoded)


def rendezvous_score(
    artifact_id: str,
    candidate: StorageCandidate,
    *,
    digest_fn: DigestFn = _sha256,
) -> int:
    """Calculate a stable weighted rendezvous score.

    Weight is integer-scaled deliberately. This is not a live load balancer: the
    weight represents a relatively stable administrative/storage-class preference.
    Exact equal scores are resolved separately by a protocol-defined total order.
    """

    if candidate.weight <= 0:
        raise ValueError("storage candidate weight must be positive")
    digest = digest_fn(_canonical_key(artifact_id, candidate))
    if not digest:
        raise ValueError("digest function returned an empty digest")
    raw = int.from_bytes(digest, "big", signed=False)
    return raw * candidate.weight


def rank_storage_candidates(
    artifact_id: str,
    candidates: Iterable[StorageCandidate],
    *,
    digest_fn: DigestFn = _sha256,
) -> tuple[RankedStorageCandidate, ...]:
    """Return one globally deterministic ordering of eligible storage writers.

    Ordering is defined by the protocol, not by the leader:

    1. higher weighted rendezvous score;
    2. lexicographically smaller UTF-8 ``node_id`` when scores are equal;
    3. lexicographically smaller UTF-8 ``writer_id`` when both above are equal.

    The tie-breakers are intentionally deterministic. The elected leader has no
    discretionary tie-breaking authority.
    """

    ranked = [
        RankedStorageCandidate(candidate, rendezvous_score(artifact_id, candidate, digest_fn=digest_fn))
        for candidate in candidates
        if candidate.healthy and candidate.writable and candidate.eligible
    ]
    ranked.sort(
        key=lambda item: (
            -item.score,
            item.candidate.node_id.encode("utf-8"),
            item.candidate.writer_id.encode("utf-8"),
        )
    )
    return tuple(ranked)


def plan_replicas(
    artifact_id: str,
    membership_epoch: int,
    candidates: Iterable[StorageCandidate],
    *,
    replica_count: int = 3,
    digest_fn: DigestFn = _sha256,
) -> PlacementPlan:
    """Derive preferred replica placement from agreed cluster state.

    At most one selected writer may belong to a failure domain. For the default
    Raspberry Pi writer, the node itself is the failure domain, so three disks on
    one Pi can never masquerade as three-node durability.

    The result is a proposal. The current cluster leader serializes/commits the
    authoritative placement transition, but any member can independently derive
    and validate the same proposal from the same agreed inputs.
    """

    if membership_epoch < 0:
        raise ValueError("membership_epoch must be non-negative")
    if replica_count < 1:
        raise ValueError("replica_count must be at least one")

    selected: list[StorageCandidate] = []
    domains: set[str] = set()
    for ranked in rank_storage_candidates(artifact_id, candidates, digest_fn=digest_fn):
        candidate = ranked.candidate
        if candidate.domain in domains:
            continue
        domains.add(candidate.domain)
        selected.append(candidate)
        if len(selected) == replica_count:
            break

    return PlacementPlan(
        artifact_id=artifact_id,
        membership_epoch=membership_epoch,
        replica_count=replica_count,
        selected=tuple(selected),
        degraded=len(selected) < replica_count,
    )


def validate_placement(
    plan: PlacementPlan,
    candidates: Iterable[StorageCandidate],
    *,
    digest_fn: DigestFn = _sha256,
) -> bool:
    """Verify that a committed/proposed plan matches deterministic policy."""

    expected = plan_replicas(
        plan.artifact_id,
        plan.membership_epoch,
        candidates,
        replica_count=plan.replica_count,
        digest_fn=digest_fn,
    )
    return plan == expected
