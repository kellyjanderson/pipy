from __future__ import annotations

import asyncio
import os
import socket
import time
from typing import Any

from .bootstrap import decode_bundle
from .crypto import Ephemeral, decrypt, encrypt, mac, new_unity_key, sign, token_hash, verify
from .discovery import cluster_tag
from .models import Member
from .protocol import ProtocolError, message, read_message, request, write_message


class AdmissionMixin:
    async def _handle_admission(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        hello: dict[str, Any],
    ) -> None:
        if (
            not self.cfg.enrolled
            or not self.cfg.cluster_private
            or not self.cfg.cluster_public
            or not self.cfg.unity_key
        ):
            await write_message(
                writer, message("admission_reject", error="node cannot admit members")
            )
            return

        token_id = str(hello.get("token_id") or "")
        records = {
            record["token_id"]: record
            for record in await asyncio.to_thread(self.store.enrollments)
        }
        record = records.get(token_id)
        if not record or record["used"]:
            await write_message(
                writer,
                message("admission_reject", error="invalid or used enrollment capability"),
            )
            return

        unsigned = {key: value for key, value in hello.items() if key != "signature"}
        if not verify(
            str(hello["node_public"]),
            unsigned,
            str(hello.get("signature") or ""),
        ):
            await write_message(
                writer, message("admission_reject", error="invalid node identity proof")
            )
            return

        eph = Ephemeral.create()
        nonce = os.urandom(16)
        transcript = {
            "cluster_id": self.cfg.cluster_id,
            "join_node_id": hello["node_id"],
            "join_ephemeral": hello["ephemeral"],
            "member_node_id": self.cfg.node_id,
            "member_ephemeral": eph.public,
            "server_nonce": nonce.hex(),
        }
        await write_message(
            writer,
            message(
                "admission_challenge",
                member_node_id=self.cfg.node_id,
                member_public=self.cfg.node_public,
                member_ephemeral=eph.public,
                server_nonce=nonce.hex(),
                cluster_id=self.cfg.cluster_id,
                cluster_signature=sign(self.cfg.cluster_private, transcript),
            ),
        )

        session_key = eph.derive(str(hello["ephemeral"]), salt=nonce)
        proof = await read_message(reader)
        if proof["kind"] != "admission_proof":
            raise ProtocolError("expected admission proof")
        proof_payload = decrypt(
            session_key,
            dict(proof["envelope"]),
            b"pipy-admission-proof",
        )
        secret = str(proof_payload.get("secret") or "")
        if (
            proof_payload.get("token_id") != token_id
            or proof_payload.get("server_nonce") != nonce.hex()
            or record["token_hash"] != token_hash(secret)
        ):
            raise ProtocolError("invalid admission proof")
        if not await asyncio.to_thread(
            self.store.consume_enrollment,
            token_id,
            token_hash(secret),
        ):
            raise ProtocolError("enrollment capability already consumed")

        old_unity = self.cfg.unity_key
        new_unity = new_unity_key()
        now = time.time()
        peername = writer.get_extra_info("peername")
        peer_host = str(peername[0]) if peername else "127.0.0.1"
        member = Member(
            str(hello["node_id"]),
            str(hello["node_public"]),
            peer_host,
            int(hello["port"]),
            str(hello.get("hostname") or hello["node_id"]),
            now,
            now,
        )
        await asyncio.to_thread(self.store.put_member, member)

        self.cfg.unity_key = new_unity
        self.cfg.save(self.paths.config)
        await self._replicate_unity_rotation(
            old_unity,
            new_unity,
            exclude={member.node_id},
        )

        certificate_body = {
            "cluster_id": self.cfg.cluster_id,
            "node_id": member.node_id,
            "node_public": member.public_key,
            "joined_at": now,
        }
        admission = {
            "cluster_id": self.cfg.cluster_id,
            "cluster_public": self.cfg.cluster_public,
            "cluster_private": self.cfg.cluster_private,
            "unity_key": new_unity,
            "wifi_ssid": self.cfg.wifi_ssid,
            "wifi_password": self.cfg.wifi_password,
            "membership_certificate": {
                "body": certificate_body,
                "signature": sign(self.cfg.cluster_private, certificate_body),
            },
            "snapshot": (await asyncio.to_thread(self.store.snapshot)).to_dict(),
        }
        await write_message(
            writer,
            message(
                "admission_grant",
                envelope=encrypt(
                    session_key,
                    admission,
                    b"pipy-admission-grant",
                ),
            ),
        )

        ack = await read_message(reader)
        if ack["kind"] != "admission_ack":
            raise ProtocolError("expected admission acknowledgment")
        ack_payload = decrypt(
            session_key,
            dict(ack["envelope"]),
            b"pipy-admission-ack",
        )
        if ack_payload.get("node_id") != member.node_id:
            raise ProtocolError("invalid admission acknowledgment")
        await write_message(
            writer,
            message("admission_complete", cluster_id=self.cfg.cluster_id),
        )
        await self._replicate_snapshot()

    async def _join_from_bundle_loop(self) -> None:
        bundle = decode_bundle(self.cfg.bootstrap_bundle or "")
        while not self.cfg.enrolled and not self.stop_event.is_set():
            candidates: list[tuple[str, int]] = []
            if bundle.get("seed_host"):
                candidates.append(
                    (
                        str(bundle["seed_host"]),
                        int(bundle.get("seed_port", self.cfg.port)),
                    )
                )
            candidates.extend(
                (member.host, member.port)
                for member in await asyncio.to_thread(self.store.members)
                if member.node_id != self.cfg.node_id
            )
            for host, port in candidates:
                try:
                    await self._join_member(host, port, bundle)
                    return
                except Exception:
                    continue
            try:
                await asyncio.wait_for(self.stop_event.wait(), 2.0)
            except TimeoutError:
                pass

    async def _join_member(
        self,
        host: str,
        port: int,
        bundle: dict[str, Any],
    ) -> None:
        reader, writer = await asyncio.open_connection(host, port)
        try:
            eph = Ephemeral.create()
            hello = message(
                "admission_hello",
                token_id=bundle["token_id"],
                node_id=self.cfg.node_id,
                node_public=self.cfg.node_public,
                ephemeral=eph.public,
                port=self.cfg.port,
                hostname=socket.gethostname(),
            )
            hello["signature"] = sign(
                self.cfg.node_private,
                {key: value for key, value in hello.items() if key != "signature"},
            )
            await write_message(writer, hello)

            challenge = await read_message(reader)
            if challenge["kind"] != "admission_challenge":
                raise RuntimeError(challenge.get("error", "admission rejected"))
            transcript = {
                "cluster_id": challenge["cluster_id"],
                "join_node_id": self.cfg.node_id,
                "join_ephemeral": eph.public,
                "member_node_id": challenge["member_node_id"],
                "member_ephemeral": challenge["member_ephemeral"],
                "server_nonce": challenge["server_nonce"],
            }
            if (
                challenge["cluster_id"] != bundle["cluster_id"]
                or not verify(
                    str(bundle["cluster_public"]),
                    transcript,
                    str(challenge["cluster_signature"]),
                )
            ):
                raise RuntimeError("cluster identity verification failed")

            session_key = eph.derive(
                str(challenge["member_ephemeral"]),
                salt=bytes.fromhex(str(challenge["server_nonce"])),
            )
            proof = {
                "token_id": bundle["token_id"],
                "secret": bundle["secret"],
                "server_nonce": challenge["server_nonce"],
                "node_id": self.cfg.node_id,
            }
            await write_message(
                writer,
                message(
                    "admission_proof",
                    envelope=encrypt(
                        session_key,
                        proof,
                        b"pipy-admission-proof",
                    ),
                ),
            )

            grant = await read_message(reader)
            if grant["kind"] != "admission_grant":
                raise RuntimeError(grant.get("error", "admission grant missing"))
            admission = decrypt(
                session_key,
                dict(grant["envelope"]),
                b"pipy-admission-grant",
            )
            cert = admission["membership_certificate"]
            if not verify(
                str(bundle["cluster_public"]),
                cert["body"],
                cert["signature"],
            ):
                raise RuntimeError("invalid membership certificate")

            self.cfg.cluster_id = str(admission["cluster_id"])
            self.cfg.cluster_public = str(admission["cluster_public"])
            self.cfg.cluster_private = str(admission["cluster_private"])
            self.cfg.unity_key = str(admission["unity_key"])
            self.cfg.wifi_ssid = admission.get("wifi_ssid")
            self.cfg.wifi_password = admission.get("wifi_password")
            self.cfg.bootstrap_bundle = None
            self.cfg.save(self.paths.config)

            await asyncio.to_thread(
                self.store.apply_snapshot,
                admission["snapshot"],
            )
            await self._refresh_self_member()
            await write_message(
                writer,
                message(
                    "admission_ack",
                    envelope=encrypt(
                        session_key,
                        {"node_id": self.cfg.node_id},
                        b"pipy-admission-ack",
                    ),
                ),
            )
            complete = await read_message(reader)
            if complete["kind"] != "admission_complete":
                raise RuntimeError("admission did not complete")
            self.udp.tag = cluster_tag(self.cfg.cluster_id)
            self.ble.tag = cluster_tag(self.cfg.cluster_id)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _replicate_unity_rotation(
        self,
        old_key: str,
        new_key: str,
        *,
        exclude: set[str],
    ) -> None:
        body = {
            "new_unity_key": new_key,
            "epoch": int(await asyncio.to_thread(self.store.get, "epoch", 0)) + 1,
            "issued_by": self.cfg.node_id,
        }
        tasks = []
        for member in await asyncio.to_thread(self.store.members):
            if member.node_id == self.cfg.node_id or member.node_id in exclude:
                continue
            tasks.append(
                asyncio.create_task(
                    request(
                        member.host,
                        member.port,
                        self._signed(
                            "unity_rotate",
                            body=body,
                            mac=mac(old_key, body),
                        ),
                        timeout=3.0,
                    )
                )
            )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
