from .base import DistributedJob
from .pi import PI_JOB, PiJob

JOBS: dict[str, DistributedJob] = {PI_JOB.kind: PI_JOB}

__all__ = ["DistributedJob", "PiJob", "PI_JOB", "JOBS"]
