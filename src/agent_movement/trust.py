"""Synthetic, local-only peer trust model for pre-disclosure authorization (issue #8).

TEST/LAB KEYS ONLY. This is not a PKI, not X.509, not OAuth and not A2A. It keeps three
things apart that the PR #6 receiver conflated in one self-declared ``agent_id`` string:

* **peer identity** -- proof of possession of a key that a *pinned* synthetic test CA
  bound to an agent ID in a signed descriptor ("card");
* **claimed agent metadata** -- endpoint, capabilities and schemas inside that card. The
  CA endorses the *binding*; nothing here is evidence of how the agent behaves;
* **user authorization** -- a grant signed by a *separate* synthetic user authority and
  scoped to actor, audience, task, capabilities, classification and a validity window
  (RFC 8693-like ``sub``/``act``/``aud`` semantics, not an RFC 8693 implementation).

Two signature backends share one interface:

* ``HS256`` (stdlib ``hmac``): the dependency-free default. Symmetric -- every holder of a
  verification key can also sign with it, so it only models *outsider* attackers.
* ``Ed25519`` (optional ``cryptography`` extra): asymmetric; verifiers cannot forge.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Iterable

from .core import ContractError, PolicyDenied, _fields, _id, canonical

PEER_SCHEMA_VERSION = "0.1.0-peer-draft"
HS256 = "HS256"
ED25519 = "Ed25519"
TASK_KINDS = frozenset({"word_count", "sha256"})
CLASSIFICATIONS = frozenset({"synthetic", "public"})
SEALED_FIELDS = {"alg", "kid", "payload", "sig"}
_DOMAIN = b"agent-movement/peer/v0\n"
_PURPOSES = frozenset({"agent-card", "grant", "revocation", "preflight", "admission",
                       "delivery", "receipt"})
# Loopback or in-process only: a card can never point a sender at an arbitrary host (SSRF).
_ENDPOINT = re.compile(r"(http://127\.0\.0\.1:[1-9][0-9]{0,4}|local://[A-Za-z0-9._-]{1,64})\Z")
_B64 = re.compile(r"[A-Za-z0-9_-]{0,4096}\Z")
_MAX_TIME = 2 ** 40


class UnsupportedSchema(ContractError):
    """Peer schema version is not one this participant implements."""


class TrustDenied(PolicyDenied):
    """Denial with a machine-readable reason, recorded only in sanitized local traces."""

    status = 403

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Unauthenticated(TrustDenied):
    """Peer identity, descriptor or message signature could not be verified."""

    status = 401


class Unauthorized(TrustDenied):
    """Peer is authenticated but the user grant / receiver policy does not allow this."""

    status = 403


class DisclosureBlocked(TrustDenied):
    """Sender-side guard refused to transmit bytes containing held secret material."""


def b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64d(text: Any, label: str = "base64 field") -> bytes:
    if not isinstance(text, str) or not _B64.fullmatch(text):
        raise ContractError(f"invalid {label}")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except ValueError as exc:
        raise ContractError(f"invalid {label}") from exc


def _time(value: Any, label: str) -> int:
    if type(value) is not int or not 0 <= value < _MAX_TIME:
        raise ContractError(f"invalid {label}")
    return value


def _id_list(value: Any, label: str, allowed: frozenset[str] | None = None) -> frozenset[str]:
    if not isinstance(value, list) or not 0 < len(value) <= 16 or len(set(value)) != len(value):
        raise ContractError(f"invalid {label}")
    for item in value:
        _id(item, label)
        if allowed is not None and item not in allowed:
            raise ContractError(f"unknown value in {label}")
    return frozenset(value)


def endpoint(value: Any) -> str:
    if not isinstance(value, str) or not _ENDPOINT.fullmatch(value):
        raise ContractError("endpoint must be loopback http or local://")
    return value


def safe_id(value: Any) -> str | None:
    """Return value only if it is a syntactically valid ID; used for sanitized traces."""
    try:
        return _id(value, "id")
    except ContractError:
        return None


# ---------------------------------------------------------------------------- keys


class HmacKey:
    """Symmetric HS256 test key. Any holder can both sign and verify (see limitations)."""

    alg = HS256

    def __init__(self, kid: str, secret: bytes):
        _id(kid, "kid")
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ContractError("HMAC test key must be at least 32 bytes")
        self.kid = kid
        self._secret = secret

    @classmethod
    def generate(cls, kid: str) -> "HmacKey":
        return cls(kid, secrets.token_bytes(32))

    def sign(self, data: bytes) -> bytes:
        return hmac.new(self._secret, data, hashlib.sha256).digest()

    def verify(self, data: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(data), signature)

    def public_value(self) -> str:
        return ""  # nothing public: verifiers must be provisioned out of band

    def verifier(self) -> "HmacKey":
        return self  # symmetric: the verifier necessarily holds signing power

    def secret_forms(self) -> tuple[bytes, ...]:
        return (self._secret, b64e(self._secret).encode("ascii"), self._secret.hex().encode("ascii"))

    def export(self, private: bool = True) -> dict[str, str]:
        return {"alg": HS256, "kid": self.kid, "secret": b64e(self._secret)}

    def __repr__(self) -> str:
        return f"HmacKey(kid={self.kid!r}, secret=<redacted>)"


def ed25519_available() -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
    except ImportError:
        return False
    return True


class Ed25519Key:
    """Ed25519 key via the optional ``cryptography`` extra; public-only instances verify."""

    alg = ED25519

    def __init__(self, kid: str, private: Any = None, public: Any = None):
        _id(kid, "kid")
        self.kid = kid
        self._private = private
        self._public = public if public is not None else private.public_key()

    @classmethod
    def generate(cls, kid: str) -> "Ed25519Key":
        from cryptography.hazmat.primitives.asymmetric import ed25519
        return cls(kid, private=ed25519.Ed25519PrivateKey.generate())

    @classmethod
    def from_public(cls, kid: str, public_b64: str) -> "Ed25519Key":
        from cryptography.hazmat.primitives.asymmetric import ed25519
        raw = b64d(public_b64, "public key")
        if len(raw) != 32:
            raise ContractError("invalid Ed25519 public key")
        return cls(kid, public=ed25519.Ed25519PublicKey.from_public_bytes(raw))

    @classmethod
    def from_private(cls, kid: str, private_b64: str) -> "Ed25519Key":
        from cryptography.hazmat.primitives.asymmetric import ed25519
        raw = b64d(private_b64, "private key")
        if len(raw) != 32:
            raise ContractError("invalid Ed25519 private key")
        return cls(kid, private=ed25519.Ed25519PrivateKey.from_private_bytes(raw))

    def _raw_private(self) -> bytes:
        from cryptography.hazmat.primitives import serialization
        return self._private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                           serialization.NoEncryption())

    def sign(self, data: bytes) -> bytes:
        if self._private is None:
            raise TypeError("public-only Ed25519 key cannot sign")
        return self._private.sign(data)

    def verify(self, data: bytes, signature: bytes) -> bool:
        from cryptography.exceptions import InvalidSignature
        try:
            self._public.verify(signature, data)
        except InvalidSignature:
            return False
        return True

    def public_value(self) -> str:
        from cryptography.hazmat.primitives import serialization
        return b64e(self._public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))

    def verifier(self) -> "Ed25519Key":
        return Ed25519Key(self.kid, public=self._public)

    def secret_forms(self) -> tuple[bytes, ...]:
        if self._private is None:
            return ()
        raw = self._raw_private()
        return (raw, b64e(raw).encode("ascii"), raw.hex().encode("ascii"))

    def export(self, private: bool = True) -> dict[str, str]:
        out = {"alg": ED25519, "kid": self.kid, "public": self.public_value()}
        if private and self._private is not None:
            out["private"] = b64e(self._raw_private())
        return out

    def __repr__(self) -> str:
        return f"Ed25519Key(kid={self.kid!r}, private={'<redacted>' if self._private else None})"


def generate_key(alg: str, kid: str) -> Any:
    if alg == HS256:
        return HmacKey.generate(kid)
    if alg == ED25519:
        return Ed25519Key.generate(kid)
    raise ContractError("unsupported key algorithm")


def import_key(data: Any) -> Any:
    if not isinstance(data, dict):
        raise ContractError("invalid key")
    if data.get("alg") == HS256:
        _fields(data, {"alg", "kid", "secret"}, "HS256 key")
        return HmacKey(data["kid"], b64d(data["secret"], "secret"))
    if data.get("alg") == ED25519:
        if "private" in data:
            _fields(data, {"alg", "kid", "public", "private"}, "Ed25519 key")
            return Ed25519Key.from_private(data["kid"], data["private"])
        _fields(data, {"alg", "kid", "public"}, "Ed25519 key")
        return Ed25519Key.from_public(data["kid"], data["public"])
    raise ContractError("unsupported key algorithm")


# -------------------------------------------------------------- sealed messages


def _signing_input(purpose: str, payload: dict[str, Any]) -> bytes:
    if purpose not in _PURPOSES:
        raise ValueError("unknown signature purpose")
    # Domain separation: a signature for one purpose can never verify for another.
    return _DOMAIN + purpose.encode("ascii") + b"\n" + canonical(payload).encode("utf-8")


def seal(purpose: str, payload: dict[str, Any], key: Any) -> dict[str, Any]:
    return {"alg": key.alg, "kid": key.kid, "payload": payload,
            "sig": b64e(key.sign(_signing_input(purpose, payload)))}


def sealed_parts(sealed: Any, label: str) -> dict[str, Any]:
    s = _fields(sealed, SEALED_FIELDS, label)
    if s["alg"] not in (HS256, ED25519) or not isinstance(s["payload"], dict):
        raise ContractError(f"invalid {label}")
    _id(s["kid"], f"{label}.kid")
    return s


def unseal(purpose: str, sealed: Any, key: Any, reason: str = "bad_signature") -> dict[str, Any]:
    """Verify ``sealed`` against an already-resolved key; never trusts the embedded kid alone."""
    s = sealed_parts(sealed, purpose)
    if s["alg"] != key.alg or s["kid"] != key.kid:
        raise Unauthenticated("key_mismatch")
    try:
        signature = b64d(s["sig"], "signature")
    except ContractError as exc:
        raise Unauthenticated(reason) from exc
    if not key.verify(_signing_input(purpose, s["payload"]), signature):
        raise Unauthenticated(reason)
    return s["payload"]


# ------------------------------------------------------------------ trust store


@dataclass
class TrustStore:
    """What one participant pinned out of band. Nothing here is learned from a peer."""

    card_issuers: dict[str, Any]
    grant_issuers: dict[str, Any]
    peer_keys: dict[str, HmacKey] = field(default_factory=dict)  # HS256 only

    @classmethod
    def build(cls, card_issuers: Iterable[Any], grant_issuers: Iterable[Any],
              peer_keys: Iterable[HmacKey] = ()) -> "TrustStore":
        return cls({k.kid: k.verifier() for k in card_issuers},
                   {k.kid: k.verifier() for k in grant_issuers},
                   {k.kid: k for k in peer_keys})

    def export(self) -> dict[str, list[dict[str, str]]]:
        return {"card_issuers": [k.export(private=False) for k in self.card_issuers.values()],
                "grant_issuers": [k.export(private=False) for k in self.grant_issuers.values()],
                "peer_keys": [k.export() for k in self.peer_keys.values()]}

    @classmethod
    def from_dict(cls, data: Any) -> "TrustStore":
        d = _fields(data, {"card_issuers", "grant_issuers", "peer_keys"}, "trust store")
        return cls.build([import_key(k) for k in d["card_issuers"]],
                         [import_key(k) for k in d["grant_issuers"]],
                         [import_key(k) for k in d["peer_keys"]])


def _resolve(keys: dict[str, Any], sealed: Any, label: str, reason: str) -> Any:
    try:
        kid = sealed_parts(sealed, label)["kid"]
    except ContractError as exc:
        raise Unauthenticated(f"malformed_{label.replace('-', '_')}") from exc
    key = keys.get(kid)
    if key is None:
        raise Unauthenticated(reason)
    return key


# ------------------------------------------------------------------ agent cards

CARD_FIELDS = {"type", "issuer", "agent_id", "endpoint", "capabilities", "schema_versions",
               "key", "not_before", "expires_at"}


def issue_card(ca_key: Any, *, agent_id: str, endpoint_url: str, capabilities: Iterable[str],
               agent_key: Any, not_before: int, expires_at: int,
               schema_versions: Iterable[str] = (PEER_SCHEMA_VERSION,)) -> dict[str, Any]:
    """Test CA binds agent ID + key + claimed metadata. Like an A2A Agent Card, but signed."""
    payload = {"type": "agent-card", "issuer": ca_key.kid, "agent_id": agent_id,
               "endpoint": endpoint_url, "capabilities": sorted(capabilities),
               "schema_versions": sorted(schema_versions),
               "key": {"alg": agent_key.alg, "kid": agent_key.kid, "public": agent_key.public_value()},
               "not_before": not_before, "expires_at": expires_at}
    return seal("agent-card", payload, ca_key)


@dataclass(frozen=True)
class VerifiedCard:
    agent_id: str
    endpoint: str
    capabilities: frozenset[str]
    schema_versions: frozenset[str]
    key: Any
    expires_at: int


def verify_card(sealed: Any, trust: TrustStore, now: int) -> VerifiedCard:
    issuer = _resolve(trust.card_issuers, sealed, "agent-card", "untrusted_card_issuer")
    p = unseal("agent-card", sealed, issuer, "bad_card_signature")
    try:
        _fields(p, CARD_FIELDS, "agent card")
        if p["type"] != "agent-card" or p["issuer"] != issuer.kid:
            raise ContractError("invalid agent card")
        agent_id = _id(p["agent_id"], "agent_id")
        url = endpoint(p["endpoint"])
        caps = _id_list(p["capabilities"], "capabilities")
        schemas = frozenset(p["schema_versions"]) if isinstance(p["schema_versions"], list) else None
        if not schemas or not all(isinstance(x, str) and len(x) <= 64 for x in schemas):
            raise ContractError("invalid schema_versions")
        k = _fields(p["key"], {"alg", "kid", "public"}, "card key")
        _id(k["kid"], "card key kid")
        nbf, exp = _time(p["not_before"], "not_before"), _time(p["expires_at"], "expires_at")
    except ContractError as exc:
        raise Unauthenticated("malformed_card") from exc
    if not nbf <= now < exp:
        raise Unauthenticated("card_expired")
    if k["alg"] == ED25519:
        if not ed25519_available():
            raise Unauthenticated("unsupported_key_alg")
        try:
            key = Ed25519Key.from_public(k["kid"], k["public"])
        except ContractError as exc:
            raise Unauthenticated("malformed_card") from exc
    elif k["alg"] == HS256 and k["public"] == "":
        key = trust.peer_keys.get(k["kid"])
        if key is None:
            raise Unauthenticated("unknown_peer_key")
    else:
        raise Unauthenticated("unsupported_key_alg")
    return VerifiedCard(agent_id, url, caps, schemas, key, exp)


# ----------------------------------------------------------------------- grants

GRANT_FIELDS = {"type", "grant_id", "issuer", "subject", "actor", "audience", "task_id",
                "capabilities", "classification", "not_before", "expires_at"}


def issue_grant(issuer_key: Any, *, grant_id: str, subject: str, actor: str, audience: str,
                task_id: str, capabilities: Iterable[str], not_before: int, expires_at: int,
                classification: str = "synthetic") -> dict[str, Any]:
    """Synthetic user authority delegates ONE task to ONE destination for ONE actor.

    The grant is not a reusable user or provider credential: it is useless for any other
    task/audience, and the receiver also requires the actor's own signature (sender-
    constrained, proof-of-possession) on every request that presents it.
    """
    payload = {"type": "grant", "grant_id": grant_id, "issuer": issuer_key.kid,
               "subject": subject, "actor": actor, "audience": audience, "task_id": task_id,
               "capabilities": sorted(capabilities), "classification": classification,
               "not_before": not_before, "expires_at": expires_at}
    return seal("grant", payload, issuer_key)


def verify_grant(sealed: Any, trust: TrustStore) -> dict[str, Any]:
    """Signature and structure only; scope and liveness are checked by check_grant_*."""
    issuer = _resolve(trust.grant_issuers, sealed, "grant", "untrusted_grant_issuer")
    p = unseal("grant", sealed, issuer, "bad_grant_signature")
    try:
        _fields(p, GRANT_FIELDS, "grant")
        if p["type"] != "grant" or p["issuer"] != issuer.kid:
            raise ContractError("invalid grant")
        for name in ("grant_id", "subject", "actor", "audience", "task_id"):
            _id(p[name], name)
        _id_list(p["capabilities"], "grant capabilities", TASK_KINDS)
        if p["classification"] not in CLASSIFICATIONS:
            raise ContractError("invalid grant classification")
        _time(p["not_before"], "not_before")
        _time(p["expires_at"], "expires_at")
    except ContractError as exc:
        raise Unauthorized("malformed_grant") from exc
    return p


def check_grant_live(grant: dict[str, Any], *, now: int, revoked: bool) -> None:
    if revoked:
        raise Unauthorized("grant_revoked")
    if now < grant["not_before"]:
        raise Unauthorized("grant_not_yet_valid")
    if now >= grant["expires_at"]:
        raise Unauthorized("grant_expired")


def check_grant_scope(grant: dict[str, Any], *, actor: str, audience: str, task_id: str,
                      kind: str, classification: str) -> None:
    if grant["audience"] != audience:
        raise Unauthorized("wrong_audience")
    if grant["actor"] != actor:
        raise Unauthorized("wrong_actor")
    if grant["task_id"] != task_id:
        raise Unauthorized("wrong_task")
    if kind not in grant["capabilities"]:
        raise Unauthorized("capability_not_granted")
    if grant["classification"] != classification:
        raise Unauthorized("classification_not_granted")


def issue_revocation(issuer_key: Any, grant_id: str, revoked_at: int) -> dict[str, Any]:
    return seal("revocation", {"type": "revocation", "issuer": issuer_key.kid,
                               "grant_id": grant_id, "revoked_at": revoked_at}, issuer_key)


def verify_revocation(sealed: Any, trust: TrustStore) -> dict[str, Any]:
    issuer = _resolve(trust.grant_issuers, sealed, "revocation", "untrusted_grant_issuer")
    p = unseal("revocation", sealed, issuer, "bad_revocation_signature")
    try:
        _fields(p, {"type", "issuer", "grant_id", "revoked_at"}, "revocation")
        if p["type"] != "revocation" or p["issuer"] != issuer.kid:
            raise ContractError("invalid revocation")
        _id(p["grant_id"], "grant_id")
        _time(p["revoked_at"], "revoked_at")
    except ContractError as exc:
        raise Unauthenticated("malformed_revocation") from exc
    return p


def commitment(salt: bytes, task: dict[str, Any]) -> str:
    """Salted hiding commitment: binds delivery to preflight without disclosing the text."""
    return hashlib.sha256(_DOMAIN + b"commitment\n" + salt + canonical(task).encode("utf-8")).hexdigest()
