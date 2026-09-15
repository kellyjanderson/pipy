from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable
from typing import Protocol

from .name_data import GIVEN_NAMES, NODE_NAME_DATASET_VERSION, SURNAMES

_NAMESPACE = f"pipy-node-name-v{NODE_NAME_DATASET_VERSION}\0".encode("ascii")


class NamedMember(Protocol):
    node_id: str
    public_key: str


def _digest(public_key: str) -> bytes:
    return hashlib.sha256(_NAMESPACE + public_key.encode("utf-8")).digest()


def node_name(public_key: str) -> str:
    """Return the stable human-readable PiPy name for a node public key."""
    digest = _digest(public_key)
    given_index = int.from_bytes(digest[:8], "big") % len(GIVEN_NAMES)
    surname_index = int.from_bytes(digest[8:16], "big") % len(SURNAMES)
    return f"{GIVEN_NAMES[given_index]} {SURNAMES[surname_index]}"


def collision_suffix(public_key: str) -> str:
    """Return a deterministic suffix used only when base names collide."""
    return _digest(public_key)[16:19].hex().upper()


def cluster_node_names(members: Iterable[NamedMember]) -> dict[str, str]:
    """Return node_id -> display name, deterministically disambiguating collisions.

    Base names are stable functions of public keys. If two current members map to
    the same base name, every member derives the same key-derived suffix for each
    colliding node. The persistent node identity remains node_id; these are display
    labels only.
    """
    materialized = list(members)
    bases = {member.node_id: node_name(member.public_key) for member in materialized}
    counts = Counter(bases.values())
    return {
        member.node_id: (
            f"{bases[member.node_id]}-{collision_suffix(member.public_key)}"
            if counts[bases[member.node_id]] > 1
            else bases[member.node_id]
        )
        for member in materialized
    }


def short_node_id(node_id: str, length: int = 10) -> str:
    return node_id[:length]
