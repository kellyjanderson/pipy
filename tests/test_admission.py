import asyncio
import socket
from pathlib import Path

import pytest

from pipy.bootstrap import create_enrollment_bundle, decode_bundle
from pipy.config import Paths
from pipy.node import PiPyNode


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.mark.asyncio
async def test_four_message_admission_establishes_shared_cluster(tmp_path: Path) -> None:
    first_port = free_port()
    second_port = free_port()
    first = PiPyNode(Paths(tmp_path / "first"), port=first_port)
    await first.initialize()
    bundle, _ = create_enrollment_bundle(first.store, first.cfg, seed_host="127.0.0.1")

    second = PiPyNode(Paths(tmp_path / "second"), port=second_port)
    second.cfg.bootstrap_bundle = bundle
    second.cfg.save(second.paths.config)

    first.server = await asyncio.start_server(first._handle_connection, "127.0.0.1", first_port)
    try:
        await second._join_member("127.0.0.1", first_port, decode_bundle(bundle))
        assert second.cfg.cluster_id == first.cfg.cluster_id
        assert second.cfg.cluster_public == first.cfg.cluster_public
        assert second.cfg.cluster_private == first.cfg.cluster_private
        assert second.cfg.unity_key == first.cfg.unity_key
        assert {m.node_id for m in first.store.members()} == {first.cfg.node_id, second.cfg.node_id}
        assert {m.node_id for m in second.store.members()} == {first.cfg.node_id, second.cfg.node_id}
        assert first.store.enrollments()[0]["used"] is True
    finally:
        first.server.close()
        await first.server.wait_closed()
        first.store.close()
        second.store.close()
