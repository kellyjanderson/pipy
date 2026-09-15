from __future__ import annotations

import base64
import json
import shlex
import socket
import time
import uuid

from .config import LocalConfig, Paths
from .crypto import new_ed25519, new_token, new_unity_key, node_id, sign, token_hash
from .models import Member
from .store import StateStore


def encode_bundle(payload: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")


def decode_bundle(value: str) -> dict[str, object]:
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid PiPy enrollment bundle")
    return data


def ensure_identity(paths: Paths, port: int) -> LocalConfig:
    if paths.config.exists():
        cfg = LocalConfig.load(paths.config)
        cfg.port = port
        cfg.save(paths.config)
        return cfg
    private, public = new_ed25519()
    cfg = LocalConfig(
        node_private=private,
        node_public=public,
        node_id=node_id(public),
        port=port,
    )
    cfg.save(paths.config)
    return cfg


def genesis(
    paths: Paths,
    store: StateStore,
    cfg: LocalConfig,
    *,
    wifi_ssid: str | None = None,
    wifi_password: str | None = None,
) -> LocalConfig:
    if cfg.enrolled:
        return cfg
    cluster_private, cluster_public = new_ed25519()
    cfg.cluster_id = str(uuid.uuid4())
    cfg.cluster_private = cluster_private
    cfg.cluster_public = cluster_public
    cfg.unity_key = new_unity_key()
    cfg.wifi_ssid = wifi_ssid
    cfg.wifi_password = wifi_password
    cfg.save(paths.config)
    now = time.time()
    store.set("cluster_id", cfg.cluster_id)
    store.set("epoch", 1)
    store.set("leader_id", cfg.node_id)
    store.put_member(
        Member(
            cfg.node_id,
            cfg.node_public,
            "127.0.0.1",
            cfg.port,
            socket.gethostname(),
            now,
            now,
        )
    )
    return cfg


def create_enrollment_bundle(
    store: StateStore,
    cfg: LocalConfig,
    *,
    seed_host: str | None = None,
) -> tuple[str, str]:
    if not cfg.enrolled or not cfg.cluster_private or not cfg.cluster_public:
        raise RuntimeError("PiPy cluster has not been initialized")
    token_id = str(uuid.uuid4())
    secret = new_token()
    store.create_enrollment(token_id, token_hash(secret), time.time())
    payload: dict[str, object] = {
        "version": 1,
        "cluster_id": cfg.cluster_id,
        "cluster_public": cfg.cluster_public,
        "token_id": token_id,
        "secret": secret,
        "seed_port": cfg.port,
    }
    if seed_host:
        payload["seed_host"] = seed_host
    payload["issuer"] = cfg.node_id
    payload["issuer_signature"] = sign(
        cfg.node_private,
        {key: value for key, value in payload.items() if key != "issuer_signature"},
    )
    return encode_bundle(payload), token_id


def make_script(
    bundle: str,
    *,
    source: str = "git+https://github.com/kellyjanderson/pipy.git",
) -> str:
    qbundle = shlex.quote(bundle)
    qsource = shlex.quote(source)
    return f"""#!/bin/sh
set -eu
PYTHON="${{PYTHON:-python3}}"
"$PYTHON" -m pip install --upgrade {qsource}
umask 077
BUNDLE_FILE="$(mktemp "${{TMPDIR:-/tmp}}/pipy-enrollment.XXXXXX")"
trap 'rm -f "$BUNDLE_FILE"' EXIT HUP INT TERM
BUNDLE={qbundle}
printf '%s' "$BUNDLE" > "$BUNDLE_FILE"
pipy enroll --bundle-file "$BUNDLE_FILE"
rm -f "$BUNDLE_FILE"
trap - EXIT HUP INT TERM
echo "PiPy enrollment prepared. Starting node..."
exec pipy begin
"""
