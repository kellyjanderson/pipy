# Contributing to PiPy

PiPy welcomes contributions that make the cluster easier to understand, safer to operate, more reliable on real Raspberry Pi hardware, or more useful as a small distributed-compute fabric.

## Before you start

Read these first:

1. [`README.md`](README.md) for current behavior and setup.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) for the architectural contract.
3. [`ROADMAP.md`](ROADMAP.md) for current maturity and planned direction.
4. [`SECURITY.md`](SECURITY.md) before changing admission, identity, cryptography, RPC authentication, membership, or key lifecycle.

For substantial architectural changes, open an issue first so the design can be discussed before implementation effort is spent.

## Development setup

```bash
git clone https://github.com/kellyjanderson/pipy.git
cd pipy
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
python -m build
```

Python 3.11 or newer is required.

## Engineering principles

### One node implementation

Do not create permanent controller and worker products. Coordination is a temporary cluster role. Every normal member should remain capable of discovery, compute, state replication, and future leadership.

### Discovery is not trust

BLE, UDP, DNS, IP addresses, or hostnames may tell PiPy where another process is. They must never be sufficient to authorize membership or privileged control operations.

### Deterministic distributed work

Work units should have stable identities, explicit input payloads, independently verifiable results where practical, and idempotent acceptance semantics. Retry and duplicate delivery are normal distributed-systems conditions.

### Keep core headless

Dashboards and historical telemetry stores are observers. They must not become dependencies of scheduling, consensus, membership, or result correctness.

### Use existing packages before inventing infrastructure

Before implementing general-purpose cryptography, networking helpers, serialization, consensus, CLI frameworks, system integration, or similar infrastructure, look for mature standard-library or PyPI solutions first. Bespoke infrastructure needs a concrete reason.

Never implement custom cryptographic primitives.

### Keep asyncio nonblocking

The node control plane uses `asyncio`. CPU-heavy work and blocking system/library operations must execute outside the event loop. Do not hide blocking calls inside `async def` functions.

## Tests

Every behavioral change should include focused tests.

Important categories include:

- deterministic pure workload tests;
- protocol/authentication tests;
- admission and replay tests;
- persistence/restart tests;
- multi-node asyncio integration tests;
- lease expiration/retry tests;
- stale/duplicate message tests;
- failure and shutdown tests.

Tests should not depend on timing sleeps when deterministic synchronization is possible.

Hardware-specific fixes should describe:

- Raspberry Pi model;
- Raspberry Pi OS version;
- Python version;
- Bluetooth adapter/BlueZ version where relevant;
- network topology;
- exact reproduction steps.

## Pull requests

Keep pull requests cohesive. A PR should explain:

- the problem;
- the intended behavior;
- architectural impact;
- security impact, if any;
- tests run;
- hardware validation performed, if any;
- remaining known limitations.

A feature is not complete merely because a helper exists. Production behavior should consume the new path and tests should enter through the real interface where practical.

## Dependencies

New runtime dependencies should be justified by functionality that would otherwise be expensive or risky to maintain internally. Prefer packages that are:

- actively maintained;
- appropriately licensed;
- widely used or technically well established;
- compatible with supported Python/Raspberry Pi OS versions;
- reasonably small for the function they provide.

Avoid dependency churn for trivial helpers that are clearer in the standard library.

## Style

- Keep public names descriptive.
- Prefer explicit state transitions over implicit side effects.
- Use typed data structures for protocol/domain state where useful.
- Keep network protocol messages versioned and inspectable.
- Keep comments focused on why, invariants, and non-obvious constraints.
- Avoid compatibility shims unless an actual external compatibility requirement exists.

Run before submitting:

```bash
pytest
ruff check .
python -m build
```

## Security-sensitive contributions

Do not open a public issue for an undisclosed vulnerability. Follow [`SECURITY.md`](SECURITY.md).

## Conduct

Participation in this project is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
