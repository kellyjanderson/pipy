from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def new_ed25519() -> tuple[str, str]:
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return b64(private_raw), b64(public_raw)


def public_from_private(private_b64: str) -> str:
    private = Ed25519PrivateKey.from_private_bytes(unb64(private_b64))
    return b64(private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def sign(private_b64: str, payload: Any) -> str:
    return b64(Ed25519PrivateKey.from_private_bytes(unb64(private_b64)).sign(canonical(payload)))


def verify(public_b64: str, payload: Any, signature_b64: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(unb64(public_b64)).verify(unb64(signature_b64), canonical(payload))
        return True
    except Exception:
        return False


def node_id(public_b64: str) -> str:
    return hashlib.sha256(unb64(public_b64)).hexdigest()[:16]


def token_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def new_token() -> str:
    return b64(os.urandom(32))


def new_unity_key() -> str:
    return b64(os.urandom(32))


@dataclass(slots=True)
class Ephemeral:
    private: X25519PrivateKey
    public: str

    @classmethod
    def create(cls) -> "Ephemeral":
        private = X25519PrivateKey.generate()
        public = b64(private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        return cls(private, public)

    def derive(self, peer_public: str, *, salt: bytes, info: bytes = b"pipy-admission-v1") -> bytes:
        shared = self.private.exchange(X25519PublicKey.from_public_bytes(unb64(peer_public)))
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(shared)


def encrypt(key: bytes, payload: Any, aad: bytes = b"") -> dict[str, str]:
    nonce = os.urandom(12)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, canonical(payload), aad)
    return {"nonce": b64(nonce), "ciphertext": b64(ciphertext)}


def decrypt(key: bytes, envelope: dict[str, str], aad: bytes = b"") -> Any:
    raw = ChaCha20Poly1305(key).decrypt(unb64(envelope["nonce"]), unb64(envelope["ciphertext"]), aad)
    return json.loads(raw)


def mac(key_b64: str, payload: Any) -> str:
    return b64(hmac.new(unb64(key_b64), canonical(payload), hashlib.sha256).digest())


def check_mac(key_b64: str, payload: Any, value: str) -> bool:
    return hmac.compare_digest(mac(key_b64, payload), value)
