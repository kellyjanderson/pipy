# PiPy Support

PiPy is currently an early-alpha project. Support is community/project-maintainer best effort rather than a commercial support commitment.

## Before asking for help

Please check:

- [`README.md`](README.md) for installation and basic operation;
- [`ROADMAP.md`](ROADMAP.md) for known MVP boundaries;
- [`ARCHITECTURE.md`](ARCHITECTURE.md) for intended behavior;
- existing GitHub issues for the same symptom.

## Bug reports

Open a GitHub issue for reproducible defects that are not security-sensitive.

Include:

- Raspberry Pi model or development host;
- OS and version;
- Python version;
- PiPy commit/version;
- number and type of nodes;
- whether the issue occurs with BLE, UDP, TCP control traffic, compute, or persistence;
- exact command used;
- expected behavior;
- actual behavior;
- relevant logs with secrets removed;
- minimal reproduction steps.

For networking failures, include addresses/topology when useful but remove public IPs, Wi-Fi credentials, enrollment tokens, and private keys.

## Feature requests

Feature requests are welcome. Explain the problem/use case before proposing a particular implementation. Requests that preserve PiPy's small self-organizing compute-fabric model are easier to evaluate than requests that turn it into a general fleet/container orchestrator.

## Security issues

Do not use normal support channels for undisclosed vulnerabilities. Follow [`SECURITY.md`](SECURITY.md).

## Hardware validation

Reports from real Raspberry Pi hardware are particularly valuable during the alpha phase. Include Pi model, Bluetooth/BlueZ information, Raspberry Pi OS version, power/network setup, and whether the same scenario works in local software tests.
