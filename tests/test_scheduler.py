from pathlib import Path

import pytest

from pipy.config import Paths
from pipy.jobs import JOBS
from pipy.models import JobStatus
from pipy.node import PiPyNode


@pytest.mark.asyncio
async def test_leader_leases_and_reduces_pi_job(tmp_path: Path) -> None:
    node = PiPyNode(Paths(tmp_path / "node"), port=31415)
    await node.initialize()
    job = await node._submit_job("pi", {"digits": 80}, node.cfg.node_id)
    while True:
        unit = await node._lease_work(node.cfg.node_id)
        if unit is None:
            break
        result = JOBS["pi"].compute(unit.payload)
        assert await node._accept_result(node.cfg.node_id, unit.work_id, result)
    complete = node.store.job(job.job_id)
    assert complete is not None
    assert complete.status == JobStatus.COMPLETE
    assert complete.result.startswith("3.1415926535897932384626433832795")
    node.store.close()
