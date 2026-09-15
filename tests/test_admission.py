import asyncio
import socket
from pathlib import Path

import pytest

from pipy.bootstrap import create_enrollment_bundle, decode_bundle
from pipy.config import Paths
from pipy.node import PiPyNode
from pipy.protocol import message, read_message, write_message


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


@pytest.mark.asyncio
async def test_enrollment_secret_is_not_sent_in_plaintext_hello(tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    async def capture(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        captured.update(await read_message(reader))
        await write_message(writer, message("admission_reject", error="test complete"))
        writer.close()
        await writer.wait_closed()

    port = free_port()
    server = await asyncio.start_server(capture, "127.0.0.1", port)
    node = PiPyNode(Paths(tmp_path / "joiner"), port=free_port())
    bundle = {
        "cluster_id": "test-cluster",
        "cluster_public": "unused-for-rejected-test",
        "token_id": "token-1",
        "secret": "must-not-cross-plaintext",
    }
    try:
        with pytest.raises(RuntimeError, match="test complete"):
            await node._join_member("127.0.0.1", port, bundle)
        assert captured["kind"] == "admission_hello"
        assert captured["token_id"] == "token-1"
        assert "secret" not in captured
    finally:
        server.close()
        await server.wait_closed()
        node.store.close()


@pytest.mark.asyncio
async def test_self_member_refresh_publishes_current_advertised_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = PiPyNode(Paths(tmp_path / "node"), port=free_port())
    monkeypatch.setattr(node, "_advertised_host", lambda: "10.23.45.67")
    try:
        await node.initialize()
        self_member = next(m for m in node.store.members() if m.node_id == node.cfg.node_id)
        assert self_member.host == "10.23.45.67"
    finally:
        node.store.close()
