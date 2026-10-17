"""Software-only device-binding experiment for synthetic agent clones.

This is NOT hardware attestation or non-exportability. A trusted coordinator grants
scoped authority, an independent effect gateway checks a device-specific signature,
and an agent snapshot contains no signing keys. The HMAC verification secret can
also sign, so this only models a limited software-key-possession adversary.

A clone may copy the entire portable agent snapshot and assert any identity; it
may not access the origin's device-specific signing key, the gateway's trusted
configuration or the authority that issues grants. This adversary is *assumed*,
not enforced by a TPM, TEE, kernel sandbox, or this Python process.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import asdict, dataclass
from typing import Protocol

_ID = re.compile(r"[A-Za-z][A-Za-z0-9._:-]{0,127}\Z")
_DOMAIN = b"agent-movement/device-binding/software-only/v0\n"


class BindingDenied(ValueError):
    """A test gateway denial; "reason" has a stable machine-readable meaning."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class SignatureVerifier(Protocol):
    """Verifier adapter; an actual hardware backend would need its own validation."""

    def verify(self, message: bytes, signature: bytes) -> bool: ...


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise BindingDenied("invalid_identifier")
    return value


def _canonical(value: dict[str, str | int]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


@dataclass(frozen=True)
class PortableAgent:
    """Only this synthetic public task data is copied; credentials never enter it."""

    task_id: str
    definition_id: str
    text: str

    def snapshot(self) -> dict[str, str]:
        _identifier(self.task_id)
        _identifier(self.definition_id)
        if len(self.text.encode("utf-8")) > 2048:
            raise BindingDenied("snapshot_too_large")
        return {"schema": "device-binding-v0", "task_id": self.task_id,
                "definition_id": self.definition_id, "text": self.text}

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, str]) -> PortableAgent:
        if set(snapshot) != {"schema", "task_id", "definition_id", "text"} or snapshot["schema"] != "device-binding-v0":
            raise BindingDenied("invalid_snapshot")
        agent = cls(snapshot["task_id"], snapshot["definition_id"], snapshot["text"])
        agent.snapshot()  # validate values on both sides
        return agent

    def compute(self) -> int:
        return len(self.text.split())


class LocalSoftwareKey:
    """EXTRACTABLE HMAC key. It deliberately does not simulate genuine hardware protection."""

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("software test key must be 32 bytes")
        self._key = key

    @classmethod
    def generate(cls) -> LocalSoftwareKey:
        return cls(secrets.token_bytes(32))

    @classmethod
    def from_fixture_hex(cls, value: str) -> LocalSoftwareKey:
        return cls(bytes.fromhex(value))

    def export_fixture_hex(self) -> str:
        """For demo subprocess provisioning only. Never a hardware/non-exportable guarantee."""
        return self._key.hex()

    def sign(self, message: bytes) -> bytes:
        return hmac.new(self._key, _DOMAIN + message, hashlib.sha256).digest()

    def verifier(self) -> SignatureVerifier:
        # Symmetric-key verification: the gateway also possesses signing power.
        return LocalSoftwareKey(self._key)

    def verify(self, message: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(message), signature)


@dataclass(frozen=True)
class Grant:
    grant_id: str
    task_id: str
    agent_instance_id: str
    device_id: str
    audience: str
    action: str
    expires_at: int
    epoch: int


@dataclass(frozen=True)
class Challenge:
    """A gateway-minted single-use request. All attributes are covered by the proof."""

    nonce: str
    grant_id: str
    task_id: str
    agent_instance_id: str
    device_id: str
    audience: str
    action: str
    effect_id: str
    epoch: int
    expires_at: int

    def signed_bytes(self) -> bytes:
        return _canonical(asdict(self))


class DeviceEffectGateway:
    """Synthetic tool-side enforcement: not a remotely accessible production service.

    Only a trusted coordinator may call register_device, issue_grant,
    fence or revoke. The exposed agent API is challenge/commit.
    The test harness separates these roles; it does not authenticate admin calls.
    """

    def __init__(self, challenge_ttl: int = 15):
        if not 1 <= challenge_ttl <= 60:
            raise ValueError("challenge_ttl out of bounds")
        self._ttl = challenge_ttl
        self._devices: dict[str, SignatureVerifier] = {}
        self._grants: dict[str, Grant] = {}
        self._epochs: dict[str, int] = {}
        self._revoked: set[str] = set()
        self._pending: dict[str, Challenge] = {}
        self._effects: set[tuple[str, str]] = set()

    def register_device(self, device_id: str, verifier: SignatureVerifier) -> None:
        if _identifier(device_id) in self._devices:
            raise BindingDenied("device_already_registered")
        self._devices[device_id] = verifier

    def issue_grant(self, grant_id: str, task_id: str, agent_instance_id: str,
                    device_id: str, audience: str, action: str, expires_at: int,
                    now: int) -> Grant:
        for value in (grant_id, task_id, agent_instance_id, device_id, audience, action):
            _identifier(value)
        if device_id not in self._devices:
            raise BindingDenied("unknown_device")
        if grant_id in self._grants:
            raise BindingDenied("duplicate_grant")
        if type(expires_at) is not int or expires_at <= now:
            raise BindingDenied("invalid_expiry")
        epoch = self._epochs.setdefault(task_id, 1)
        grant = Grant(grant_id, task_id, agent_instance_id, device_id, audience, action, expires_at, epoch)
        self._grants[grant_id] = grant
        return grant

    def fence(self, task_id: str) -> int:
        """Trusted coordinator advances the epoch, invalidating all older task grants."""
        _identifier(task_id)
        epoch = self._epochs.get(task_id, 0) + 1
        self._epochs[task_id] = epoch
        return epoch

    def revoke(self, grant_id: str) -> None:
        if grant_id not in self._grants:
            raise BindingDenied("unknown_grant")
        self._revoked.add(grant_id)

    def _active(self, grant_id: str, now: int) -> Grant:
        grant = self._grants.get(grant_id)
        if grant is None:
            raise BindingDenied("unknown_grant")
        if grant_id in self._revoked:
            raise BindingDenied("revoked_grant")
        if now >= grant.expires_at:
            raise BindingDenied("expired_grant")
        if grant.epoch != self._epochs.get(grant.task_id):
            raise BindingDenied("stale_epoch")
        return grant

    def challenge(self, grant_id: str, agent_instance_id: str, device_id: str,
                  audience: str, action: str, effect_id: str, now: int) -> Challenge:
        for value in (agent_instance_id, device_id, audience, action, effect_id):
            _identifier(value)
        grant = self._active(grant_id, now)
        if (agent_instance_id, device_id, audience, action) != (
            grant.agent_instance_id, grant.device_id, grant.audience, grant.action
        ):
            raise BindingDenied("binding_mismatch")
        result = Challenge(secrets.token_hex(16), grant_id, grant.task_id, agent_instance_id,
                           device_id, audience, action, effect_id, grant.epoch,
                           min(grant.expires_at, now + self._ttl))
        self._pending[result.nonce] = result
        return result

    def commit(self, challenge: Challenge, signature: bytes, now: int) -> dict[str, str]:
        """Independently verify fresh device proof before committing a fake effect.

        A nonce is consumed on the FIRST attempt, even if verification fails.
        No external effect is performed. There is no distributed persistence here.
        """
        pinned = self._pending.pop(challenge.nonce, None)
        if pinned is None or pinned != challenge:
            raise BindingDenied("challenge_unknown_or_modified")
        if now >= challenge.expires_at:
            raise BindingDenied("expired_challenge")
        grant = self._active(challenge.grant_id, now)
        if (challenge.agent_instance_id, challenge.device_id, challenge.audience,
                challenge.action, challenge.task_id, challenge.epoch) != (
                grant.agent_instance_id, grant.device_id, grant.audience, grant.action,
                grant.task_id, grant.epoch):
            raise BindingDenied("binding_mismatch")
        if not self._devices[grant.device_id].verify(challenge.signed_bytes(), signature):
            raise BindingDenied("signature_invalid")
        effect = (grant.task_id, challenge.effect_id)
        if effect in self._effects:
            raise BindingDenied("duplicate_effect")
        self._effects.add(effect)
        return {"status": "synthetic_effect_committed", "task_id": grant.task_id,
                "effect_id": challenge.effect_id, "device_id": grant.device_id}

    @property
    def effect_count(self) -> int:
        return len(self._effects)
