from pathlib import Path

from pipy.models import Job, Member, WorkUnit
from pipy.store import StateStore


def test_snapshot_round_trip(tmp_path: Path) -> None:
    one = StateStore(tmp_path / "one.sqlite")
    one.set("cluster_id", "cluster")
    one.set("epoch", 3)
    one.set("leader_id", "node-a")
    one.put_member(Member("node-a", "pk", "127.0.0.1", 1, "a", 1.0, 2.0))
    one.put_job(Job("job", "pi", {"digits": 10}, 1.0))
    one.put_work(WorkUnit("work", "job", 0, {"start": 0, "end": 1}))
    one.create_enrollment("token", "hash", 1.0)

    two = StateStore(tmp_path / "two.sqlite")
    two.apply_snapshot(one.snapshot().to_dict())
    assert two.get("cluster_id") == "cluster"
    assert two.get("leader_id") == "node-a"
    assert two.members()[0].node_id == "node-a"
    assert two.jobs()[0].job_id == "job"
    assert two.work()[0].work_id == "work"
    assert two.enrollments()[0]["token_id"] == "token"
    one.close()
    two.close()
