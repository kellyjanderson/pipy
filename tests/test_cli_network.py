import asyncio
import socket
from pathlib import Path

import pytest

from pipy.config import Paths
from pipy.node import PiPyNode


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.mark.asyncio
async def test_real_server_submit_and_worker_loop_complete_job(tmp_path: Path) -> None:
    port = free_port()
    node = PiPyNode(Paths(tmp_path / "node"), port=port)
    await node.initialize()
    await node.start()
    try:
        job = await node.submit_job("pi", {"digits": 60})
        async with asyncio.timeout(10):
            while True:
                current = node.store.job(job.job_id)
                if current and current.status == "complete":
                    assert current.result.startswith("3.141592653589793238462643383279")
                    break
                await asyncio.sleep(0.05)
    finally:
        await node.close()
