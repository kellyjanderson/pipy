# PiPy

PiPy is a self-organizing distributed-computing fabric for Raspberry Pi computers. Every installation runs the same node software. Nodes discover peers, establish cluster trust, elect a temporary coordinator, replicate cluster state, lease work, compute, recover abandoned work, and broadcast status.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the system design.

## MVP quick start

On the first Raspberry Pi:

```bash
python3 -m pip install .
pipy begin
```

A never-enrolled node creates a lone-wolf cluster and a new cluster identity. In another shell:

```bash
pipy makemeapipy --seed-host 192.168.1.20
```

Copy `makemeapipy.sh` to another Pi and run it. The script installs PiPy and stores a one-use enrollment capability. When that node starts, it discovers/contacts the cluster, proves its freshly generated node identity, authenticates the cluster identity, completes an ephemeral encrypted admission handshake, receives cluster state, and becomes an equal member.

Then, from any member:

```bash
pipy run pi --digits 10000
```

All members, including the current coordinator, participate in computation.

## Discovery

PiPy attempts BLE discovery/advertising using BlueZ/Bleak and also emits a LAN UDP discovery beacon as a recovery/development path. BLE is not the trust boundary: a discovered peer still has to authenticate as a cluster member or present a valid enrollment capability.

## Telemetry

Every node broadcasts `pipy.status.v1` JSON over UDP port 31416. The core has no dashboard dependency. A dashboard can listen, store observations, and render them independently.

## MVP consensus note

The MVP uses a deterministic membership/heartbeat election (lowest live node ID) with an epoch counter rather than a complete Raft implementation. All durable job/work/member state is replicated from the elected leader. The architecture leaves the consensus boundary explicit so a future Raft implementation can replace election/replication without changing the job, discovery, telemetry, or node APIs.
