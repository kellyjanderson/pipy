from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pipy.models import WorkUnit


class DistributedJob(ABC):
    kind: str

    @abstractmethod
    def split(self, job_id: str, parameters: dict[str, Any], target_units: int) -> list[WorkUnit]: ...

    @abstractmethod
    def compute(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def verify(self, payload: dict[str, Any], result: dict[str, Any]) -> bool: ...

    @abstractmethod
    def reduce(self, parameters: dict[str, Any], ordered_results: list[dict[str, Any]]) -> str: ...
