# PiPy Node Names

PiPy gives every node a human-readable display name derived from its persistent node public key. The name is presentation metadata only: cluster identity, authentication, elections, leases, storage placement, and RPC continue to use cryptographic `node_id` and public-key identity.

Examples of the intended style include `Albert Turing`, `Ada Shannon`, `Emmy Knuth`, and `Claude Lovelace`. The names intentionally combine given names and surnames across disciplines rather than reproduce historical full names.

## Dataset v1

Node-name dataset version 1 is frozen with:

- 412 given names;
- 519 surnames;
- 213,828 possible base combinations.

The pool was curated from notable mathematicians, computer scientists, statisticians, logicians, cryptographers, numerical/scientific-computing pioneers, and mathematically central physicists. Primary public indexes used to build and cross-check the corpus include:

- MacTutor History of Mathematics, Alphabetical Biographies: https://mathshistory.st-andrews.ac.uk/Biographies/
- MacTutor History of Mathematics index: https://mathshistory.st-andrews.ac.uk/
- IEEE Computer Society, Computer Pioneers: https://history.computer.org/pioneers/index.html
- Wikipedia, List of computer scientists: https://en.wikipedia.org/wiki/List_of_computer_scientists
- Wikipedia, Lists of mathematicians: https://en.wikipedia.org/wiki/Lists_of_mathematicians
- Wikipedia, List of physicists: https://en.wikipedia.org/wiki/List_of_physicists

The corpus includes adjacent disciplines deliberately. PiPy cares about the mathematical/computational tradition, not strict departmental labels.

## Stability rule

Dataset v1 is an identity-display protocol asset and must never be edited in place. Reordering, adding, or deleting entries would change existing node names because the selected indexes depend on the frozen tuple lengths and order.

If the corpus is expanded later, add dataset v2 and define an explicit cluster-level migration/selection policy. Existing clusters should continue using the dataset version with which their names were established unless deliberately upgraded.

## Deterministic mapping

For dataset version 1:

```text
digest = SHA-256("pipy-node-name-v1\\0" || UTF8(node_public_key))

given_index   = uint64_be(digest[0:8])  mod 412
surname_index = uint64_be(digest[8:16]) mod 519

base_name = GIVEN_NAMES[given_index] + " " + SURNAMES[surname_index]
```

This algorithm is independent of leader, hostname, boot order, IP address, locale, Python's randomized `hash()`, and cluster membership order. Any node with the public key can derive the same name.

A golden vector is retained in tests so accidental changes to the corpus or algorithm are detected.

## Collisions

With 213,828 base combinations, a small PiPy cluster will usually have unique base names, but collisions are possible and therefore specified.

If more than one current member has the same base name, every member deterministically appends a six-hex-digit suffix derived from bytes 16–18 of the same SHA-256 digest:

```text
Albert Turing-7C3A9E
Albert Turing-1D82F4
```

The leader does not choose which node keeps the unsuffixed name. All colliding members are suffixed, and every node independently derives the same result from replicated membership.

When no collision exists, the suffix is omitted.

## User-facing presentation

Human-oriented surfaces should prefer:

```text
Emmy Shannon  a631cd4f92
```

rather than presenting the full opaque node identifier alone. Diagnostic/protocol output may still include the complete `node_id`.
