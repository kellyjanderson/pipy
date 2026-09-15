from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import time
import uuid
from typing import Any

from .admission import AdmissionMixin
from .bootstrap import decode_bundle, ensure_identity, genesis
from .config import Paths
from .constants import DEFAULT_LEASE_SECONDS, HEARTBEAT_SECONDS, PEER_DEAD_SECONDS
from .discovery import BleDiscovery, PeerBeacon, UdpDiscovery, cluster_tag
from .jobs import JOBS
from .models import Job, JobStatus, Member, NodeStatus, WorkStatus, WorkUnit
from .protocol import request
from .rpc import RpcMixin
from .store import StateStore
from .telemetry import TelemetryBroadcaster


class PiPyNode(AdmissionMixin, RpcMixin):
    def __init__(self, paths: Paths, *, port: int = 31415) -> None:
        self.paths = paths
        self.store = StateStore(paths.state_db)
        self.cfg = ensure_identity(paths, port)
        self.stop_event = asyncio.Event()
        self.server: asyncio.AbstractServer | None = None
        self.udp = UdpDiscovery(self.cfg.node_id, self.cfg.cluster_id, port)
        self.ble = BleDiscovery(self.cfg.node_id, self.cfg.cluster_id, port)
        self._tasks: list[asyncio.Task[Any]] = []
        self._started_at = time.time()

    async def initialize(self, *, wifi_ssid: str | None = None, wifi_password: str | None = None) -> None:
        if self.cfg.bootstrap_bundle and not self.cfg.enrolled:
            return
        if not self.cfg.enrolled:
            self.cfg = await asyncio.to_thread(genesis, self.paths, self.store, self.cfg, wifi_ssid=wifi_ssid, wifi_password=wifi_password)
        await self._refresh_self_member()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle_connection, host="0.0.0.0", port=self.cfg.port)
        self._tasks.extend([
            asyncio.create_task(self.udp.run_advertiser(self.stop_event), name="udp-advertise"),
            asyncio.create_task(self.udp.listen(self.stop_event), name="udp-listen"),
            asyncio.create_task(self.ble.run_advertiser(self.stop_event), name="ble-advertise"),
            asyncio.create_task(self.ble.scan(self.stop_event), name="ble-scan"),
            asyncio.create_task(self._consume_beacons(self.udp), name="udp-beacons"),
            asyncio.create_task(self._consume_beacons(self.ble), name="ble-beacons"),
            asyncio.create_task(self._heartbeat_loop(), name="heartbeats"),
            asyncio.create_task(self._election_loop(), name="election"),
            asyncio.create_task(self._worker_loop(), name="worker"),
            asyncio.create_task(TelemetryBroadcaster(self.telemetry_payload).run(self.stop_event), name="telemetry"),
        ])
        if self.cfg.bootstrap_bundle and not self.cfg.enrolled:
            self._tasks.append(asyncio.create_task(self._join_from_bundle_loop(), name="admission"))

    async def run(self) -> None:
        await self.start()
        await self.stop_event.wait()

    async def close(self) -> None:
        self.stop_event.set()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self.store.close()

    async def _refresh_self_member(self) -> None:
        if not self.cfg.enrolled:
            return
        now = time.time()
        current = next((m for m in await asyncio.to_thread(self.store.members) if m.node_id == self.cfg.node_id), None)
        member = Member(self.cfg.node_id, self.cfg.node_public, current.host if current else "127.0.0.1", self.cfg.port, socket.gethostname(), current.joined_at if current else now, now, NodeStatus.ALIVE, current.capacity if current else 1.0)
        await asyncio.to_thread(self.store.put_member, member)

    async def telemetry_payload(self) -> dict[str, Any]:
        jobs = await asyncio.to_thread(self.store.jobs)
        active = next((j for j in reversed(jobs) if j.status in {JobStatus.PENDING, JobStatus.RUNNING}), None)
        work = await asyncio.to_thread(self.store.work, active.job_id) if active else []
        return {
            "cluster_id": self.cfg.cluster_id,
            "cluster_tag": cluster_tag(self.cfg.cluster_id),
            "node_id": self.cfg.node_id,
            "leader_id": await asyncio.to_thread(self.store.get, "leader_id"),
            "epoch": await asyncio.to_thread(self.store.get, "epoch", 0),
            "uptime": time.time() - self._started_at,
            "members": len(await asyncio.to_thread(self.store.members)),
            "job_id": active.job_id if active else None,
            "job_kind": active.kind if active else None,
            "work_complete": sum(1 for u in work if u.status == WorkStatus.COMPLETE),
            "work_total": len(work),
        }

    async def _consume_beacons(self, backend: Any) -> None:
        async for beacon in backend.beacons():
            if self.stop_event.is_set():
                return
            await self._on_beacon(beacon)

    async def _on_beacon(self, beacon: PeerBeacon) -> None:
        if self.cfg.enrolled and beacon.cluster_tag != cluster_tag(self.cfg.cluster_id):
            return
        member = await self._member_for(beacon.node_id)
        if member:
            member.host, member.port = beacon.host, beacon.port
            await asyncio.to_thread(self.store.put_member, member)
            try:
                response = await request(beacon.host, beacon.port, self._signed("heartbeat", host=self._advertised_host(), port=self.cfg.port, capacity=member.capacity), timeout=2.0)
                if response.get("kind") == "ok":
                    member.last_seen, member.status = time.time(), NodeStatus.ALIVE
                    await asyncio.to_thread(self.store.put_member, member)
            except Exception:
                pass
        elif self.cfg.bootstrap_bundle and not self.cfg.enrolled:
            bundle = decode_bundle(self.cfg.bootstrap_bundle)
            if beacon.cluster_tag == cluster_tag(str(bundle["cluster_id"])):
                try:
                    await self._join_member(beacon.host, beacon.port, bundle)
                except Exception:
                    pass

    def _advertised_host(self) -> str:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            host = sock.getsockname()[0]
            sock.close()
            return host
        except OSError:
            return "127.0.0.1"

    async def _heartbeat_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.cfg.enrolled:
                await self._refresh_self_member()
                for member in await asyncio.to_thread(self.store.members):
                    if member.node_id == self.cfg.node_id:
                        continue
                    try:
                        response = await request(member.host, member.port, self._signed("heartbeat", host=self._advertised_host(), port=self.cfg.port, capacity=member.capacity), timeout=1.5)
                        if response.get("kind") == "ok":
                            member.last_seen, member.status = time.time(), NodeStatus.ALIVE
                            await asyncio.to_thread(self.store.put_member, member)
                    except Exception:
                        pass
                if await self.is_leader():
                    await self._replicate_snapshot()
            try:
                await asyncio.wait_for(self.stop_event.wait(), HEARTBEAT_SECONDS)
            except TimeoutError:
                pass

    async def _election_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.cfg.enrolled:
                now = time.time()
                members = await asyncio.to_thread(self.store.members)
                alive: list[Member] = []
                for member in members:
                    if member.node_id == self.cfg.node_id or now - member.last_seen <= PEER_DEAD_SECONDS:
                        member.status = NodeStatus.ALIVE
                        alive.append(member)
                    else:
                        member.status = NodeStatus.DEAD
                    await asyncio.to_thread(self.store.put_member, member)
                new_leader = min((m.node_id for m in alive), default=self.cfg.node_id)
                current = await asyncio.to_thread(self.store.get, "leader_id")
                if new_leader != current:
                    await asyncio.to_thread(self.store.set, "leader_id", new_leader)
                    epoch = int(await asyncio.to_thread(self.store.get, "epoch", 0)) + 1
                    await asyncio.to_thread(self.store.set, "epoch", epoch)
                    if new_leader == self.cfg.node_id:
                        await self._replicate_snapshot()
            try:
                await asyncio.wait_for(self.stop_event.wait(), 1.0)
            except TimeoutError:
                pass

    async def is_leader(self) -> bool:
        return (await asyncio.to_thread(self.store.get, "leader_id")) == self.cfg.node_id

    async def leader_endpoint(self) -> dict[str, Any] | None:
        leader = await asyncio.to_thread(self.store.get, "leader_id")
        member = await self._member_for(str(leader)) if leader else None
        return None if member is None else {"node_id": member.node_id, "host": member.host, "port": member.port}

    async def submit_job(self, kind: str, parameters: dict[str, Any]) -> Job:
        if await self.is_leader():
            return await self._submit_job(kind, parameters, self.cfg.node_id)
        endpoint = await self.leader_endpoint()
        if not endpoint:
            raise RuntimeError("cluster has no reachable leader")
        response = await request(endpoint["host"], int(endpoint["port"]), self._signed("submit_job", job_kind=kind, parameters=parameters), timeout=10.0)
        if response["kind"] == "redirect" and response.get("leader"):
            target = response["leader"]
            response = await request(target["host"], int(target["port"]), self._signed("submit_job", job_kind=kind, parameters=parameters), timeout=10.0)
        if response["kind"] != "job_submitted":
            raise RuntimeError(response.get("error", "job submission failed"))
        return Job(**response["job"])

    async def _submit_job(self, kind: str, parameters: dict[str, Any], submitted_by: str) -> Job:
        implementation = JOBS.get(kind)
        if implementation is None:
            raise ValueError(f"unknown job kind {kind}")
        job = Job(str(uuid.uuid4()), kind, parameters, time.time(), JobStatus.RUNNING, submitted_by=submitted_by)
        members = [m for m in await asyncio.to_thread(self.store.members) if m.status == NodeStatus.ALIVE]
        units = await asyncio.to_thread(implementation.split, job.job_id, parameters, max(4, len(members) * 4))
        await asyncio.to_thread(self.store.put_job, job)
        for unit in units:
            await asyncio.to_thread(self.store.put_work, unit)
        await self._replicate_snapshot()
        return job

    async def _lease_work(self, worker_id: str) -> WorkUnit | None:
        now = time.time()
        for unit in await asyncio.to_thread(self.store.work):
            if unit.status == WorkStatus.LEASED and unit.lease_until is not None and unit.lease_until < now:
                unit.status, unit.lease_owner, unit.lease_until = WorkStatus.AVAILABLE, None, None
                await asyncio.to_thread(self.store.put_work, unit)
            if unit.status == WorkStatus.AVAILABLE:
                unit.status, unit.lease_owner, unit.lease_until = WorkStatus.LEASED, worker_id, now + DEFAULT_LEASE_SECONDS
                await asyncio.to_thread(self.store.put_work, unit)
                return unit
        return None

    async def _accept_result(self, worker_id: str, work_id: str, result: dict[str, Any]) -> bool:
        unit = next((u for u in await asyncio.to_thread(self.store.work) if u.work_id == work_id), None)
        if unit is None or unit.status == WorkStatus.COMPLETE:
            return False
        job = await asyncio.to_thread(self.store.job, unit.job_id)
        if job is None:
            return False
        implementation = JOBS[job.kind]
        if not await asyncio.to_thread(implementation.verify, unit.payload, result):
            return False
        unit.result = result
        unit.result_hash = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        unit.status, unit.lease_owner, unit.lease_until = WorkStatus.COMPLETE, worker_id, None
        await asyncio.to_thread(self.store.put_work, unit)
        work = await asyncio.to_thread(self.store.work, job.job_id)
        if work and all(u.status == WorkStatus.COMPLETE and u.result is not None for u in work):
            job.result = await asyncio.to_thread(implementation.reduce, job.parameters, [u.result for u in work if u.result is not None])
            job.status = JobStatus.COMPLETE
            await asyncio.to_thread(self.store.put_job, job)
        await self._replicate_snapshot()
        return True

    async def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.cfg.enrolled:
                try:
                    if await self.is_leader():
                        unit = await self._lease_work(self.cfg.node_id)
                    else:
                        endpoint = await self.leader_endpoint()
                        unit = None
                        if endpoint:
                            response = await request(endpoint["host"], int(endpoint["port"]), self._signed("lease_request"), timeout=3.0)
                            if response.get("kind") == "lease_result" and response.get("work"):
                                unit = WorkUnit(**response["work"])
                    if unit:
                        job = await asyncio.to_thread(self.store.job, unit.job_id)
                        if job:
                            implementation = JOBS[job.kind]
                            started = time.perf_counter()
                            result = await asyncio.to_thread(implementation.compute, unit.payload)
                            await self._record_capacity(1.0 / max(1e-6, time.perf_counter() - started))
                            if await self.is_leader():
                                await self._accept_result(self.cfg.node_id, unit.work_id, result)
                            else:
                                endpoint = await self.leader_endpoint()
                                if endpoint:
                                    await request(endpoint["host"], int(endpoint["port"]), self._signed("work_result", work_id=unit.work_id, result=result), timeout=20.0)
                            continue
                except Exception:
                    pass
            try:
                await asyncio.wait_for(self.stop_event.wait(), 0.25)
            except TimeoutError:
                pass

    async def _record_capacity(self, sample: float) -> None:
        member = await self._member_for(self.cfg.node_id)
        if member:
            member.capacity = sample if member.capacity <= 0 else member.capacity * 0.8 + sample * 0.2
            member.last_seen = time.time()
            await asyncio.to_thread(self.store.put_member, member)

    async def _replicate_snapshot(self) -> None:
        if not self.cfg.enrolled or not await self.is_leader():
            return
        snapshot = (await asyncio.to_thread(self.store.snapshot)).to_dict()
        tasks = [asyncio.create_task(request(member.host, member.port, self._signed("snapshot", snapshot=snapshot), timeout=3.0)) for member in await asyncio.to_thread(self.store.members) if member.node_id != self.cfg.node_id and member.status != NodeStatus.DEAD]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
