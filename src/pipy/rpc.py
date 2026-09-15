from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Protocol

from .crypto import check_mac, sign, verify
from .models import Job, Member, NodeStatus
from .protocol import ProtocolError, message, read_message, write_message


class RpcNode(Protocol):
    cfg: Any
    store: Any

    async def is_leader(self) -> bool: ...
    async def leader_endpoint(self) -> dict[str, Any] | None: ...
    async def telemetry_payload(self) -> dict[str, Any]: ...
    async def _submit_job(self, kind: str, parameters: dict[str, Any], submitted_by: str) -> Job: ...
    async def _lease_work(self, worker_id: str) -> Any: ...
    async def _accept_result(self, worker_id: str, work_id: str, result: dict[str, Any]) -> bool: ...
    async def _handle_admission(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, hello: dict[str, Any]) -> None: ...


class RpcMixin:
    cfg: Any
    store: Any

    def _signed(self, kind: str, **payload: Any) -> dict[str, Any]:
        body = message(kind, node_id=self.cfg.node_id, **payload)
        body["signature"] = sign(self.cfg.node_private, {k: v for k, v in body.items() if k != "signature"})
        return body

    async def _member_for(self, node_id: str) -> Member | None:
        return next((m for m in await asyncio.to_thread(self.store.members) if m.node_id == node_id), None)

    async def _verify_member_message(self, data: dict[str, Any]) -> bool:
        member = await self._member_for(str(data.get("node_id") or ""))
        if member is None:
            return False
        signature = str(data.get("signature") or "")
        unsigned = {k: v for k, v in data.items() if k != "signature"}
        return verify(member.public_key, unsigned, signature)

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            first = await read_message(reader)
            if first["kind"] == "admission_hello":
                await self._handle_admission(reader, writer, first)
                return
            await write_message(writer, await self._dispatch(first))
        except (EOFError, ProtocolError, json.JSONDecodeError) as exc:
            await write_message(writer, message("error", error=str(exc)))
        except Exception as exc:
            try:
                await write_message(writer, message("error", error=f"{type(exc).__name__}: {exc}"))
            except Exception:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, data: dict[str, Any]) -> dict[str, Any]:
        kind = data["kind"]
        if kind == "status":
            return message("status_result", payload=await self.telemetry_payload())
        if kind == "heartbeat":
            if not await self._verify_member_message(data):
                return message("error", error="unauthenticated heartbeat")
            member = await self._member_for(str(data["node_id"]))
            if member:
                member.last_seen = time.time()
                member.host = str(data.get("host") or member.host)
                member.port = int(data.get("port") or member.port)
                member.capacity = float(data.get("capacity") or member.capacity)
                member.status = NodeStatus.ALIVE
                await asyncio.to_thread(self.store.put_member, member)
            return message("ok")
        if kind == "submit_job":
            if not await self._verify_member_message(data):
                return message("error", error="unauthenticated submit")
            if not await self.is_leader():
                return message("redirect", leader=await self.leader_endpoint())
            job = await self._submit_job(str(data["job_kind"]), dict(data["parameters"]), str(data["node_id"]))
            return message("job_submitted", job=job.to_dict())
        if kind == "lease_request":
            if not await self._verify_member_message(data):
                return message("error", error="unauthenticated lease request")
            if not await self.is_leader():
                return message("redirect", leader=await self.leader_endpoint())
            unit = await self._lease_work(str(data["node_id"]))
            return message("lease_result", work=unit.to_dict() if unit else None)
        if kind == "work_result":
            if not await self._verify_member_message(data):
                return message("error", error="unauthenticated work result")
            if not await self.is_leader():
                return message("redirect", leader=await self.leader_endpoint())
            accepted = await self._accept_result(str(data["node_id"]), str(data["work_id"]), dict(data["result"]))
            return message("result_ack", accepted=accepted)
        if kind == "snapshot":
            if not await self._verify_member_message(data):
                return message("error", error="unauthenticated snapshot")
            if data["node_id"] != await asyncio.to_thread(self.store.get, "leader_id"):
                return message("error", error="snapshot not from leader")
            await asyncio.to_thread(self.store.apply_snapshot, dict(data["snapshot"]))
            return message("ok")
        if kind == "unity_rotate":
            if not await self._verify_member_message(data) or not self.cfg.unity_key:
                return message("error", error="unauthenticated rotation")
            body = dict(data["body"])
            if not check_mac(self.cfg.unity_key, body, str(data["mac"])):
                return message("error", error="invalid rotation MAC")
            self.cfg.unity_key = str(body["new_unity_key"])
            self.cfg.save(self.paths.config)
            return message("ok")
        if kind == "job_status":
            job = await asyncio.to_thread(self.store.job, str(data["job_id"]))
            return message("job_status_result", job=job.to_dict() if job else None)
        return message("error", error=f"unknown request {kind}")
