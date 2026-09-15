# PiPy Roadmap

PiPy is being developed in maturity stages rather than as a collection of unrelated features. Each stage should leave the cluster more trustworthy, more observable, easier to deploy, and more self-contained on real Raspberry Pi hardware.

This roadmap describes direction, not a release-date promise.

## Current state — MVP / pre-hardware alpha

Implemented today:

- one identical node package and CLI;
- lone-wolf cluster genesis;
- persistent node identity and cluster identity;
- one-use `makemeapipy.sh` enrollment capability;
- encrypted authenticated admission;
- BLE and UDP discovery implementations;
- deterministic temporary leader election with epochs;
- SQLite-backed replicated cluster state;
- heartbeat-based liveness;
- expiring work leases;
- leader and non-leader compute participation;
- generic workload interface;
- distributed Chudnovsky binary-splitting π workload;
- observer-only UDP telemetry;
- systemd installation helper;
- deterministic local tests including a real asyncio server/worker path.

Architecturally specified but not yet implemented:

- thin artifact persistence service;
- pluggable storage-writer interface;
- self-contained distributed member storage as the default writer;
- durability policies independent of physical destinations;
- optional attached-disk, NAS/filesystem, and S3-compatible writers.

See [`PERSISTENCE.md`](PERSISTENCE.md) for the storage architecture.

Known MVP boundaries:

- real multi-Pi hardware has not yet been fully qualified;
- BLE/BlueZ behavior needs hardware validation;
- deterministic leader election is not partition-safe consensus;
- state replication is leader snapshot replication, not a replicated log;
- persistent workload artifacts are not yet implemented;
- security has not received an independent audit;
- package publication under the PyPI name `pipy` is blocked by an existing unrelated project using that name.

---

## Milestone 1 — Two-Pi hardware qualification

Goal: prove that the current MVP behaves correctly on actual Raspberry Pi OS systems before increasing architectural complexity.

### Required demonstrations

- initialize Pi A as a lone-wolf cluster;
- generate `makemeapipy.sh` on Pi A;
- enroll Pi B from the script;
- prove BLE discovery in both directions;
- prove UDP discovery fallback;
- verify both nodes agree on cluster identity and unity key;
- verify replicated membership state;
- submit π from either node;
- prove both machines receive work and contribute results;
- unplug the non-leader during active work and observe lease recovery;
- unplug the leader and observe replacement election plus continued operation where the MVP consistency model permits it;
- reboot both machines independently and prove durable rejoin;
- validate systemd startup;
- capture UDP telemetry externally.

### Hardening work

- make advertised-address selection robust on multi-interface hosts;
- validate Bluetooth permissions and BlueZ service requirements;
- produce useful diagnostic errors for unavailable Bluetooth adapters;
- test Wi-Fi changes and DHCP address changes;
- verify clock-skew tolerance for liveness/lease behavior;
- qualify Raspberry Pi Zero 2 W, Pi 4, and Pi 5 where available.

Exit criterion: a two-node cluster can be repeatedly created, restarted, interrupted, and used without manual database repair or topology editing.

---

## Milestone 2 — Self-contained persistent artifacts

Goal: make the default PiPy cluster durably retain workload output without requiring any external storage service.

The first implementation uses member SD cards because every Pi already has them and the π workload produces very small persistent output relative to available capacity. This provides a useful distributed-storage implementation while preserving the zero-external-infrastructure default.

### Persistence foundation

- introduce `PersistenceService` as the only workload-facing artifact API;
- define stable artifact IDs and metadata;
- separate artifact metadata in the control plane from bytes in the data plane;
- implement `put`, `open`, `stat`, `list`, and `delete`;
- implement explicit `planned -> writing -> verifying -> committed` publication lifecycle;
- content-hash every committed artifact;
- keep incomplete writes invisible to consumers;
- connect completed π jobs to persisted result artifacts rather than only inline result strings.

### Default `DistributedPiWriter`

- use PiPy-managed local storage on each member;
- replicate whole artifacts initially rather than prematurely introducing chunking;
- one-member cluster: one available copy;
- two-member cluster: two copies where capacity permits;
- three-or-more-member cluster: three copies by default for `durable` artifacts;
- report degraded durability when the requested replica count cannot be met;
- reconcile/repair lost replicas when members disappear or return;
- verify transferred replicas by content hash;
- avoid unnecessary SD-card writes and replica churn.

### Writer abstraction

- define the thin `StorageWriter` protocol;
- advertise writer capacity and health as a cluster resource;
- add `FilesystemWriter` for local disks, USB storage, NFS, and SMB mounts;
- preserve interfaces for an S3-compatible writer without making cloud storage a requirement;
- allow policy to target more than one writer.

### Durability policies

Initial classes:

- `ephemeral`;
- `cached`;
- `durable`;
- `redundant`;
- `archival`.

Workloads specify durability intent, never storage vendor or physical path.

Exit criterion: a π result can be created on one node, retrieved from another, survive loss of one replica-bearing member when cluster size permits, and repair back to requested durability without workload-specific storage code.

---

## Milestone 3 — Small heterogeneous cluster

Goal: validate self-organization, scheduling, and storage behavior on approximately 3–10 mixed Raspberry Pis.

Planned work:

- capacity-aware lease batch sizing rather than one-unit-at-a-time claiming;
- explicit node capability descriptions (cores, architecture, memory, optional accelerators);
- job admission limits based on cluster resources;
- lease renewal for long work units;
- configurable failure and timeout policies;
- structured cluster event log;
- improved peer-address reconciliation;
- load and temperature telemetry;
- network and computation throughput metrics;
- storage capacity/health telemetry;
- stress tests for simultaneous startup, restart storms, and intermittent nodes;
- deterministic duplicate-result handling under retries;
- explicit node retirement/removal flow;
- cluster identity backup/recovery procedure;
- replica repair during node churn;
- storage placement that avoids needless concentration on one failure domain.

Exit criterion: adding or removing a Pi predictably changes available compute and storage capacity without requiring configuration edits elsewhere.

---

## Milestone 4 — Consensus and partition safety

Goal: replace the MVP election/snapshot mechanism with a formally defined replicated-state protocol.

The intended direction is Raft or an equivalent well-understood consensus design. Prefer a mature maintained implementation if one satisfies PiPy's constraints; do not write a bespoke consensus protocol merely for novelty.

Required properties:

- quorum-based leader election;
- monotonically ordered replicated log;
- committed membership changes;
- durable terms/epochs;
- prevention of dual authoritative leaders during network partitions;
- explicit joint-consensus or equivalent membership transitions;
- snapshot/log compaction;
- recovery after minority partitions;
- deterministic replay into PiPy state;
- clear behavior for two-node clusters where quorum availability is inherently limited;
- artifact metadata transitions consistent with the authoritative cluster state.

The job/work and persistence APIs should not need to change when this layer is replaced.

Exit criterion: authoritative state cannot diverge under tested network partitions and leader failures.

---

## Milestone 5 — Security hardening

Goal: move from carefully designed experimental security to a reviewed operational security model.

Planned work:

- threat-model document;
- external review of admission protocol and key lifecycle;
- enrollment capability expiration;
- optional enrollment revocation before use;
- secure node removal and key rotation;
- cluster-identity private-key strategy review;
- minimize replication of high-value private key material;
- authenticated/encrypted member RPC transport rather than per-message signatures alone where justified;
- replay protection/nonces for signed control requests;
- security event logging;
- secrets-at-rest integration with OS facilities where practical;
- recovery process for compromised members;
- artifact encryption-at-rest policy and writer credential isolation;
- dependency vulnerability scanning and release SBOM.

Exit criterion: cluster compromise and recovery boundaries are explicit, tested, and documented.

---

## Milestone 6 — Workload ecosystem

Goal: demonstrate that PiPy is a useful purpose-built distributed-compute framework rather than a π-specific scheduler.

Candidate workloads:

- prime search/range sieving;
- Mandelbrot/tile rendering;
- hash/search demonstrations;
- file checksumming or integrity scans;
- CPU benchmarking/burn-in;
- embarrassingly parallel scientific calculations.

Workload API evolution may include:

- declared resource requirements;
- work-unit cost estimates;
- streaming or hierarchical reduction;
- checkpointable units;
- durable artifact outputs through the persistence service;
- plugin discovery through Python entry points;
- workload versioning and compatibility declaration.

Pi remains the reference workload and regression benchmark.

---

## Milestone 7 — Storage scaling

Goal: preserve the thin persistence API as workloads begin producing artifacts large enough that whole-file replication is inefficient.

Potential work, driven by demonstrated need rather than implemented preemptively:

- content-defined or fixed-size chunking;
- chunk-level content addressing and deduplication;
- background integrity scrubbing;
- artifact garbage collection and retention policies;
- tiered storage placement;
- S3-compatible writer;
- quotas and capacity reservations;
- storage-aware compute placement for large immutable inputs;
- Reed-Solomon or other erasure coding when replication overhead becomes materially expensive.

Replication remains the preferred simple mechanism until measured storage volume justifies erasure coding complexity.

---

## Milestone 8 — Observability ecosystem

Goal: keep core PiPy headless while making its behavior easy to inspect.

Planned companion tools:

- `pipy-dash`: UDP telemetry listener, SQLite history, web dashboard;
- `pipy-tui`: terminal cluster view;
- Prometheus/OpenTelemetry bridge;
- benchmark/report generator.

Core rule: observers consume telemetry and never become required for scheduling, storage, or correctness.

---

## Milestone 9 — Distribution and release engineering

Goal: make PiPy straightforward to install and update without weakening the self-organizing model.

Planned work:

- resolve the existing PyPI `pipy` project-name conflict or establish a temporary distribution name while retaining the `pipy` module/CLI;
- reproducible wheel/sdist builds;
- local/release-script package validation without requiring hosted CI;
- signed/tagged releases;
- release notes and changelog discipline;
- supported-Python/Raspberry-Pi-OS matrix;
- optional system package or install script for Raspberry Pi OS;
- safe cluster-aware upgrade protocol;
- protocol-version compatibility policy.

The desired final user experience remains:

```bash
pip install pipy
pipy begin
```

---

## Non-goals

Unless the architecture changes explicitly, PiPy is not trying to become:

- Kubernetes;
- a container runtime;
- a remote shell fleet manager;
- a general-purpose distributed database;
- a mandatory cloud service;
- a dashboard-centric orchestration product.

PiPy should remain a small, understandable compute fabric that organizes Raspberry Pis into a cooperative execution and storage pool.
