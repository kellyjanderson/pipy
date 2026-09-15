# PiPy Roadmap

PiPy is being developed in maturity stages rather than as a collection of unrelated features. Each stage should leave the cluster more trustworthy, more observable, and easier to deploy on real Raspberry Pi hardware.

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

Known MVP boundaries:

- real multi-Pi hardware has not yet been fully qualified;
- BLE/BlueZ behavior needs hardware validation;
- deterministic leader election is not partition-safe consensus;
- state replication is leader snapshot replication, not a replicated log;
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

## Milestone 2 — Small heterogeneous cluster

Goal: validate self-organization and scheduling on approximately 3–10 mixed Raspberry Pis.

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
- stress tests for simultaneous startup, restart storms, and intermittent nodes;
- deterministic duplicate-result handling under retries;
- explicit node retirement/removal flow;
- cluster identity backup/recovery procedure.

Exit criterion: adding or removing a Pi predictably changes available compute capacity without requiring configuration edits elsewhere.

---

## Milestone 3 — Consensus and partition safety

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
- clear behavior for two-node clusters where quorum availability is inherently limited.

The job/work API should not need to change when this layer is replaced.

Exit criterion: authoritative state cannot diverge under tested network partitions and leader failures.

---

## Milestone 4 — Security hardening

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
- dependency vulnerability scanning and release SBOM.

Exit criterion: cluster compromise and recovery boundaries are explicit, tested, and documented.

---

## Milestone 5 — Workload ecosystem

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
- artifacts separate from control-plane state;
- plugin discovery through Python entry points;
- workload versioning and compatibility declaration.

Pi remains the reference workload and regression benchmark.

---

## Milestone 6 — Observability ecosystem

Goal: keep core PiPy headless while making its behavior easy to inspect.

Planned companion tools:

- `pipy-dash`: UDP telemetry listener, SQLite history, web dashboard;
- `pipy-tui`: terminal cluster view;
- Prometheus/OpenTelemetry bridge;
- benchmark/report generator.

Core rule: observers consume telemetry and never become required for scheduling or correctness.

---

## Milestone 7 — Distribution and release engineering

Goal: make PiPy straightforward to install and update without weakening the self-organizing model.

Planned work:

- resolve the existing PyPI `pipy` project-name conflict or establish a temporary distribution name while retaining the `pipy` module/CLI;
- reproducible wheel/sdist builds;
- automated package validation;
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

PiPy should remain a small, understandable compute fabric that organizes Raspberry Pis into a cooperative execution pool.
