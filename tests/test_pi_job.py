from pipy.jobs.pi import PI_JOB


def test_distributed_pi_reduces_to_known_digits() -> None:
    units = PI_JOB.split("job", {"digits": 100}, target_units=5)
    results = [PI_JOB.compute(unit.payload) for unit in units]
    value = PI_JOB.reduce({"digits": 100}, results)
    assert value.startswith("3.14159265358979323846264338327950288419716939937510")
    assert len(value.split(".")[1]) == 100


def test_work_ids_are_deterministic() -> None:
    a = PI_JOB.split("same", {"digits": 1000}, target_units=8)
    b = PI_JOB.split("same", {"digits": 1000}, target_units=8)
    assert [u.work_id for u in a] == [u.work_id for u in b]
