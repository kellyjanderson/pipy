# PiPy Persistence Architecture

## Self-contained by default, pluggable by design

PiPy persistence is a first-class cluster subsystem. Workloads produce logical artifacts; they do not write directly to a particular disk, NAS, cloud bucket, or member SD card.

The default configuration is intentionally self-contained: a PiPy cluster stores durable artifacts redundantly across the SD cards of its own members. No NAS, USB disk, database server, or cloud account is required to create a useful cluster.

This default is especially appropriate for the reference π workload because its persistent output is small relative to the available storage on even modest Raspberry Pi systems. It lets PiPy exercise real distributed durability without requiring external infrastructure.

External storage remains optional and interchangeable through the same persistence interface.

---

# 1. Architectural boundary

PiPy separates four concerns:

```text
workload
   |
   | logical artifact
   v
PersistenceService
   |
   +-- identity and metadata
   +-- durability policy
   +-- placement selection
   +-- publication state
   |
   v
StorageWriter
   |
   +-- DistributedPiWriter   (default)
   +-- FilesystemWriter      (USB disk, mounted NAS, local disk)
   +-- S3Writer              (S3-compatible/cloud object storage)
   +-- future writers
```

The workload must not know which writer is active.

A π job, image renderer, prime search, or future scientific workload should all publish through the same persistence API.

---

# 2. Minimal application-facing API

The persistence API should stay deliberately small.

Conceptually:

```python
artifact = await persistence.put(
    source,
    name="pi-1000000.txt",
    content_type="text/plain",
    durability="durable",
)

stream = await persistence.open(artifact.id)
metadata = await persistence.stat(artifact.id)
await persistence.delete(artifact.id)
```

Useful operations are limited to:

- `put` — create and durably publish an artifact;
- `open` — retrieve artifact content as a stream;
- `stat` — retrieve authoritative metadata and durability state;
- `list` — discover artifacts by job/name/type where useful;
- `delete` — request deletion according to retention policy.

The persistence layer owns artifact identity, integrity metadata, durability policy, placement state, and publication state.

---

# 3. Artifact model

An artifact is identified independently from its physical location.

A minimal artifact record contains:

```text
artifact_id
logical_name
content_type
size
content_hash
created_at
creating_job_id
creating_node_id
retention_policy
durability_policy
storage_state
placements
```

Artifact IDs should be stable even when physical placement changes.

Large immutable content should be content-addressed. BLAKE3 or SHA-256 are suitable initial choices; use a mature implementation rather than custom hashing code.

The authoritative cluster state stores artifact metadata and placement descriptions, not the artifact bytes themselves.

---

# 4. Publication lifecycle

Persistence uses an explicit lifecycle so partially written content never appears as a valid artifact.

```text
planned
   |
   v
writing
   |
   v
verifying
   |
   v
committed
```

Failure before `committed` leaves no published artifact.

A writer returns a placement receipt only after the destination has accepted the data and integrity verification succeeds.

The PersistenceService publishes the artifact record only after the requested durability policy has been satisfied.

Temporary state may include `failed`, `repairing`, or `degraded` as the implementation matures.

---

# 5. Durability policy, not destination selection

Workloads request durability characteristics rather than storage implementations.

Initial policy classes:

| Policy | Meaning |
| --- | --- |
| `ephemeral` | May disappear with the executing node; reproducible or temporary data. |
| `cached` | Reproducible data that may be evicted. |
| `durable` | Must survive at least one ordinary node/storage failure. |
| `redundant` | Maintain an explicitly configured replica count. |
| `archival` | Prefer a configured long-term external backend when available. |

A caller says:

```text
durability = durable
```

not:

```text
write to S3
```

Cluster configuration maps policy to writers and placement rules.

---

# 6. Default: DistributedPiWriter

The default writer stores content redundantly on PiPy member storage, normally the SD cards that already host Raspberry Pi OS and PiPy state.

This makes a new cluster completely self-contained.

For small artifacts the initial implementation can replicate the complete artifact rather than shard it.

Example for a three-member cluster with replication factor 3:

```text
artifact A
   +-- Pi 1 /var/lib/pipy/artifacts/...
   +-- Pi 2 /var/lib/pipy/artifacts/...
   +-- Pi 3 /var/lib/pipy/artifacts/...
```

For larger artifacts the same writer may evolve to chunked content-addressed storage:

```text
artifact
   |
   +-- chunk 0 -> Pi 1, Pi 3, Pi 5
   +-- chunk 1 -> Pi 2, Pi 3, Pi 4
   +-- chunk 2 -> Pi 1, Pi 4, Pi 6
```

The artifact record contains the ordered chunk hashes and desired durability. Placement records describe which nodes currently hold each chunk.

## 6.1 Replica policy

The default durability policy should scale with cluster size:

- one-node cluster: one copy; durability is necessarily limited by the only node;
- two-node cluster: two copies where capacity permits;
- three or more nodes: three replicas by default for `durable` artifacts;
- explicit `redundant` policy may request another replica count.

PiPy must report when requested durability cannot currently be met rather than pretending the artifact is fully protected.

## 6.2 Failure repair

When membership or storage health changes, a storage reconciler compares actual placement with desired placement.

```text
node disappears
   |
   v
replica count falls below policy
   |
   v
storage reconciler selects healthy source and destination
   |
   v
copy + hash verification
   |
   v
placement metadata updated
```

Repair is asynchronous and should not block compute scheduling.

## 6.3 SD-card wear

Distributed SD storage is the default because it is universally present, not because SD cards are ideal archival media.

The writer must therefore avoid needless rewrites:

- content-addressed immutable objects;
- no in-place mutation of stored blobs;
- deduplicate identical content;
- batch or coalesce metadata writes where practical;
- do not continuously reshuffle healthy replicas;
- expose write volume/health telemetry when available.

---

# 7. External writers

External storage is an alternate or additional writer, not a different artifact API.

## 7.1 FilesystemWriter

A filesystem writer can target:

- USB SSD/HDD attached to one Pi;
- local SATA/NVMe storage where available;
- NFS mount;
- SMB/CIFS mount;
- other mounted filesystems.

A NAS therefore does not require a PiPy-specific NAS protocol when the OS already exposes it as a filesystem.

The node advertising the writer publishes capacity and availability into cluster resource state.

## 7.2 S3Writer

An object-store writer can support AWS S3 or S3-compatible services.

It should use mature SDKs and preserve the same artifact identity and integrity semantics as local writers.

Cloud credentials remain node/cluster secrets and do not belong in workload definitions.

## 7.3 Multiple writers

A durability policy may target more than one writer.

For example:

```text
durable:
    distributed-pi replicas = 3

archival:
    distributed-pi replicas = 2
    plus S3
```

This allows fast local retrieval and external long-term durability simultaneously.

---

# 8. Writer interface

The storage implementation boundary should be narrow.

Conceptually:

```python
class StorageWriter(Protocol):
    async def put(self, artifact, source) -> PlacementReceipt: ...
    async def open(self, placement) -> AsyncIterator[bytes]: ...
    async def delete(self, placement) -> None: ...
    async def health(self) -> StorageHealth: ...
    async def capacity(self) -> StorageCapacity: ...
```

Writers are responsible for bytes.

The PersistenceService is responsible for policy and artifact truth.

Writers should not independently decide cluster-level durability.

---

# 9. Storage as a cluster resource

Each node advertises storage capabilities alongside compute capability.

Example:

```text
node_id: abc
compute_capacity: 0.72
storage:
  sd:
    class: distributed-local
    free_bytes: 42_000_000_000
    writable: true
  usb0:
    class: attached-filesystem
    free_bytes: 1_800_000_000_000
    writable: true
```

A node may expose zero, one, or multiple storage writers.

The cluster scheduler for storage considers:

- free capacity;
- writer health;
- node liveness;
- failure-domain diversity;
- existing placements;
- requested durability;
- optional performance hints.

Compute capacity and storage capacity are separate resource dimensions.

---

# 10. Control plane versus data plane

Artifact bytes must not flow through the consensus or replicated-state log.

The control plane records:

```text
artifact ID
content hash
size
state
requested durability
placement receipts
replica/chunk health
```

The data plane carries actual bytes using direct authenticated transfer, filesystem I/O, or an external object-store API.

This keeps cluster consensus small even if future workloads produce very large artifacts.

---

# 11. Recovery and reconciliation

Persistence must be convergent after ordinary failures.

On startup or leadership change, the storage reconciler compares authoritative artifact metadata with observed writer/node state.

It may:

- restore missing replicas;
- remove stale temporary writes;
- mark unavailable placements degraded;
- verify suspect hashes;
- adopt verified already-present content where safe;
- defer repair when insufficient capacity or members exist.

Artifact correctness is based on content identity and committed metadata, not merely on a filename existing somewhere.

---

# 12. Pi workload behavior

The reference π workload is intentionally a good first user of the persistence layer.

Its result is small enough that whole-artifact replication across SD cards is inexpensive, while still exercising:

- artifact creation;
- durable publication;
- replication;
- node failure and repair;
- retrieval from another member;
- metadata replication;
- backend substitution.

A completed job can therefore produce:

```text
job result metadata
    +-- artifact_id: ...
    +-- logical_name: pi-1000000.txt
    +-- durability: durable
    +-- replicas: 3/3
```

The workload itself does not know whether those replicas are SD cards, a USB SSD, a NAS, or cloud objects.

---

# 13. Default cluster profile

A fresh PiPy cluster requires no storage configuration.

Default behavior:

```text
writer: distributed-pi
artifact root: PiPy-managed local data directory
policy ephemeral: local only
policy cached: local/distributed as capacity allows
policy durable: replicate across up to 3 distinct members
policy redundant: caller/config specifies replica target
policy archival: fall back to durable until an archival writer is configured
```

This preserves PiPy's core promise:

> Install PiPy on Raspberry Pis and the cluster is useful by itself.

Adding a NAS, hard drive, or cloud account improves capacity or durability but is never required for the cluster to function.

---

# 14. Future evolution

The persistence API should permit future capabilities without changing workloads:

- chunking for large artifacts;
- Reed-Solomon or other erasure coding;
- tiered hot/cold placement;
- artifact pinning and retention windows;
- garbage collection of unreferenced content;
- per-workload quotas;
- encryption at rest;
- remote/cloud lifecycle rules;
- background integrity scrubbing;
- storage-aware compute placement for very large inputs.

Replication is the correct initial distributed-storage strategy. Erasure coding should be introduced only when artifact sizes and cluster scale make replication overhead materially important.
