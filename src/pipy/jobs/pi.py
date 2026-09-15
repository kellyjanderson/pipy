from __future__ import annotations

import hashlib
from decimal import Decimal, localcontext
from typing import Any

from pipy.models import WorkUnit
from .base import DistributedJob

C3_OVER_24 = 10939058860032000


def binary_split(a: int, b: int) -> tuple[int, int, int]:
    if b - a == 1:
        if a == 0:
            return 1, 1, 13591409
        p = (6 * a - 5) * (2 * a - 1) * (6 * a - 1)
        q = a * a * a * C3_OVER_24
        t = p * (13591409 + 545140134 * a)
        if a & 1:
            t = -t
        return p, q, t
    m = (a + b) // 2
    p1, q1, t1 = binary_split(a, m)
    p2, q2, t2 = binary_split(m, b)
    return p1 * p2, q1 * q2, t1 * q2 + p1 * t2


def combine(left: tuple[int, int, int], right: tuple[int, int, int]) -> tuple[int, int, int]:
    p1, q1, t1 = left
    p2, q2, t2 = right
    return p1 * p2, q1 * q2, t1 * q2 + p1 * t2


class PiJob(DistributedJob):
    kind = "pi"

    def split(self, job_id: str, parameters: dict[str, Any], target_units: int) -> list[WorkUnit]:
        digits = max(1, int(parameters["digits"]))
        terms = digits // 14 + 2
        target_units = max(1, min(target_units, terms))
        chunk = max(1, (terms + target_units - 1) // target_units)
        units: list[WorkUnit] = []
        ordinal = 0
        for start in range(0, terms, chunk):
            end = min(terms, start + chunk)
            work_id = hashlib.sha256(f"{job_id}:pi:{start}:{end}".encode()).hexdigest()[:24]
            units.append(WorkUnit(work_id=work_id, job_id=job_id, ordinal=ordinal, payload={"start": start, "end": end}))
            ordinal += 1
        return units

    def compute(self, payload: dict[str, Any]) -> dict[str, Any]:
        p, q, t = binary_split(int(payload["start"]), int(payload["end"]))
        return {"p": str(p), "q": str(q), "t": str(t)}

    def verify(self, payload: dict[str, Any], result: dict[str, Any]) -> bool:
        expected = self.compute(payload)
        return expected == {"p": str(result["p"]), "q": str(result["q"]), "t": str(result["t"])}

    def reduce(self, parameters: dict[str, Any], ordered_results: list[dict[str, Any]]) -> str:
        digits = int(parameters["digits"])
        triples = [(int(r["p"]), int(r["q"]), int(r["t"])) for r in ordered_results]
        while len(triples) > 1:
            triples = [combine(triples[i], triples[i + 1]) if i + 1 < len(triples) else triples[i] for i in range(0, len(triples), 2)]
        _p, q, t = triples[0]
        with localcontext() as ctx:
            ctx.prec = digits + 20
            c = Decimal(426880) * Decimal(10005).sqrt()
            value = c * Decimal(q) / Decimal(t)
            rendered = format(value, "f")
        whole, dot, frac = rendered.partition(".")
        return whole if digits <= 0 else f"{whole}.{frac[:digits]}"


PI_JOB = PiJob()
