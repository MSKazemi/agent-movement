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

Delivery confidentiality (issue #19) is a separate, optional layer. A receiver card may carry
an X25519 key (``enc_key``) signed with the card. Senders then seal the task with RFC 9180
HPKE (base mode, DHKEM(X25519, HKDF-SHA256), HKDF-SHA256, ChaCha20-Poly1305) through the
``cryptography`` package's own HPKE implementation, bound to the preflight transcript
(``delivery_info``). Without that key -- always the case in the stdlib-only mode -- deliveries
travel in plaintext and have **no confidentiality**.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .core import ContractError, PolicyDenied, _fields, _id, canonical, digest

if TYPE_CHECKING:  # the optional ``cryptography`` extra; imported lazily at runtime
    from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
    from cryptography.hazmat.primitives.hpke import Suite

PEER_SCHEMA_VERSION = "0.1.0-peer-draft"
HS256 = "HS256"
ED25519 = "Ed25519"
TASK_KINDS = frozenset({"word_count", "sha256"})
CLASSIFICATIONS = frozenset({"synthetic", "public"})
SEALED_FIELDS = {"alg", "kid", "payload", "sig"}
_DOMAIN = b"agent-movement/peer/v0\n"
_PURPOSES = frozenset({"agent-card", "grant", "revocation", "preflight", "admission",
                       "delivery", "receipt", "continuity-consent", "continuity-revocation",
                       "continuity-observation", "continuity-ack"})
# Loopback or in-process only: a card can never point a sender at an arbitrary host (SSRF).
_ENDPOINT = re.compile(r"(http://127\.0\.0\.1:[1-9][0-9]{0,4}|local://[A-Za-z0-9._-]{1,64})\Z")
_B64 = re.compile(r"[A-Za-z0-9_-]*\Z")
# RFC 9180 HPKE base mode: KEM 0x0020 DHKEM(X25519, HKDF-SHA256), KDF 0x0001 HKDF-SHA256,
# AEAD 0x0003 ChaCha20Poly1305. The identifier string is local to this prototype.
HPKE_SUITE = "hpke-base-x25519-hkdfsha256-chacha20poly1305"
RESPONSE_AEAD = "chacha20poly1305"
HPKE_OVERHEAD = 32 + 16  # enc (X25519 public key) + Poly1305 tag
MAX_SEALED_B64 = 16384  # base64 characters; the HTTP body cap is 16 KiB anyway
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


def b64d(text: Any, label: str = "base64 field", max_len: int = 4096) -> bytes:
    if not isinstance(text, str) or len(text) > max_len or not _B64.fullmatch(text):
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
    def generate(cls, kid: str) -> HmacKey:
        return cls(kid, secrets.token_bytes(32))

    def sign(self, data: bytes) -> bytes:
        return hmac.new(self._secret, data, hashlib.sha256).digest()

    def verify(self, data: bytes, signature: bytes) -> bool:
        return hmac.compare_digest(self.sign(data), signature)

    def public_value(self) -> str:
        return ""  # nothing public: verifiers must be provisioned out of band

    def verifier(self) -> HmacKey:
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
        self._private: ed25519.Ed25519PrivateKey | None = private
        self._public: ed25519.Ed25519PublicKey = public if public is not None else private.public_key()

    @classmethod
    def generate(cls, kid: str) -> Ed25519Key:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        return cls(kid, private=ed25519.Ed25519PrivateKey.generate())

    @classmethod
    def from_public(cls, kid: str, public_b64: str) -> Ed25519Key:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        raw = b64d(public_b64, "public key")
        if len(raw) != 32:
            raise ContractError("invalid Ed25519 public key")
        return cls(kid, public=ed25519.Ed25519PublicKey.from_public_bytes(raw))

    @classmethod
    def from_private(cls, kid: str, private_b64: str) -> Ed25519Key:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        raw = b64d(private_b64, "private key")
        if len(raw) != 32:
            raise ContractError("invalid Ed25519 private key")
        return cls(kid, private=ed25519.Ed25519PrivateKey.from_private_bytes(raw))

    def _raw_private(self) -> bytes:
        if self._private is None:  # callers check first; kept for the type checker
            raise TypeError("public-only Ed25519 key has no private bytes")
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

    def verifier(self) -> Ed25519Key:
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


def hpke_available() -> bool:
    """True when the installed ``cryptography`` exposes its RFC 9180 HPKE API (50.x does)."""
    try:
        from cryptography.hazmat.primitives.asymmetric import x25519  # noqa: F401
        from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305  # noqa: F401
        from cryptography.hazmat.primitives.hpke import AEAD, KDF, KEM, Suite  # noqa: F401
    except ImportError:
        return False
    return True


def _hpke_suite() -> Suite:
    from cryptography.hazmat.primitives.hpke import AEAD, KDF, KEM, Suite
    return Suite(KEM.X25519, KDF.HKDF_SHA256, AEAD.CHACHA20_POLY1305)


class HpkeKey:
    """X25519 delivery-encryption key for ``HPKE_SUITE``; deliberately separate from signing keys.

    Public-only instances (parsed from a verified card) need no third-party package until
    ``seal`` is called. ``open`` needs the private key and the optional ``cryptography`` extra.
    """

    suite = HPKE_SUITE

    def __init__(self, kid: str, public: bytes, private: Any = None):
        _id(kid, "enc kid")
        if not isinstance(public, bytes) or len(public) != 32 or public == bytes(32):
            raise ContractError("invalid X25519 public key")
        self.kid = kid
        self._public = public
        self._private: x25519.X25519PrivateKey | None = private

    @classmethod
    def generate(cls, kid: str) -> HpkeKey:
        from cryptography.hazmat.primitives.asymmetric import x25519
        private = x25519.X25519PrivateKey.generate()
        return cls(kid, private.public_key().public_bytes_raw(), private)

    @classmethod
    def from_public(cls, kid: str, public_b64: str) -> HpkeKey:
        return cls(kid, b64d(public_b64, "enc public key"))

    @classmethod
    def from_private(cls, kid: str, private_b64: str) -> HpkeKey:
        from cryptography.hazmat.primitives.asymmetric import x25519
        raw = b64d(private_b64, "enc private key")
        if len(raw) != 32:
            raise ContractError("invalid X25519 private key")
        private = x25519.X25519PrivateKey.from_private_bytes(raw)
        return cls(kid, private.public_key().public_bytes_raw(), private)

    def public_value(self) -> str:
        return b64e(self._public)

    def descriptor(self) -> dict[str, str]:
        """The ``enc_key`` object that the test CA signs into the receiver's card."""
        return {"suite": HPKE_SUITE, "kid": self.kid, "public": self.public_value()}

    def matches(self, other: Any) -> bool:
        return isinstance(other, HpkeKey) and (self.kid, self._public) == (other.kid, other._public)

    def seal(self, plaintext: bytes, info: bytes) -> bytes:
        """HPKE single-shot seal to this public key. Returns ``enc || ciphertext``."""
        from cryptography.hazmat.primitives.asymmetric import x25519
        public = x25519.X25519PublicKey.from_public_bytes(self._public)
        return _hpke_suite().encrypt(plaintext, public, info=info)

    def open(self, sealed: bytes, info: bytes) -> bytes:
        """HPKE single-shot open. A wrong key, any tampering or a different ``info`` raises
        ``Unauthenticated`` and returns no plaintext: the AEAD tag is verified first."""
        if self._private is None:
            raise TypeError("public-only HPKE key cannot open")
        from cryptography.exceptions import InvalidTag
        if len(sealed) < HPKE_OVERHEAD:
            raise Unauthenticated("delivery_decrypt_failed")
        try:
            return _hpke_suite().decrypt(sealed, self._private, info=info)
        except (InvalidTag, ValueError) as exc:
            raise Unauthenticated("delivery_decrypt_failed") from exc

    def secret_forms(self) -> tuple[bytes, ...]:
        if self._private is None:
            return ()
        raw = self._private.private_bytes_raw()
        return (raw, b64e(raw).encode("ascii"), raw.hex().encode("ascii"))

    def export(self, private: bool = True) -> dict[str, str]:
        out = self.descriptor()
        if private and self._private is not None:
            out["private"] = b64e(self._private.private_bytes_raw())
        return out

    def __repr__(self) -> str:
        return f"HpkeKey(kid={self.kid!r}, private={'<redacted>' if self._private else None})"


def import_enc_key(data: Any) -> HpkeKey:
    if not isinstance(data, dict) or data.get("suite") != HPKE_SUITE:
        raise ContractError("unsupported encryption key suite")
    if "private" not in data:
        _fields(data, {"suite", "kid", "public"}, "enc key")
        return HpkeKey.from_public(data["kid"], data["public"])
    _fields(data, {"suite", "kid", "public", "private"}, "enc key")
    key = HpkeKey.from_private(data["kid"], data["private"])
    if key.public_value() != data["public"]:
        raise ContractError("enc key public/private mismatch")
    return key


def delivery_info(*, card_digest: str, enc_kid: str, movement_id: str, origin_id: str, audience: str,
                  endpoint_url: str, client_nonce: str, admission_id: str, preflight_digest: str) -> bytes:
    """Preflight transcript bound into the HPKE key schedule as ``info``.

    RFC 9180 section 8.1: applications that use only the single-shot APIs should carry
    auxiliary authenticated information in ``info`` (``cryptography`` documents the same and
    exposes no public ``aad`` argument). A mismatch in any field derives a different AEAD key,
    so a sealed delivery opens only for this suite, key ID, receiver descriptor, movement,
    origin, audience, endpoint, client nonce, admission and preflight.
    """
    transcript = {"suite": HPKE_SUITE, "enc_kid": enc_kid, "card_digest": card_digest,
                  "movement_id": movement_id, "origin_id": origin_id, "audience": audience,
                  "endpoint": endpoint_url, "client_nonce": client_nonce, "admission_id": admission_id,
                  "preflight_digest": preflight_digest}
    return _DOMAIN + b"delivery-hpke\n" + canonical(transcript).encode("utf-8")


def seal_response(response_key: bytes, info: bytes, obj: Any) -> dict[str, str]:
    """Encrypt the signed receipt to the sender under the single-use key it sent inside the
    HPKE plaintext. Comparable to RFC 9458 section 4.4 response encapsulation, which derives
    the key with the HPKE exporter instead; ``cryptography``'s single-shot API has no exporter."""
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    nonce = secrets.token_bytes(12)
    ct = ChaCha20Poly1305(response_key).encrypt(nonce, canonical(obj).encode("utf-8"),
                                                info + b"\nresponse")
    return {"type": "encrypted-receipt", "aead": RESPONSE_AEAD, "nonce": b64e(nonce), "ct": b64e(ct)}


def open_response(response_key: bytes, info: bytes, obj: Any) -> bytes:
    """Inverse of ``seal_response``; raises ``Unauthenticated`` without returning plaintext."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    try:
        r = _fields(obj, {"type", "aead", "nonce", "ct"}, "encrypted receipt")
        if r["type"] != "encrypted-receipt" or r["aead"] != RESPONSE_AEAD:
            raise ContractError("invalid encrypted receipt")
        nonce = b64d(r["nonce"], "receipt nonce")
        ct = b64d(r["ct"], "receipt ciphertext", MAX_SEALED_B64)
        if len(nonce) != 12:
            raise ContractError("invalid receipt nonce")
        return ChaCha20Poly1305(response_key).decrypt(nonce, ct, info + b"\nresponse")
    except (ContractError, InvalidTag) as exc:
        raise Unauthenticated("bad_response_ciphertext") from exc


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
    payload: dict[str, Any] = s["payload"]
    return payload


# ------------------------------------------------------------------ trust store


@dataclass
class TrustStore:
    """What one participant pinned out of band. Nothing here is learned from a peer."""

    card_issuers: dict[str, Any]
    grant_issuers: dict[str, Any]
    peer_keys: dict[str, HmacKey] = field(default_factory=dict)  # HS256 only

    @classmethod
    def build(cls, card_issuers: Iterable[Any], grant_issuers: Iterable[Any],
              peer_keys: Iterable[HmacKey] = ()) -> TrustStore:
        return cls({k.kid: k.verifier() for k in card_issuers},
                   {k.kid: k.verifier() for k in grant_issuers},
                   {k.kid: k for k in peer_keys})

    def export(self) -> dict[str, list[dict[str, str]]]:
        return {"card_issuers": [k.export(private=False) for k in self.card_issuers.values()],
                "grant_issuers": [k.export(private=False) for k in self.grant_issuers.values()],
                "peer_keys": [k.export() for k in self.peer_keys.values()]}

    @classmethod
    def from_dict(cls, data: Any) -> TrustStore:
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
CARD_ENC_FIELDS = CARD_FIELDS | {"enc_key"}  # the agent accepts HPKE-sealed deliveries


def issue_card(ca_key: Any, *, agent_id: str, endpoint_url: str, capabilities: Iterable[str],
               agent_key: Any, not_before: int, expires_at: int,
               schema_versions: Iterable[str] = (PEER_SCHEMA_VERSION,),
               enc_key: HpkeKey | None = None) -> dict[str, Any]:
    """Test CA binds agent ID + key + claimed metadata. Like an A2A Agent Card, but signed.

    ``enc_key`` (optional) is the X25519 key that senders seal deliveries to. The same CA
    signature covers it, so a relay cannot substitute its own encryption key.
    """
    payload = {"type": "agent-card", "issuer": ca_key.kid, "agent_id": agent_id,
               "endpoint": endpoint_url, "capabilities": sorted(capabilities),
               "schema_versions": sorted(schema_versions),
               "key": {"alg": agent_key.alg, "kid": agent_key.kid, "public": agent_key.public_value()},
               "not_before": not_before, "expires_at": expires_at}
    if enc_key is not None:
        payload["enc_key"] = enc_key.descriptor()
    return seal("agent-card", payload, ca_key)


@dataclass(frozen=True)
class VerifiedCard:
    agent_id: str
    endpoint: str
    capabilities: frozenset[str]
    schema_versions: frozenset[str]
    key: Any
    expires_at: int
    enc_key: HpkeKey | None = None  # None: deliveries to this agent have no confidentiality
    digest: str = ""  # SHA-256 of the canonical signed card, bound into the HPKE transcript


def verify_card(sealed: Any, trust: TrustStore, now: int) -> VerifiedCard:
    issuer = _resolve(trust.card_issuers, sealed, "agent-card", "untrusted_card_issuer")
    p = unseal("agent-card", sealed, issuer, "bad_card_signature")
    try:
        if not isinstance(p, dict) or set(p) not in (CARD_FIELDS, CARD_ENC_FIELDS):
            raise ContractError("invalid agent card fields")
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
        enc = p.get("enc_key")
        if enc is not None:
            _fields(enc, {"suite", "kid", "public"}, "card enc_key")
    except ContractError as exc:
        raise Unauthenticated("malformed_card") from exc
    enc_key = None
    if enc is not None:
        if enc["suite"] != HPKE_SUITE:
            raise Unauthenticated("unsupported_enc_suite")
        try:
            enc_key = HpkeKey.from_public(enc["kid"], enc["public"])
        except ContractError as exc:
            raise Unauthenticated("malformed_card") from exc
    if not nbf <= now < exp:
        raise Unauthenticated("card_expired")
    key: Ed25519Key | HmacKey | None
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
    return VerifiedCard(agent_id, url, caps, schemas, key, exp, enc_key, digest(sealed))


# ----------------------------------------------------------------------- grants

GRANT_FIELDS = {"type", "grant_id", "issuer", "subject", "actor", "audience", "task_id",
                "capabilities", "classification", "not_before", "expires_at", "max_uses"}
# Grants signed before issue #29 carry no ``max_uses``; they verify as single-use (the default
# and the most restrictive value). The field cannot be stripped: the signature covers it.
LEGACY_GRANT_FIELDS = GRANT_FIELDS - {"max_uses"}
DEFAULT_GRANT_USES = 1
MAX_GRANT_USES = 1_000_000  # bounded so that no value can silently mean "unlimited"


def grant_uses(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= MAX_GRANT_USES:
        raise ContractError("invalid max_uses")
    return value


def issue_grant(issuer_key: Any, *, grant_id: str, subject: str, actor: str, audience: str,
                task_id: str, capabilities: Iterable[str], not_before: int, expires_at: int,
                classification: str = "synthetic", max_uses: int = DEFAULT_GRANT_USES) -> dict[str, Any]:
    """Synthetic user authority delegates ONE task to ONE destination for ONE actor.

    The grant is not a reusable user or provider credential: it is useless for any other
    task/audience, and the receiver also requires the actor's own signature (sender-
    constrained, proof-of-possession) on every request that presents it. ``max_uses``
    (signed, default 1) bounds how many distinct movements the receiver admits under it;
    retries of an admitted movement do not count again (``PeerLedger.consume_use``).
    """
    payload = {"type": "grant", "grant_id": grant_id, "issuer": issuer_key.kid,
               "subject": subject, "actor": actor, "audience": audience, "task_id": task_id,
               "capabilities": sorted(capabilities), "classification": classification,
               "not_before": not_before, "expires_at": expires_at, "max_uses": grant_uses(max_uses)}
    return seal("grant", payload, issuer_key)


def verify_grant(sealed: Any, trust: TrustStore) -> dict[str, Any]:
    """Signature and structure only; scope and liveness are checked by check_grant_*.

    The returned payload always has ``max_uses`` (1 for a legacy grant that predates it).
    Use counting is stateful and lives in the receiver's ledger, not here.
    """
    issuer = _resolve(trust.grant_issuers, sealed, "grant", "untrusted_grant_issuer")
    p = unseal("grant", sealed, issuer, "bad_grant_signature")
    try:
        if not isinstance(p, dict) or set(p) not in (GRANT_FIELDS, LEGACY_GRANT_FIELDS):
            raise ContractError("invalid grant fields")
        p = {"max_uses": DEFAULT_GRANT_USES, **p}
        grant_uses(p["max_uses"])
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
