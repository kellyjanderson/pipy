# Security Policy

PiPy is early-alpha distributed-systems software. It uses established cryptographic primitives, but the overall protocol and implementation have not yet received an independent security audit. Do not treat the current MVP as hardened infrastructure for hostile networks or high-value secrets.

## Supported versions

Until the first stable release, only the current `main` branch is expected to receive security fixes.

## Reporting a vulnerability

Please do **not** open a public issue containing exploit details, private keys, enrollment capabilities, Wi-Fi credentials, or a working proof of concept for an undisclosed vulnerability.

Use GitHub's private vulnerability reporting / Security Advisory flow for this repository when available. If that mechanism is unavailable, contact the repository owner privately through GitHub before publishing details.

A useful report includes:

- affected commit/version;
- affected Raspberry Pi OS/Python versions where relevant;
- attack preconditions;
- reproduction steps;
- security impact;
- whether credentials or cluster keys may have been exposed;
- any suggested mitigation.

## Security-sensitive assets

Treat these as secrets:

- node private keys;
- the `imapipy` cluster private key;
- unity keys;
- unused enrollment capabilities and generated `makemeapipy.sh` scripts;
- optional Wi-Fi credentials;
- future recovery/revocation material.

Do not commit them to source control or paste them into public issues/logs.

## Current trust model

- Discovery is not authorization.
- Existing members authenticate signed control messages against replicated membership state.
- New members require a one-use enrollment capability.
- Admission uses ephemeral X25519 key agreement, HKDF-derived session keys, authenticated encryption, and Ed25519 identity signatures.
- PiPy relies on the `cryptography` package rather than custom cryptographic primitives.

The current architecture deliberately leaves several hardening items for later milestones, including replay protection for all signed control messages, stronger partition-safe consensus, cluster key-compromise recovery, node revocation, capability expiration, and external protocol review. See [`ROADMAP.md`](ROADMAP.md).

## Deployment guidance

For the MVP:

- run PiPy only on networks you control;
- keep OS packages and Python dependencies updated;
- protect the Pi user account and local PiPy state directory;
- delete enrollment scripts after successful use;
- do not expose the control port directly to the public Internet;
- assume that compromise of a cluster member may compromise cluster-wide secrets in the current design;
- back up identity material only through an intentionally secured process.

## Dependency issues

If a vulnerability originates in a dependency, include the upstream advisory/CVE where available. PiPy should prefer upgrading or replacing the dependency over carrying a private security fork unless there is no practical alternative.
