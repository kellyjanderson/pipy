# PiPy

PiPy is a self-organizing distributed-computing fabric for Raspberry Pi computers. Install the same software on every node, start the nodes, and they form a cooperative compute cluster without a permanently special controller.

The reference workload computes arbitrary-precision π with distributed Chudnovsky binary splitting. The cluster machinery itself is workload-agnostic: jobs are split into deterministic work units, leased to available nodes, verified, reduced, replicated, and recovered when nodes disappear.

> **Project status:** early alpha / hardware-validation stage. The software architecture and local multi-node tests are implemented; real Raspberry Pi and BlueZ/BLE validation is the next milestone.

## What PiPy does

- one identical node implementation on every Raspberry Pi;
- lone-wolf first boot that creates a new cluster identity;
- `makemeapipy.sh` enrollment for additional nodes;
- BLE-first peer discovery, with LAN UDP discovery as a recovery/development path;
- authenticated node admission with per-node identities and ephemeral session keys;
- temporary leader election rather than a permanent controller machine;
- replicated membership, job, work, and enrollment state;
- expiring work leases so abandoned work is automatically recoverable;
- heterogeneous-node participation with measured capacity tracking;
- a generic distributed workload interface;
- Chudnovsky/binary-splitting π as the first workload;
- observer-only UDP telemetry for dashboards and external tools;
- no dashboard, database server, message broker, or orchestrator required for cluster correctness.

For the complete architectural contract, see [`ARCHITECTURE.md`](ARCHITECTURE.md). For planned work and maturity milestones, see [`ROADMAP.md`](ROADMAP.md).

## Requirements

The MVP targets:

- Raspberry Pi OS or another modern Linux distribution;
- Python 3.11 or newer;
- network connectivity between nodes;
- BlueZ for BLE discovery on Raspberry Pi/Linux hosts.

Development and most protocol/scheduler tests can run on non-Pi machines. BLE advertising and real cluster networking still require hardware validation.

## Install for development

```bash
git clone https://github.com/kellyjanderson/pipy.git
cd pipy
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Run static checks with:

```bash
ruff check .
python -m build
```

### PyPI naming note

The product, Python module, and command are all named **PiPy / `pipy`**. The PyPI distribution name `pipy`, however, is currently held by an unrelated project released in 2015. Until that naming issue is resolved, install PiPy from this repository rather than assuming `pip install pipy` refers to this project.

The intended long-term installation experience remains:

```bash
pip install pipy
```

## First cluster

On the first Raspberry Pi:

```bash
python3 -m pip install 'git+https://github.com/kellyjanderson/pipy.git'
pipy begin
```

A PiPy installation that has never belonged to a cluster creates a lone-wolf cluster. It generates:

- a persistent node identity;
- the cluster identity (`imapipy`);
- a cluster unity key;
- the initial replicated state;
- the initial leader role.

A node that was previously enrolled does **not** create a new cluster merely because peers are temporarily unavailable.

## Add another Pi

On an existing member:

```bash
pipy makemeapipy --seed-host 192.168.1.20
```

This creates `makemeapipy.sh` containing a one-use enrollment capability and the public cluster identity material needed to authenticate the target cluster.

Copy the script to another Raspberry Pi and run it there:

```bash
chmod 700 makemeapipy.sh
./makemeapipy.sh
```

The joining Pi creates its own long-lived node key pair. Admission then establishes an ephemeral encrypted channel, validates the one-use enrollment capability, authenticates the cluster identity, installs membership state, and joins the cluster as an equal node.

The generated enrollment script is sensitive until it has been used because it carries a one-use admission capability. Treat it like a temporary credential and delete it after successful enrollment.

## Run a distributed π job

From any cluster member:

```bash
pipy run pi --digits 10000
```

The request is routed to the current leader. The workload is divided into deterministic binary-splitting ranges, leased across available members, verified, and reduced into the final result. The leader also participates in computation.

To submit without waiting for completion:

```bash
pipy run pi --digits 100000 --no-wait
```

Inspect local replicated state with:

```bash
pipy status
```

## Run as a service

After initialization, install the systemd service with:

```bash
sudo pipy service install --start
```

The service runs the same `pipy begin` node process used interactively.

## Discovery and trust

PiPy deliberately separates **finding a node** from **trusting a node**.

Discovery uses BLE and UDP beacons to locate possible peers. Discovery data is never sufficient to grant membership. Existing members authenticate signed protocol messages against the replicated member list. New nodes require a valid enrollment capability and must complete the authenticated admission exchange.

The MVP currently uses a deterministic leader/epoch model rather than full Raft consensus. This is an explicit MVP boundary, documented in [`ROADMAP.md`](ROADMAP.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Telemetry

Every node emits observer-only `pipy.status.v1` JSON telemetry over UDP port `31416`.

Cluster correctness does not depend on telemetry delivery. External tools may listen, store, and visualize it independently. A future `pipy-dash` package can therefore remain completely separate from the compute fabric.

## Repository layout

```text
ARCHITECTURE.md      detailed system architecture
ROADMAP.md           planned maturity milestones
src/pipy/            production package
  admission.py       authenticated cluster enrollment
  bootstrap.py       genesis and enrollment-script generation
  discovery.py       BLE and UDP discovery
  jobs/              workload abstraction and π workload
  node.py            node lifecycle, election, scheduling, replication
  rpc.py             authenticated control protocol handlers
  store.py           durable replicated-state storage
  telemetry.py       observer-only UDP status
  cli.py             command-line interface
tests/               deterministic unit/integration tests
```

## Security model

PiPy is experimental distributed-systems software and is not yet security-audited. The implementation intentionally uses established cryptographic primitives from `cryptography` rather than custom cryptography.

Security-sensitive design details and reporting instructions are in [`SECURITY.md`](SECURITY.md).

## Contributing

Contributions are welcome, particularly around Raspberry Pi hardware validation, BlueZ/BLE behavior, failure testing, consensus, distributed scheduling, and additional deterministic workloads.

Read [`CONTRIBUTING.md`](CONTRIBUTING.md), [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), and [`SUPPORT.md`](SUPPORT.md) before opening substantial work.

## License

PiPy is licensed under the [Apache License 2.0](LICENSE).
