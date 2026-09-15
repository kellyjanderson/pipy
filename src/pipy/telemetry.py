from __future__ import annotations

import asyncio
import json
import socket
import time
from typing import Any

import psutil

from .constants import DEFAULT_TELEMETRY_PORT


class TelemetryBroadcaster:
    def __init__(self, payload_factory, port: int = DEFAULT_TELEMETRY_PORT) -> None:
        self.payload_factory = payload_factory
        self.port = port

    async def run(self, stop: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        try:
            while not stop.is_set():
                payload: dict[str, Any] = dict(await self.payload_factory())
                payload.update({
                    "schema": "pipy.status.v1",
                    "timestamp": time.time(),
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "load": list(psutil.getloadavg()) if hasattr(psutil, "getloadavg") else [],
                })
                try:
                    await loop.sock_sendto(sock, json.dumps(payload, separators=(",", ":")).encode(), ("255.255.255.255", self.port))
                except OSError:
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), 1.0)
                except TimeoutError:
                    pass
        finally:
            sock.close()
