from __future__ import annotations

import asyncio
import hashlib
import json
import socket
from dataclasses import dataclass
from typing import AsyncIterator

from .constants import BLE_LOCAL_NAME, DEFAULT_DISCOVERY_PORT, SERVICE_UUID


@dataclass(slots=True, frozen=True)
class PeerBeacon:
    node_id: str
    cluster_tag: str
    host: str
    port: int
    source: str


def cluster_tag(cluster_id: str | None) -> str:
    return hashlib.sha256((cluster_id or "unenrolled").encode()).hexdigest()[:12]


class DiscoveryBackend:
    async def beacons(self) -> AsyncIterator[PeerBeacon]:
        raise NotImplementedError

    async def run_advertiser(self, stop: asyncio.Event) -> None:
        raise NotImplementedError


class UdpDiscovery(DiscoveryBackend):
    """LAN fallback and test-friendly discovery path.

    BLE is the preferred physical discovery mechanism. UDP allows development
    on machines without BlueZ and gives nodes a second way to heal after Wi-Fi
    association.
    """

    def __init__(self, node_id: str, cluster_id: str | None, control_port: int, port: int = DEFAULT_DISCOVERY_PORT) -> None:
        self.node_id = node_id
        self.tag = cluster_tag(cluster_id)
        self.control_port = control_port
        self.port = port
        self.queue: asyncio.Queue[PeerBeacon] = asyncio.Queue()

    async def run_advertiser(self, stop: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        payload = json.dumps({"pipy": 1, "node_id": self.node_id, "cluster_tag": self.tag, "port": self.control_port}).encode()
        while not stop.is_set():
            try:
                await loop.sock_sendto(sock, payload, ("255.255.255.255", self.port))
            except OSError:
                pass
            try:
                await asyncio.wait_for(stop.wait(), 2.0)
            except TimeoutError:
                pass
        sock.close()

    async def listen(self, stop: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.port))
        sock.setblocking(False)
        try:
            while not stop.is_set():
                try:
                    raw, address = await asyncio.wait_for(loop.sock_recvfrom(sock, 4096), 1.0)
                except TimeoutError:
                    continue
                try:
                    data = json.loads(raw)
                    if data.get("pipy") != 1 or data.get("node_id") == self.node_id:
                        continue
                    await self.queue.put(PeerBeacon(str(data["node_id"]), str(data["cluster_tag"]), address[0], int(data["port"]), "udp"))
                except Exception:
                    continue
        finally:
            sock.close()

    async def beacons(self) -> AsyncIterator[PeerBeacon]:
        while True:
            yield await self.queue.get()


class BleDiscovery(DiscoveryBackend):
    """BLE scanner plus optional BlueZ advertisement."""

    def __init__(self, node_id: str, cluster_id: str | None, control_port: int) -> None:
        self.node_id = node_id
        self.tag = cluster_tag(cluster_id)
        self.control_port = control_port
        self.queue: asyncio.Queue[PeerBeacon] = asyncio.Queue()

    async def scan(self, stop: asyncio.Event) -> None:
        try:
            from bleak import BleakScanner
        except Exception:
            return

        def detected(device: object, advertisement: object) -> None:
            try:
                service_uuids = [u.lower() for u in getattr(advertisement, "service_uuids", [])]
                if SERVICE_UUID.lower() not in service_uuids:
                    return
                name = getattr(advertisement, "local_name", None) or getattr(device, "name", None) or ""
                if not str(name).startswith(BLE_LOCAL_NAME):
                    return
                service_data = getattr(advertisement, "service_data", {})
                raw = service_data.get(SERVICE_UUID.lower()) or service_data.get(SERVICE_UUID)
                if not raw:
                    return
                data = json.loads(bytes(raw).decode())
                if data.get("node_id") == self.node_id:
                    return
                host = str(data.get("host") or "")
                if host:
                    self.queue.put_nowait(PeerBeacon(str(data["node_id"]), str(data["cluster_tag"]), host, int(data["port"]), "ble"))
            except Exception:
                return

        scanner = BleakScanner(detection_callback=detected, service_uuids=[SERVICE_UUID])
        try:
            await scanner.start()
            await stop.wait()
        except Exception:
            return
        finally:
            try:
                await scanner.stop()
            except Exception:
                pass

    async def run_advertiser(self, stop: asyncio.Event) -> None:
        try:
            from dbus_next.aio import MessageBus
            from dbus_next.service import ServiceInterface, dbus_property, method
            from dbus_next.constants import PropertyAccess, BusType
            from dbus_next import Variant
        except Exception:
            return
        import socket as _socket

        payload = json.dumps({"node_id": self.node_id, "cluster_tag": self.tag, "host": _socket.gethostname(), "port": self.control_port}, separators=(",", ":")).encode()

        class Advertisement(ServiceInterface):
            def __init__(self) -> None:
                super().__init__("org.bluez.LEAdvertisement1")

            @method()
            def Release(self) -> "":
                return None

            @dbus_property(access=PropertyAccess.READ)
            def Type(self) -> "s":
                return "peripheral"

            @dbus_property(access=PropertyAccess.READ)
            def ServiceUUIDs(self) -> "as":
                return [SERVICE_UUID]

            @dbus_property(access=PropertyAccess.READ)
            def LocalName(self) -> "s":
                return BLE_LOCAL_NAME

            @dbus_property(access=PropertyAccess.READ)
            def ServiceData(self) -> "a{sv}":
                return {SERVICE_UUID: Variant("ay", payload)}

        try:
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            intro = await bus.introspect("org.bluez", "/org/bluez/hci0")
            obj = bus.get_proxy_object("org.bluez", "/org/bluez/hci0", intro)
            manager = obj.get_interface("org.bluez.LEAdvertisingManager1")
            path = f"/org/pipy/advertisement/{self.node_id}"
            ad = Advertisement()
            bus.export(path, ad)
            await manager.call_register_advertisement(path, {})
            await stop.wait()
            await manager.call_unregister_advertisement(path)
            bus.disconnect()
        except Exception:
            return

    async def beacons(self) -> AsyncIterator[PeerBeacon]:
        while True:
            yield await self.queue.get()
