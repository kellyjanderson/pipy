from __future__ import annotations

from pipy.storage import (
    PlacementPlan,
    StorageCandidate,
    plan_replicas,
    rank_storage_candidates,
    validate_placement,
)


def candidates() -> list[StorageCandidate]:
    return [
        StorageCandidate("pi-1"),
        StorageCandidate("pi-2"),
        StorageCandidate("pi-3"),
        StorageCandidate("pi-4"),
        StorageCandidate("pi-5"),
        StorageCandidate("pi-6"),
    ]


def test_replica_selection_is_independent_of_input_order() -> None:
    original = candidates()
    reversed_input = list(reversed(original))

    a = plan_replicas("artifact-123", 7, original)
    b = plan_replicas("artifact-123", 7, reversed_input)

    assert a == b
    assert len(a.selected) == 3
    assert len(set(a.node_ids)) == 3
    assert not a.degraded


def test_equal_scores_use_node_then_writer_total_order() -> None:
    def tied_digest(_: bytes) -> bytes:
        return b"\x01"

    ranked = rank_storage_candidates(
        "artifact",
        [
            StorageCandidate("pi-b", "usb"),
            StorageCandidate("pi-a", "zfs"),
            StorageCandidate("pi-a", "sd"),
        ],
        digest_fn=tied_digest,
    )

    assert [(item.candidate.node_id, item.candidate.writer_id) for item in ranked] == [
        ("pi-a", "sd"),
        ("pi-a", "zfs"),
        ("pi-b", "usb"),
    ]


def test_distinct_failure_domains_are_required_for_replicas() -> None:
    plan = plan_replicas(
        "artifact",
        3,
        [
            StorageCandidate("pi-1", "sd", failure_domain="pi-1"),
            StorageCandidate("pi-1", "usb", failure_domain="pi-1"),
            StorageCandidate("pi-2", "sd", failure_domain="pi-2"),
            StorageCandidate("pi-3", "sd", failure_domain="pi-3"),
        ],
    )

    assert len(plan.selected) == 3
    assert len({candidate.domain for candidate in plan.selected}) == 3


def test_plan_is_degraded_when_not_enough_domains_exist() -> None:
    plan = plan_replicas(
        "artifact",
        1,
        [StorageCandidate("pi-1"), StorageCandidate("pi-2")],
        replica_count=3,
    )

    assert plan.degraded
    assert len(plan.selected) == 2


def test_unhealthy_or_ineligible_writers_do_not_rank() -> None:
    plan = plan_replicas(
        "artifact",
        11,
        [
            StorageCandidate("pi-1"),
            StorageCandidate("pi-2", healthy=False),
            StorageCandidate("pi-3", writable=False),
            StorageCandidate("pi-4", eligible=False),
            StorageCandidate("pi-5"),
            StorageCandidate("pi-6"),
        ],
    )

    assert set(plan.node_ids) == {"pi-1", "pi-5", "pi-6"}


def test_weight_bias_is_stable_and_integer_based() -> None:
    def deterministic_digest(data: bytes) -> bytes:
        # Return a stable nonzero pseudo-score based on the canonical bytes.
        return bytes([sum(data) % 251 + 1])

    normal = StorageCandidate("pi-a", weight=1000)
    preferred = StorageCandidate("pi-b", weight=4000)
    ranked = rank_storage_candidates("artifact", [normal, preferred], digest_fn=deterministic_digest)

    # Weight is part of deterministic ranking; there is no live floating-point load input.
    assert {item.candidate.node_id for item in ranked} == {"pi-a", "pi-b"}
    assert all(isinstance(item.score, int) for item in ranked)


def test_any_member_can_validate_leader_proposal() -> None:
    nodes = candidates()
    proposal = plan_replicas("artifact-verify", 9, nodes)
    assert validate_placement(proposal, list(reversed(nodes)))

    tampered = PlacementPlan(
        artifact_id=proposal.artifact_id,
        membership_epoch=proposal.membership_epoch,
        replica_count=proposal.replica_count,
        selected=tuple(reversed(proposal.selected)),
        degraded=proposal.degraded,
    )
    assert not validate_placement(tampered, nodes)
