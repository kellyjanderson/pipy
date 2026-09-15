# Changelog

All notable changes to PiPy will be documented here.

PiPy is currently pre-1.0. Until the protocol and persistence formats stabilize, minor releases may contain breaking changes documented in release notes.

## [Unreleased]

### Added

- project architecture and roadmap;
- community contribution, conduct, security, and support policies;
- GitHub issue and pull-request templates;
- Python 3.11–3.13 test/build workflow;
- `python -m pipy` entry point;
- `pipy version` command;
- enrollment bundles may be read from protected files.

### Changed

- corrected package license metadata to Apache-2.0;
- generated enrollment scripts keep the enrollment bundle out of command-line arguments;
- node self-membership now republishes its current advertised address;
- enrollment capability secret is transmitted only after the ephemeral encrypted admission channel is established.

## [0.1.0] - unreleased

Initial MVP implementation:

- self-organizing node runtime;
- lone-wolf cluster genesis;
- authenticated enrollment and `makemeapipy.sh`;
- BLE/UDP discovery;
- temporary leader election and snapshot replication;
- leased distributed work;
- Chudnovsky π workload;
- UDP telemetry;
- systemd helper;
- local deterministic tests.
