# PiPy Storage Placement Protocol

## Deterministic placement, leader-authoritative commitment

PiPy does not use a vote to decide which nodes store an artifact replica, and the elected leader does not exercise discretionary tie-breaking authority.

Storage placement has two distinct responsibilities:

1. **Derivation** — every member can independently calculate the same preferred placement from the same agreed cluster state.
2. **Commitment** — the current cluster leader serializes and commits the authoritative placement transition.

The rule is:

> Consensus establishes authoritative state. Deterministic policy derives the placement. The leader commits the result but does not choose among equally valid answers.

This distinction keeps storage placement inexpensive, reproducible, auditable, and compatible with a future replicated-log consensus implementation.

---

## 1. Inputs to placement

A placement calculation is defined by immutable or agreed inputs:

- artifact ID or chunk content ID;
- membership epoch;
- requested replica count;
- eligible storage writers;
- node/failure-domain identity;
- relatively stable storage-class weight;
- writer health and eligibility state.

Live transient metrics such as instantaneous CPU load, exact free-byte count, or network latency must not directly perturb the ranking. They may determine whether a writer is eligible, but they must not cause healthy replicas to migrate continuously.

---

## 2. Authority model

The current elected leader is the authority that serializes a placement intent into authoritative cluster state.

Conceptually:

```text
agreed membership/storage state
            |
            v
 deterministic placement function
            |
            v
 preferred ordered writers
            |
            v
 current leader commits placement intent
```

The leader may not substitute another healthy writer merely because it prefers one machine, and it does not break score ties manually.

Any member can recompute a proposed placement from the same inputs. A proposal that does not match deterministic policy is invalid.

In the MVP, the current leader records/replicates the placement through the existing leader-authoritative state mechanism. When PiPy adopts Raft or another replicated log, the leader will propose the placement transition to the log and quorum commitment will establish it as authoritative.

Consensus therefore does not vote on the hash ranking itself. Consensus only establishes the state on which the ranking is based and commits the resulting state transition.

---

## 3. Weighted rendezvous ranking

PiPy uses weighted rendezvous hashing (highest-random-weight style placement) to produce a deterministic ordering of eligible storage writers.

For each artifact and writer, PiPy computes a canonical byte key from:

```text
artifact_id
node_id
writer_id
```

Each field is UTF-8 encoded and length-prefixed so concatenation cannot be ambiguous.

The default digest is SHA-256. The digest is interpreted as an unsigned big-endian integer and multiplied by the writer's stable integer weight.

Conceptually:

```text
raw_score      = SHA256(canonical_key)
weighted_score = integer(raw_score) * weight
```

Higher score ranks first.

The weight is an administrative/storage-class preference, not a live load measurement. The default weight is 1000. A preferred SSD-backed writer might deliberately receive a higher stable weight; a low-endurance or administratively constrained writer might receive a lower one.

Floating-point arithmetic is deliberately avoided so architecture, Python version, and platform math behavior cannot alter ordering.

---

## 4. Total-order tie breaking

Hash collisions are extraordinarily unlikely, but the protocol still defines a complete deterministic order.

Candidates are ordered by:

1. higher weighted rendezvous score;
2. lexicographically smaller UTF-8 `node_id` if scores are equal;
3. lexicographically smaller UTF-8 `writer_id` if both score and node ID are equal.

Thus an exact score tie never invokes leader judgment.

Given the same inputs, every conforming PiPy member derives the exact same sequence.

---

## 5. Failure domains

Replica count is based on independent failure domains, not merely writer count.

By default one Raspberry Pi is one failure domain.

If one Pi exposes both:

```text
sd
usb-ssd
```

those are two writers but one node failure domain. They cannot satisfy two replicas of a three-replica durability requirement.

The placement planner walks the deterministic writer ranking and accepts only the highest-ranked writer from each not-yet-selected failure domain until the requested replica count is reached.

For the default SD-card configuration, this means three durable replicas live on three distinct Pi nodes.

---

## 6. Eligibility

A writer participates in ranking only when it is eligible.

Initial eligibility requires:

- member is alive according to authoritative membership/liveness state;
- writer is healthy;
- writer is writable;
- configured minimum free-space threshold is satisfied;
- writer has not been administratively excluded.

Eligibility may change quickly; ranking weights should not.

This distinction prevents a small free-space fluctuation from causing widespread placement churn.

---

## 7. Initial placement

For a three-replica durable artifact in a six-node cluster:

```text
rank(artifact A):
    Pi 5
    Pi 2
    Pi 6
    Pi 1
    Pi 4
    Pi 3
```

The first three distinct eligible failure domains become the preferred initial destinations:

```text
artifact A -> Pi 5, Pi 2, Pi 6
```

The producer may stream directly to those nodes. Artifact bytes do not need to pass through the leader.

The leader's responsibility is the control-plane transition, not data-plane relaying.

---

## 8. Publication

A typical durable publication is:

```text
producer creates artifact
        |
        v
leader derives/commits placement intent
        |
        v
producer streams directly to selected writers
        |
        v
writers verify content hash and return receipts
        |
        v
leader commits artifact as durable when policy is satisfied
```

A follower can verify that the placement intent matches deterministic policy before accepting replicated state.

---

## 9. Repair

Healthy placement is sticky.

Suppose the preferred initial ranking is:

```text
Pi 2, Pi 4, Pi 7, Pi 1, Pi 5, ...
```

and the artifact is stored on Pi 2, Pi 4, and Pi 7.

If Pi 4 is lost, the reconciler walks the same deterministic ranking, skips unavailable/existing failure domains, and selects Pi 1 as the next repair target.

```text
before: Pi 2, Pi 4, Pi 7
Pi 4 fails
repair: Pi 2 or Pi 7 -> Pi 1
after:  Pi 2, Pi 7, Pi 1
```

If Pi 4 later returns, PiPy does **not** automatically rewrite the healthy Pi 1 replica merely because Pi 4 ranks higher. Existing healthy placement remains valid until repair, explicit rebalance, retention change, or another policy event requires movement.

This is the storage rule:

> Placement is deterministic; healthy placement is sticky.

It avoids unnecessary network traffic and SD-card wear.

---

## 10. Adding nodes

Adding a new Pi changes rendezvous rankings only for artifacts for which the new node scores highly enough to become a preferred candidate.

PiPy does not immediately rebalance all existing healthy artifacts when membership expands. New membership primarily affects:

- new artifact placement;
- repair decisions;
- explicit future rebalance operations.

This gives PiPy the low-movement property expected from rendezvous placement while retaining the stronger anti-wear rule that healthy replicas are not rewritten merely to chase the new ideal ranking.

---

## 11. Degraded durability

If fewer independent eligible failure domains exist than the requested replica count, the planner returns every valid domain it can select and marks the plan degraded.

For example, a two-node cluster requesting three replicas results in:

```text
selected replicas: 2
desired replicas: 3
state: degraded
```

The cluster must expose this truth through artifact metadata/status and repair automatically when another eligible failure domain becomes available.

---

## 12. Protocol implementation

The MVP implementation lives in `src/pipy/storage.py` and provides:

- `StorageCandidate` — one advertised writer/failure-domain candidate;
- `rendezvous_score()` — canonical integer weighted score;
- `rank_storage_candidates()` — complete deterministic ordering;
- `plan_replicas()` — distinct-failure-domain replica selection;
- `validate_placement()` — independent proposal verification.

The implementation deliberately uses no process-randomized `hash()`, locale collation, floating-point score calculation, or iteration-order dependency.

This module is the normative placement primitive for the forthcoming PersistenceService and DistributedPiWriter implementation.
