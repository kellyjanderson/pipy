from __future__ import annotations

import asyncio
import json
from typing import Any

from .constants import PROTOCOL_VERSION


class ProtocolError(RuntimeError):
    pass


def message(kind: str, **payload: Any) -> dict[str, Any]:
    return {"version": PROTOCOL_VERSION, "kind": kind, **payload}


async def read_message(reader: asyncio.StreamReader) -> dict[str, Any]:
    raw = await reader.readline()
    if not raw:
        raise EOFError
    if len(raw) > 16 * 1024 * 1024:
        raise ProtocolError("message too large")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("version") != PROTOCOL_VERSION or not isinstance(data.get("kind"), str):
        raise ProtocolError("invalid PiPy message")
    return data


async def write_message(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    await writer.drain()


async def request(host: str, port: int, payload: dict[str, Any], *, timeout: float = 10.0) -> dict[str, Any]:
    async with asyncio.timeout(timeout):
        reader, writer = await asyncio.open_connection(host, port)
        try:
            await write_message(writer, payload)
            return await read_message(reader)
        finally:
            writer.close()
            await writer.wait_closed()
