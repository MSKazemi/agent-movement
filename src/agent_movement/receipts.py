"""Signed movement receipts and an OFFLINE forensic verifier (experimental profile).

What this module does:

* defines a strict ``0.1-draft`` receipt body that keeps identity CLAIMS
  (self-reported agent labels and principals) separate from the VERIFIED
  principal, which comes only from an out-of-band trust anchor file;
* signs ``SIGNATURE_DOMAIN || JCS(body)`` with Ed25519 (optional
  ``cryptography`` extra) and verifies body digests, signatures, key validity,
  signer role, per-signer sequence chains and replays;
* reconstructs a sanitized timeline whose entries are VERIFIABLE,
  UNVERIFIABLE or CONFLICTING, with explicit uncertainty notes.

What it does NOT do: a valid signature shows only that a trusted key holder
signed the statement, not that the statement is true; timestamps are the
signer's claim; a bundle can be incomplete; trace IDs are correlation only.
Run ``python -m agent_movement.receipts verify <dir> --trust <anchors.json>``. Trust
anchors are never read from the evidence implicitly; ``--fixture-trust`` opts into the
anchors shipped with the synthetic fixtures, with a warning.
"""

from __future__ import annotations

import argparse
import base64
import heapq
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .core import ID, ContractError, parse_json
from .jcs import CanonicalizationError, canonicalize, jcs_digest

try:  # Optional extra: pip install -e ".[signing]"
    import cryptography
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    HAVE_ED25519 = True
    CRYPTO_VERSION: str | None = cryptography.__version__
except ImportError:  # pragma: no cover - exercised in the dependency-free CI step
    HAVE_ED25519 = False
    CRYPTO_VERSION = None

RECEIPT_SCHEMA = "agent-movement.receipt/0.1-draft"
TRUST_SCHEMA = "agent-movement.trust/0.1-draft"
REPORT_SCHEMA = "agent-movement.verification-report/0.1-draft"
SIGNATURE_DOMAIN = b"agent-movement/receipt/v0.1\x00"

PRINCIPAL = re.compile(r"[a-z][a-z0-9+.-]{0,15}://[A-Za-z0-9._~:/-]{1,200}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
NONCE = re.compile(r"[0-9a-f]{32}\Z")
TRACE_ID = re.compile(r"[0-9a-f]{32}\Z")
SPAN_ID = re.compile(r"[0-9a-f]{16}\Z")
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
B64URL = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")

RECEIPT_TYPES = ("movement.dispatched", "movement.accepted", "movement.rejected",
                 "execution.started", "execution.completed", "tool.effect_recorded")
RESPONSE_TYPES = ("movement.accepted", "movement.rejected")
LINEAGE = ("delegate", "relocate", "clone", "fork", "replicate", "fan_out")
OUTCOMES = ("dispatched", "accepted", "rejected", "started", "completed", "failed", "unknown")
EFFECT_STATUS = ("committed", "rejected", "unknown")
# revocation_notice/policy_decision reference EXTERNAL signed documents by digest only;
# this profile does not parse or verify them (e.g. a peer-auth revocation notice).
SUBJECT_ROLES = ("envelope", "artifact", "checkpoint", "effect_payload", "revocation_notice", "policy_decision")
CLASSIFICATIONS = ("synthetic", "public")
ROLES = ("agent", "tool")

# Receipt verdicts. Only VALID records are used as verified statements.
VALID, UNCHECKED, UNTRUSTED = "VALID", "UNCHECKED", "UNTRUSTED"
TAMPERED, REPLAYED, MALFORMED = "TAMPERED", "REPLAYED", "MALFORMED"
VERDICTS = (VALID, UNCHECKED, UNTRUSTED, TAMPERED, REPLAYED, MALFORMED)
REJECTED = (UNTRUSTED, TAMPERED, REPLAYED, MALFORMED)
# Timeline entry status and claim status vocabularies.
VERIFIABLE, UNVERIFIABLE, CONFLICTING = "VERIFIABLE", "UNVERIFIABLE", "CONFLICTING"
VERIFIED, SIGNED_CLAIM, UNVERIFIED_CLAIM, UNKNOWN = "VERIFIED", "SIGNED_CLAIM", "UNVERIFIED_CLAIM", "UNKNOWN"
CORRELATION_ONLY = "CORRELATION_ONLY"

REDACTED = "[REDACTED]"
TOKEN_LIKE = re.compile(
    r"(?i)(\bbearer\s+\S+|\bbasic\s+[A-Za-z0-9+/=]{8,}"
    r"|eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk|rk)-[A-Za-z0-9_-]{16,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{16}\b|\bxox[abprs]-[A-Za-z0-9-]{10,}"
    r"|(?:api[_-]?key|token|secret|password)\s*[=:])")
SENSITIVE_KEY = re.compile(r"(?i)(authori[sz]ation|cookie|token|secret|passw|api[_-]?key|credential"
                           r"|prompt|message|content|completion|baggage|header)")
TELEMETRY_KEEP = ("agent.claimed_id", "movement_id", "logical_task_id", "execution_id", "outcome")

LIMITS = (
    "A valid signature shows that a trusted key holder signed the statement; it does not make the statement true.",
    "issued_at values are claims by the signer; there is no trusted timestamp, so backdating is not detectable.",
    "A bundle is not guaranteed complete: absent receipts are UNKNOWN, never evidence that nothing happened.",
    "Trace and span IDs are correlation hints only; they never authenticate an agent or a principal.",
    "Agent labels (claimed_agent_id) are never bound to keys; only trust-anchor principals are verified.",
    "Trust anchors must be obtained out of band; anchors shipped inside the evidence bundle prove nothing.",
    "The verifier never infers events: grade E0 is never assigned and gaps are reported, not filled.",
)


class ReceiptError(ValueError):
    """Receipt, trust anchor or bundle outside the experimental profile."""


def _require_crypto() -> None:
    if not HAVE_ED25519:
        raise ReceiptError('Ed25519 needs the optional extra: python -m pip install -e ".[signing]"')


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64u(text: str) -> bytes:
    if not isinstance(text, str) or not B64URL.fullmatch(text):
        raise ReceiptError("invalid base64url value")
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not TIME.fullmatch(value):
        raise ReceiptError("time must be YYYY-MM-DDTHH:MM:SSZ (UTC)")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ReceiptError("invalid calendar time") from exc


def format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- schema

def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ReceiptError(f"invalid {label} fields")
    return value


def _match(value: Any, pattern: re.Pattern[str], label: str, optional: bool = True) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ReceiptError(f"invalid {label}")


def _choice(value: Any, choices: tuple[str, ...], label: str, optional: bool = True) -> None:
    if value is None and optional:
        return
    if value not in choices:
        raise ReceiptError(f"invalid {label}")


def _party(value: Any, label: str) -> None:
    if value is None:
        return
    _exact(value, {"claimed_agent_id", "claimed_principal", "execution_id"}, label)
    _match(value["claimed_agent_id"], ID, f"{label}.claimed_agent_id")
    _match(value["claimed_principal"], PRINCIPAL, f"{label}.claimed_principal")
    _match(value["execution_id"], ID, f"{label}.execution_id")


def validate_body(body: Any) -> dict[str, Any]:
    """Strict structural validation; every optional claim is present as ``null``."""
    b = _exact(body, {"schema", "receipt_id", "receipt_type", "issuer", "audience", "nonce",
                      "issued_at", "seq", "prev_receipt_digest", "logical_task_id", "movement",
                      "source", "destination", "execution", "correlation", "subjects", "effect",
                      "outcome", "data_classification"}, "receipt")
    if b["schema"] != RECEIPT_SCHEMA:
        raise ReceiptError("unsupported receipt schema")
    _match(b["receipt_id"], ID, "receipt_id", optional=False)
    _choice(b["receipt_type"], RECEIPT_TYPES, "receipt_type", optional=False)
    issuer = _exact(b["issuer"], {"key_id", "claimed_principal", "claimed_agent_id"}, "issuer")
    _match(issuer["key_id"], ID, "issuer.key_id", optional=False)
    _match(issuer["claimed_principal"], PRINCIPAL, "issuer.claimed_principal")
    _match(issuer["claimed_agent_id"], ID, "issuer.claimed_agent_id")
    _match(b["audience"], PRINCIPAL, "audience")
    _match(b["nonce"], NONCE, "nonce", optional=False)
    parse_time(b["issued_at"])
    if type(b["seq"]) is not int or not 1 <= b["seq"] <= 2 ** 53 - 1:
        raise ReceiptError("invalid seq")
    _match(b["prev_receipt_digest"], DIGEST, "prev_receipt_digest")
    _match(b["logical_task_id"], ID, "logical_task_id")
    if b["movement"] is not None:
        m = _exact(b["movement"], {"movement_id", "parent_movement_id", "lineage_relation"}, "movement")
        _match(m["movement_id"], ID, "movement.movement_id", optional=False)
        _match(m["parent_movement_id"], ID, "movement.parent_movement_id")
        _choice(m["lineage_relation"], LINEAGE, "movement.lineage_relation")
    _party(b["source"], "source")
    _party(b["destination"], "destination")
    if b["execution"] is not None:
        e = _exact(b["execution"], {"execution_id", "parent_execution_id", "agent_instance_id",
                                    "definition_digest"}, "execution")
        for name in ("execution_id", "parent_execution_id", "agent_instance_id"):
            _match(e[name], ID, f"execution.{name}")
        _match(e["definition_digest"], DIGEST, "execution.definition_digest")
    c = _exact(b["correlation"], {"trace_id", "span_id"}, "correlation")
    _match(c["trace_id"], TRACE_ID, "correlation.trace_id")
    _match(c["span_id"], SPAN_ID, "correlation.span_id")
    if not isinstance(b["subjects"], list) or len(b["subjects"]) > 8:
        raise ReceiptError("invalid subjects")
    for subject in b["subjects"]:
        s = _exact(subject, {"role", "ref", "digest"}, "subject")
        _choice(s["role"], SUBJECT_ROLES, "subject.role", optional=False)
        _match(s["ref"], ID, "subject.ref", optional=False)
        _match(s["digest"], DIGEST, "subject.digest", optional=False)
    if b["effect"] is not None:
        f = _exact(b["effect"], {"effect_id", "tool_principal", "status", "fencing_epoch"}, "effect")
        _match(f["effect_id"], ID, "effect.effect_id", optional=False)
        _match(f["tool_principal"], PRINCIPAL, "effect.tool_principal")
        _choice(f["status"], EFFECT_STATUS, "effect.status", optional=False)
        if f["fencing_epoch"] is not None and (type(f["fencing_epoch"]) is not int or f["fencing_epoch"] < 1):
            raise ReceiptError("invalid effect.fencing_epoch")
    _choice(b["outcome"], OUTCOMES, "outcome")
    _choice(b["data_classification"], CLASSIFICATIONS, "data_classification", optional=False)
    kind = b["receipt_type"]
    if kind.startswith("movement.") and b["movement"] is None:
        raise ReceiptError("movement receipts need a movement block")
    if kind.startswith("execution.") and b["execution"] is None:
        raise ReceiptError("execution receipts need an execution block")
    if kind == "tool.effect_recorded" and b["effect"] is None:
        raise ReceiptError("tool records need an effect block")
    return b


# --------------------------------------------------------------------------- redaction

def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def contains_token_like(value: Any) -> bool:
    return any(TOKEN_LIKE.search(text) for text in _strings(value))


def redact(value: Any, key: str | None = None) -> tuple[Any, int]:
    """Replace credential-like values and sensitive-named fields; return (value, count)."""
    if key is not None and SENSITIVE_KEY.search(key):
        return REDACTED, 1
    if isinstance(value, str):
        return (REDACTED, 1) if TOKEN_LIKE.search(value) else (value, 0)
    if isinstance(value, dict):
        out, total = {}, 0
        for name, item in value.items():
            safe_name = REDACTED if TOKEN_LIKE.search(str(name)) else name
            out[safe_name], count = redact(item, str(name))
            total += count + (safe_name == REDACTED)
        return out, total
    if isinstance(value, list):
        items = [redact(item) for item in value]
        return [item for item, _ in items], sum(count for _, count in items)
    return value, 0


# --------------------------------------------------------------------------- signing

def signing_input(body: dict[str, Any]) -> bytes:
    """Domain-separated bytes covered by the signature."""
    return SIGNATURE_DOMAIN + canonicalize(body)


class Ed25519Signer:
    """Signs receipt bodies. Fixture keys are SYNTHETIC and their seeds are public."""

    def __init__(self, key_id: str, seed: bytes):
        _require_crypto()
        _match(key_id, ID, "key_id", optional=False)
        self.key_id = key_id
        self._key = Ed25519PrivateKey.from_private_bytes(seed)

    @property
    def public_key(self) -> str:
        raw = self._key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return b64u(raw)

    def seal(self, body: dict[str, Any]) -> dict[str, Any]:
        validate_body(body)
        if body["issuer"]["key_id"] != self.key_id:
            raise ReceiptError("issuer.key_id must name the signing key")
        if contains_token_like(body):
            raise ReceiptError("refusing to sign a credential-like value")
        return {"receipt": body, "body_digest": jcs_digest(body),
                "signature": {"alg": "Ed25519", "key_id": self.key_id,
                              "value": b64u(self._key.sign(signing_input(body)))}}


def commitment(value: Any, salt: str) -> dict[str, Any]:
    """Salted subject document. Publish only its digest; keep the document with the evidence.

    An unsalted digest of low-entropy content (short task text, a word count, a hash of
    the text) can be confirmed by guessing; the salt prevents that while the subject
    document stays checkable by whoever holds it.
    """
    _match(salt, NONCE, "commitment salt", optional=False)
    return {"commitment_salt": salt, "value": value}


def body_from_handoff(core_receipt: dict[str, Any], *, key_id: str, issued_at: str, nonce: str,
                      salt: str, envelope: dict[str, Any] | None = None, seq: int = 1,
                      prev: str | None = None, destination_principal: str | None = None) -> dict[str, Any]:
    """Wrap an unsigned PR #6 ``HandoffReceiver`` receipt as a signable attestation body.

    Agent IDs from the PR #6 receipt stay *claims* (``claimed_agent_id``). The PR #6
    ``trace_id`` is an opaque local ID, not a W3C trace-id, so it is not carried.
    PR #6's ``envelope_digest``/``artifact_digest`` are UNSALTED hashes that include the
    task text, so they are deliberately NOT copied; salted commitments are used instead
    (see :func:`commitment`). The envelope is committed only when it is supplied.
    """
    mid = core_receipt["movement_id"]
    subjects = [{"role": "artifact", "ref": f"art-{mid}",
                 "digest": jcs_digest(commitment(core_receipt["artifact"], salt))}]
    if envelope is not None:
        subjects.insert(0, {"role": "envelope", "ref": f"env-{mid}", "digest": jcs_digest(commitment(envelope, salt))})
    body = {
        "schema": RECEIPT_SCHEMA, "receipt_id": f"rcpt-{mid}-handoff", "receipt_type": "execution.completed",
        "issuer": {"key_id": key_id, "claimed_principal": destination_principal,
                   "claimed_agent_id": core_receipt["destination_agent_id"]},
        "audience": None, "nonce": nonce, "issued_at": issued_at, "seq": seq, "prev_receipt_digest": prev,
        "logical_task_id": core_receipt["logical_task_id"],
        "movement": {"movement_id": mid, "parent_movement_id": None, "lineage_relation": "delegate"},
        "source": {"claimed_agent_id": core_receipt["origin_agent_id"], "claimed_principal": None,
                   "execution_id": None},
        "destination": {"claimed_agent_id": core_receipt["destination_agent_id"],
                        "claimed_principal": destination_principal, "execution_id": None},
        "execution": {"execution_id": None, "parent_execution_id": None, "agent_instance_id": None,
                      "definition_digest": None},
        "correlation": {"trace_id": None, "span_id": None},
        "subjects": subjects,
        "effect": None, "outcome": "completed" if core_receipt["status"] == "completed" else "unknown",
        "data_classification": "synthetic",
    }
    return validate_body(body)


# --------------------------------------------------------------------------- trust anchors

@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    principal: str
    role: str
    public_key: bytes
    not_before: datetime
    not_after: datetime
    revoked_at: datetime | None
    revocation_ref: str | None = None  # digest of an EXTERNAL signed revocation notice, if any

    def problem_at(self, when: datetime) -> str | None:
        if when < self.not_before or when >= self.not_after:
            return "claimed issue time is outside the key validity window"
        if self.revoked_at is not None and when >= self.revoked_at:
            ref = f" (revocation notice {self.revocation_ref})" if self.revocation_ref else ""
            return "key was revoked before the claimed issue time" + ref
        return None


def load_trust(path: Path) -> dict[str, TrustedKey]:
    doc = parse_json(Path(path).read_bytes())
    doc = _exact(doc, {"schema", "note", "keys"}, "trust anchor file")
    if doc["schema"] != TRUST_SCHEMA or not isinstance(doc["keys"], list):
        raise ReceiptError("unsupported trust anchor file")
    keys: dict[str, TrustedKey] = {}
    for item in doc["keys"]:
        k = _exact(item, {"key_id", "principal", "role", "alg", "public_key",
                          "not_before", "not_after", "revoked_at", "revocation_ref"}, "trusted key")
        _match(k["revocation_ref"], DIGEST, "revocation_ref")
        if k["revocation_ref"] is not None and k["revoked_at"] is None:
            raise ReceiptError("revocation_ref requires revoked_at")
        _match(k["key_id"], ID, "key_id", optional=False)
        _match(k["principal"], PRINCIPAL, "principal", optional=False)
        _choice(k["role"], ROLES, "role", optional=False)
        if k["alg"] != "Ed25519" or k["key_id"] in keys:
            raise ReceiptError("unsupported algorithm or duplicate key_id")
        public = unb64u(k["public_key"])
        if len(public) != 32:
            raise ReceiptError("Ed25519 public keys are 32 bytes")
        keys[k["key_id"]] = TrustedKey(k["key_id"], k["principal"], k["role"], public,
                                       parse_time(k["not_before"]), parse_time(k["not_after"]),
                                       None if k["revoked_at"] is None else parse_time(k["revoked_at"]),
                                       k["revocation_ref"])
    return keys


# --------------------------------------------------------------------------- replay

class ReplayGuard:
    """Remembers (key_id, nonce) and (key_id, receipt_id) pairs, in memory only.

    Feed it only signature-valid receipts; otherwise a forger could pre-register a
    nonce and make the genuine receipt look like a replay. ``max_age`` is meant for
    live acceptance; offline forensic verification usually leaves it ``None``.
    """

    def __init__(self, max_age: timedelta | None = None):
        self.max_age = max_age
        self._seen: dict[tuple[str, str, str], tuple[str, int]] = {}

    def check(self, key_id: str, nonce: str, receipt_id: str, body_digest: str, index: int,
              issued_at: datetime | None = None, now: datetime | None = None) -> tuple[str | None, int | None]:
        """Return (problem, index of the earlier record) and remember fresh receipts.

        problem is None (fresh), 'stale', 'duplicate' (identical body seen) or
        'reuse' (same nonce or receipt_id, different body: signer equivocation).
        """
        if self.max_age is not None and issued_at is not None and now is not None \
                and issued_at < now - self.max_age:
            return "stale", None
        for slot in (("nonce", key_id, nonce), ("id", key_id, receipt_id)):
            earlier = self._seen.get(slot)
            if earlier is not None:
                return ("duplicate" if earlier[0] == body_digest else "reuse"), earlier[1]
        for slot in (("nonce", key_id, nonce), ("id", key_id, receipt_id)):
            self._seen[slot] = (body_digest, index)
        return None, None


# --------------------------------------------------------------------------- verification

@dataclass
class Record:
    index: int
    file: str
    line: int
    verdict: str = MALFORMED
    reasons: list[str] = field(default_factory=list)
    body: dict[str, Any] | None = None
    digest: str | None = None
    key: TrustedKey | None = None
    status: str = UNVERIFIABLE
    grade: str | None = None
    notes: list[str] = field(default_factory=list)
    corroborated_by: list[str] = field(default_factory=list)

    @property
    def ref(self) -> str:
        if self.body is not None:
            return f"receipt:{self.body['receipt_id']}"
        return f"{self.file}:{self.line}"

    def conflict(self, note: str) -> None:
        self.status = CONFLICTING
        if note not in self.notes:
            self.notes.append(note)


def _verify_wire(record: Record, raw: bytes, trust: dict[str, TrustedKey]) -> None:
    try:
        wire = parse_json(raw)
    except ContractError:
        record.reasons.append("not a single strict JSON object (invalid or duplicate keys)")
        return
    if not isinstance(wire, dict) or set(wire) != {"receipt", "body_digest", "signature"} \
            or not isinstance(wire["signature"], dict) \
            or set(wire["signature"]) != {"alg", "key_id", "value"}:
        record.reasons.append("wire format must be {receipt, body_digest, signature{alg,key_id,value}}")
        return
    if contains_token_like(wire["receipt"]) or contains_token_like(wire["signature"]["key_id"]):
        record.reasons.append("credential-like value present; content withheld from the report")
        return
    try:
        body = validate_body(wire["receipt"])
        computed = jcs_digest(body)
    except (ReceiptError, CanonicalizationError) as exc:
        record.reasons.append(f"schema: {exc}")
        return
    record.body, record.digest = body, computed
    sig = wire["signature"]
    if wire["body_digest"] != computed:
        record.verdict = TAMPERED
        record.reasons.append("body_digest does not match the canonical body")
        return
    if sig["alg"] != "Ed25519" or sig["key_id"] != body["issuer"]["key_id"]:
        record.verdict = TAMPERED
        record.reasons.append("signature block does not match the signed issuer key_id/algorithm")
        return
    key = trust.get(body["issuer"]["key_id"])
    if key is None:
        record.verdict = UNTRUSTED
        record.reasons.append("signing key is not in the trust anchors")
        return
    if HAVE_ED25519:
        try:
            Ed25519PublicKey.from_public_bytes(key.public_key).verify(unb64u(sig["value"]),
                                                                      signing_input(body))
        except (InvalidSignature, ReceiptError, ValueError):
            record.verdict = TAMPERED
            record.reasons.append("Ed25519 signature does not verify over the canonical body")
            return
    record.key = key
    issued = parse_time(body["issued_at"])
    claimed = body["issuer"]["claimed_principal"]
    expected_role = "tool" if body["receipt_type"] == "tool.effect_recorded" else "agent"
    for problem in (key.problem_at(issued),
                    None if claimed in (None, key.principal) else
                    "issuer claims a principal that its key is not bound to",
                    None if key.role == expected_role else
                    f"{body['receipt_type']} must be signed by a key with role '{expected_role}'"):
        if problem:
            record.verdict = UNTRUSTED
            record.reasons.append(problem)
    if record.verdict != UNTRUSTED:
        record.verdict = VALID if HAVE_ED25519 else UNCHECKED
        if not HAVE_ED25519:
            record.reasons.append("signature NOT checked: optional 'cryptography' extra not installed")


def _read_lines(path: Path) -> list[tuple[int, bytes]]:
    if not path.exists():
        return []
    return [(n, raw) for n, raw in enumerate(path.read_bytes().splitlines(), 1) if raw.strip()]


def _load_telemetry(path: Path) -> tuple[list[dict[str, Any]], int, int, int]:
    """Return (sanitized spans, malformed lines, redactions, dropped attributes)."""
    spans, malformed, redactions, dropped = [], 0, 0, 0
    for _, raw in _read_lines(path):
        try:
            span = parse_json(raw)
            span = _exact(span, {"trace_id", "span_id", "name", "time", "attributes"}, "span")
            _match(span["trace_id"], TRACE_ID, "trace_id", optional=False)
            _match(span["span_id"], SPAN_ID, "span_id", optional=False)
            parse_time(span["time"])
            if not isinstance(span["attributes"], dict):
                raise ReceiptError("attributes")
        except (ContractError, ReceiptError):
            malformed += 1
            continue
        name = span["name"] if isinstance(span["name"], str) and ID.fullmatch(span["name"]) else REDACTED
        redactions += name == REDACTED
        clean, count = redact(span["attributes"])
        redactions += count
        kept = {}
        for key, value in clean.items():
            if key in TELEMETRY_KEEP and isinstance(value, str) and (value == REDACTED or ID.fullmatch(value)):
                kept[key] = value
            else:
                dropped += value != REDACTED
        spans.append({"trace_id": span["trace_id"], "span_id": span["span_id"], "name": name,
                      "time": span["time"], "attributes": kept})
    return spans, malformed, redactions, dropped


NO_TRUST = ("no trust anchors: pass --trust FILE with anchors obtained out of band; a trust.json "
            "shipped with the evidence is never used implicitly (synthetic fixtures only: --fixture-trust)")
FIXTURE_TRUST_WARNING = ("fixture mode: trust anchors are read from the evidence ({path}); anchors shipped "
                         "with the evidence prove nothing. Use --fixture-trust only for synthetic fixtures.")


def fixture_trust_file(bundle: Path) -> Path | None:
    """Fixture mode only: the ``trust.json`` shipped in the bundle or its parent directory."""
    for candidate in (bundle / "trust.json", bundle.parent / "trust.json"):
        if candidate.is_file():
            return candidate
    return None


def resolve_trust(bundle: Path, trust_path: str | Path | None, fixture_trust: bool = False) -> Path:
    """Return the trust anchor file; fail closed unless anchors were passed explicitly.

    An explicit file inside the bundle being verified is refused too: it is part of the
    evidence, whoever points at it. ``fixture_trust`` is the explicit, warned opt-in to
    the bundle-local lookup and is meant for the synthetic fixtures only.
    """
    if fixture_trust:
        if trust_path is not None:
            raise ReceiptError("pass either --trust or --fixture-trust, not both")
        found = fixture_trust_file(bundle)
        if found is None:
            raise ReceiptError("--fixture-trust: no trust.json in the bundle or its parent directory")
        return found
    if trust_path is None:
        raise ReceiptError(NO_TRUST)
    trust_file = Path(trust_path)
    if trust_file.resolve().is_relative_to(bundle.resolve()):
        raise ReceiptError(f"trust anchor file {trust_file} is inside the evidence bundle '{bundle.name}'; "
                           "anchors shipped with the evidence prove nothing. Obtain them out of band "
                           "(synthetic fixtures only: --fixture-trust)")
    return trust_file


def verify_bundle(bundle: str | Path, trust_path: str | Path | None = None,
                  now: datetime | None = None, *, fixture_trust: bool = False) -> dict[str, Any]:
    """Verify one evidence bundle directory and return a sanitized report.

    ``trust_path`` (anchors obtained out of band) is required unless ``fixture_trust``
    explicitly selects the anchors shipped with a synthetic fixture bundle.
    """
    bundle = Path(bundle)
    now = now or datetime.now(timezone.utc)
    trust_file = resolve_trust(bundle, trust_path, fixture_trust)
    trust = load_trust(trust_file)

    records: list[Record] = []
    for name in ("receipts.jsonl", "tool-records.jsonl"):
        for line, raw in _read_lines(bundle / name):
            record = Record(index=len(records), file=name, line=line)
            _verify_wire(record, raw, trust)
            records.append(record)

    guard = ReplayGuard()
    for record in records:
        if record.verdict not in (VALID, UNCHECKED) or record.body is None:
            continue
        body = record.body
        problem, earlier = guard.check(body["issuer"]["key_id"], body["nonce"], body["receipt_id"],
                                       record.digest or "", record.index)
        if problem == "duplicate":
            record.verdict = REPLAYED
            record.reasons.append(f"identical receipt already presented at "
                                  f"{records[earlier].file}:{records[earlier].line}")
        elif problem == "reuse":
            note = "signer reused a nonce or receipt_id for a different body (equivocation)"
            record.notes.append(note)
            records[earlier].notes.append(note)
            record.status = records[earlier].status = CONFLICTING
        if parse_time(body["issued_at"]) > now + timedelta(minutes=5):
            record.notes.append("claimed issue time is in the future relative to the verifier clock")

    verified = [r for r in records if r.verdict == VALID]
    for r in verified:
        if r.status != CONFLICTING:
            r.status = VERIFIABLE
        r.grade = "E2"
    for r in records:
        if r.verdict in (UNCHECKED, UNTRUSTED):
            r.grade = "E1"
            r.notes.append("signature unchecked or signer untrusted: content is an unverified claim")

    gaps = _check_chains(verified)
    movements = _movements(records, verified)
    effects = _effects(verified)
    subjects = _subjects(bundle, records)
    spans, bad_spans, redactions, dropped = _load_telemetry(bundle / "telemetry.jsonl")
    timeline = _timeline(records, spans, gaps)

    counts = {v: sum(r.verdict == v for r in records) for v in VERDICTS}
    status_counts = {s: sum(e["status"] == s for e in timeline) for s in (VERIFIABLE, UNVERIFIABLE, CONFLICTING)}
    rejected = any(counts[v] for v in REJECTED)
    conflicts = status_counts[CONFLICTING] > 0 or any(s["status"] == "DIGEST_MISMATCH" for s in subjects)
    if rejected or conflicts:
        exit_code = 1
    elif counts[UNCHECKED] or not counts[VALID]:
        exit_code = 3
    else:
        exit_code = 0
    return {
        "schema": REPORT_SCHEMA,
        "bundle": bundle.name,
        "trust_anchors": str(trust_file),
        "trust_anchor_mode": "fixture" if fixture_trust else "explicit",
        "signature_checking": f"Ed25519 via cryptography {CRYPTO_VERSION}" if HAVE_ED25519
        else "UNAVAILABLE (install the 'signing' extra); signatures reported as UNCHECKED",
        "verified_at": format_time(now),
        "receipts": [{"ref": r.ref, "source": f"{r.file}:{r.line}", "verdict": r.verdict,
                      "verified_principal": r.key.principal if r.key and r.verdict == VALID else None,
                      "reasons": r.reasons} for r in records],
        "receipt_verdicts": counts,
        "movements": movements,
        "effects": effects,
        "subjects": subjects,
        "lineage": _lineage(verified),
        "executions": _executions(verified),
        "timeline": timeline,
        "timeline_status": status_counts,
        "telemetry": {"spans": len(spans), "malformed_lines": bad_spans,
                      "redactions": redactions, "dropped_attributes": dropped},
        "exit_code": exit_code,
        "limits": list(LIMITS),
    }


def _check_chains(verified: list[Record]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    by_key: dict[str, list[Record]] = {}
    for r in verified:
        by_key.setdefault(r.key.key_id, []).append(r)  # type: ignore[union-attr]
    for key_id, chain in by_key.items():
        by_seq: dict[int, list[Record]] = {}
        for r in chain:
            by_seq.setdefault(r.body["seq"], []).append(r)  # type: ignore[index]
        for seq, same in by_seq.items():
            if len({r.digest for r in same}) > 1:
                for r in same:
                    r.conflict(f"signer issued different receipts with the same seq {seq} (chain fork)")
            for r in same:
                prev = r.body["prev_receipt_digest"]  # type: ignore[index]
                before = by_seq.get(seq - 1)
                if before and prev not in {b.digest for b in before}:
                    r.conflict("prev_receipt_digest does not match the signer's previous receipt")
                if seq > 1 and prev is None:
                    r.notes.append("seq > 1 but no prev_receipt_digest was signed")
        ordered = sorted(by_seq)
        for low, high in zip(ordered, ordered[1:]):
            if high != low + 1:
                successor = by_seq[high][0]
                gaps.append({"key_id": key_id, "principal": successor.key.principal,  # type: ignore[union-attr]
                             "missing_seq": [low + 1, high - 1], "before": successor.ref,
                             "time": successor.body["issued_at"]})  # type: ignore[index]
    return gaps


def _claim(status: str, value: Any = None, note: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"status": status, "value": value}
    if note:
        out["note"] = note
    return out


def _movements(records: list[Record], verified: list[Record]) -> dict[str, Any]:
    ids = sorted({r.body["movement"]["movement_id"] for r in records
                  if r.body is not None and r.body["movement"] is not None
                  and r.verdict in (VALID, UNCHECKED, UNTRUSTED)})
    out: dict[str, Any] = {}
    for mid in ids:
        mine = [r for r in verified if r.body["movement"] and r.body["movement"]["movement_id"] == mid]  # type: ignore[index]
        claims_only = [r for r in records if r.verdict in (UNCHECKED, UNTRUSTED) and r.body
                       and r.body["movement"] and r.body["movement"]["movement_id"] == mid]
        dispatches = [r for r in mine if r.body["receipt_type"] == "movement.dispatched"]  # type: ignore[index]
        responses = [r for r in mine if r.body["receipt_type"] in RESPONSE_TYPES]  # type: ignore[index]

        # Source: bound by the dispatch signer's trust anchor, never by the label.
        if dispatches:
            source_conflict = False
            for d in dispatches:
                claimed = d.body["source"]["claimed_principal"] if d.body["source"] else None  # type: ignore[index]
                if claimed is not None and claimed != d.key.principal:  # type: ignore[union-attr]
                    d.conflict("dispatch signer is not the principal it names as source")
                    source_conflict = True
            principals = sorted({d.key.principal for d in dispatches})  # type: ignore[union-attr]
            source = _claim(CONFLICTING if source_conflict or len(principals) > 1 else VERIFIED,
                            principals if len(principals) > 1 else principals[0])
        else:
            src = [r.body["source"]["claimed_principal"] for r in claims_only  # type: ignore[index]
                   if r.body["receipt_type"] == "movement.dispatched" and r.body["source"]]  # type: ignore[index]
            source = _claim(UNVERIFIED_CLAIM, src[0]) if src and src[0] else \
                _claim(UNKNOWN, note="no verified dispatch receipt")

        named = {d.body["destination"]["claimed_principal"] for d in dispatches  # type: ignore[index]
                 if d.body["destination"] and d.body["destination"]["claimed_principal"]}  # type: ignore[index]
        dest_conflict = len({r.key.principal for r in responses}) > 1  # type: ignore[union-attr]
        for r in responses:
            claimed = r.body["destination"]["claimed_principal"] if r.body["destination"] else None  # type: ignore[index]
            if claimed is not None and claimed != r.key.principal:  # type: ignore[union-attr]
                r.conflict("response signer is not the principal it names as destination")
                dest_conflict = True
            if named and r.key.principal not in named:  # type: ignore[union-attr]
                dest_conflict = True
                r.conflict("response signed by a principal other than the dispatched destination (swap)")
                for d in dispatches:
                    d.conflict("destination named in dispatch did not sign the response")
            for d in dispatches:
                if d.body["logical_task_id"] != r.body["logical_task_id"]:  # type: ignore[index]
                    r.conflict("dispatch and response disagree on logical_task_id")
                    d.conflict("dispatch and response disagree on logical_task_id")
        decisions = {(r.key.principal, r.body["receipt_type"], r.body["outcome"]) for r in responses}  # type: ignore[union-attr,index]
        if len(decisions) > 1:
            for r in responses:
                r.conflict("contradictory signed responses for one movement")
        for d in dispatches:
            for r in responses:
                if d.status != CONFLICTING and r.status != CONFLICTING:
                    d.grade = r.grade = "E3"
                    d.corroborated_by.append(r.ref)
                    r.corroborated_by.append(d.ref)

        if responses:
            principals = sorted({r.key.principal for r in responses})  # type: ignore[union-attr]
            destination = _claim(CONFLICTING if dest_conflict else VERIFIED,
                                 principals if len(principals) > 1 else principals[0],
                                 None if named else "dispatch did not name a destination principal")
            outcomes = sorted({r.body["outcome"] or "null" for r in responses})  # type: ignore[index]
            outcome = _claim(CONFLICTING if len(decisions) > 1 else SIGNED_CLAIM,
                             outcomes if len(outcomes) > 1 else outcomes[0])
            executions = sorted({r.body["destination"]["execution_id"] for r in responses  # type: ignore[index]
                                 if r.body["destination"] and r.body["destination"]["execution_id"]})  # type: ignore[index]
            dest_exec = _claim(SIGNED_CLAIM, executions[0]) if len(executions) == 1 else \
                _claim(CONFLICTING, executions) if executions else _claim(UNKNOWN)
        else:
            destination = _claim(SIGNED_CLAIM, sorted(named)[0],
                                 "named by the source only; destination never signed") if named else \
                _claim(UNKNOWN, note="no verified response and no named destination")
            outcome = _claim(UNKNOWN, note="no verified response from the destination; this is not a failure")
            dest_exec = _claim(UNKNOWN)

        def label(side: str) -> dict[str, Any]:
            signed = sorted({r.body[side]["claimed_agent_id"] for r in mine  # type: ignore[index]
                             if r.body[side] and r.body[side]["claimed_agent_id"]})  # type: ignore[index]
            loose = sorted({r.body[side]["claimed_agent_id"] for r in claims_only  # type: ignore[index]
                            if r.body[side] and r.body[side]["claimed_agent_id"]})  # type: ignore[index]
            if len(signed) > 1:
                return _claim(CONFLICTING, signed)
            if signed:
                return _claim(SIGNED_CLAIM, signed[0], "agent labels are never bound to keys")
            if loose:
                return _claim(UNVERIFIED_CLAIM, loose)
            return _claim(UNKNOWN)

        traces = sorted({r.body["correlation"]["trace_id"] for r in mine + claims_only  # type: ignore[index]
                         if r.body["correlation"]["trace_id"]})  # type: ignore[index]
        grade = "E3" if any(r.grade == "E3" for r in mine) else "E2" if mine else "E1" if claims_only else None
        movement = (mine + claims_only)[0].body["movement"]  # type: ignore[index]
        out[mid] = {
            "logical_task_ids": sorted({r.body["logical_task_id"] or "null" for r in mine + claims_only}),  # type: ignore[index]
            "lineage_relation": movement["lineage_relation"],
            "parent_movement_id": movement["parent_movement_id"],
            "source_principal": source, "source_agent_label": label("source"),
            "destination_principal": destination, "destination_agent_label": label("destination"),
            "destination_execution_id": dest_exec, "outcome": outcome,
            "trace_ids": _claim(CORRELATION_ONLY, traces, "correlation only; never authentication"),
            "grade": grade,
        }
    return out


def _effects(verified: list[Record]) -> list[dict[str, Any]]:
    claims: dict[tuple[str, str], list[Record]] = {}
    tools: dict[tuple[str, str], list[Record]] = {}
    for r in verified:
        if r.body["effect"] is None:  # type: ignore[index]
            continue
        slot = (r.body["logical_task_id"] or "null", r.body["effect"]["effect_id"])  # type: ignore[index]
        (tools if r.body["receipt_type"] == "tool.effect_recorded" else claims).setdefault(slot, []).append(r)  # type: ignore[index]
    out = []
    for slot in sorted(set(claims) | set(tools)):
        agent, tool = claims.get(slot, []), tools.get(slot, [])
        if not tool:
            status = UNKNOWN
            for r in agent:
                r.notes.append("no independent tool-side record for the claimed effect")
        elif not agent:
            status = "TOOL_RECORD_ONLY"
        else:
            status = "CONFIRMED_BY_TOOL"
            for a in agent:
                for t in tool:
                    invoker = t.body["source"]["claimed_principal"] if t.body["source"] else None  # type: ignore[index]
                    named_tool = a.body["effect"]["tool_principal"]  # type: ignore[index]
                    if a.body["effect"]["status"] != t.body["effect"]["status"] or \
                            (invoker is not None and invoker != a.key.principal) or \
                            (named_tool is not None and named_tool != t.key.principal):  # type: ignore[index,union-attr]
                        status = CONFLICTING
                        a.conflict("agent's effect claim contradicts the independent tool-side record")
                        t.conflict("tool-side record contradicts the agent's effect claim")
            if status == "CONFIRMED_BY_TOOL":
                for r in agent + tool:
                    r.grade = "E3"
                for a in agent:
                    a.corroborated_by.extend(t.ref for t in tool)
                for t in tool:
                    t.corroborated_by.extend(a.ref for a in agent)
        out.append({"logical_task_id": slot[0], "effect_id": slot[1], "status": status,
                    "agent_claims": sorted({r.body["effect"]["status"] for r in agent}),  # type: ignore[index]
                    "tool_records": sorted({r.body["effect"]["status"] for r in tool})})  # type: ignore[index]
    return out


def _subjects(bundle: Path, records: list[Record]) -> list[dict[str, Any]]:
    out, seen = [], set()
    for r in records:
        if r.body is None or r.verdict not in (VALID, UNCHECKED):
            continue
        for s in r.body["subjects"]:
            slot = (s["ref"], s["digest"])
            if slot in seen:
                continue
            seen.add(slot)
            path = bundle / "subjects" / f"{s['ref']}.json"
            if not path.is_file():
                status = UNKNOWN
            else:
                try:
                    status = "DIGEST_MATCH" if jcs_digest(parse_json(path.read_bytes())) == s["digest"] \
                        else "DIGEST_MISMATCH"
                except (ContractError, CanonicalizationError):
                    status = "UNREADABLE"
            if status == "DIGEST_MISMATCH":
                r.conflict(f"provided {s['role']} '{s['ref']}' does not match the signed digest")
            out.append({"ref": s["ref"], "role": s["role"], "status": status, "signed_by": r.ref})
    return out


def _lineage(verified: list[Record]) -> list[dict[str, Any]]:
    edges = {}
    for r in verified:
        m = r.body["movement"]  # type: ignore[index]
        if m and m["parent_movement_id"]:
            edges[(m["parent_movement_id"], m["movement_id"])] = m["lineage_relation"]
    return [{"parent_movement_id": p, "movement_id": c, "relation": rel, "status": SIGNED_CLAIM}
            for (p, c), rel in sorted(edges.items(), key=lambda x: (x[0][0], x[0][1]))]


def _executions(verified: list[Record]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for r in verified:
        e = r.body["execution"]  # type: ignore[index]
        if e and e["execution_id"]:
            entry = seen.setdefault(e["execution_id"], {
                "execution_id": e["execution_id"], "logical_task_id": r.body["logical_task_id"],  # type: ignore[index]
                "parent_execution_id": e["parent_execution_id"], "definition_digest": e["definition_digest"],
                "attested_by": r.key.principal})  # type: ignore[union-attr]
            if entry["attested_by"] != r.key.principal:  # type: ignore[union-attr]
                entry["attested_by"] = "MULTIPLE"
    out = sorted(seen.values(), key=lambda x: x["execution_id"])
    for entry in out:
        twins = [x["execution_id"] for x in out if x is not entry and x["definition_digest"]
                 and x["definition_digest"] == entry["definition_digest"]]
        entry["shares_definition_with"] = twins  # same definition != same agent
    return out


def _timeline(records: list[Record], spans: list[dict[str, Any]],
              gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    by_ref: dict[str, int] = {}
    trace_index: dict[str, list[str]] = {}
    for r in records:
        if r.body is None or r.verdict not in (VALID, UNCHECKED, UNTRUSTED):
            continue
        b = r.body
        actor_party = b["source"] if b["receipt_type"] == "movement.dispatched" else b["destination"]
        node = {
            "ref": r.ref, "event_type": b["receipt_type"], "claimed_time": b["issued_at"],
            "logical_task_id": b["logical_task_id"],
            "movement_id": b["movement"]["movement_id"] if b["movement"] else None,
            "execution_id": b["execution"]["execution_id"] if b["execution"] else None,
            "outcome": b["outcome"],
            "actor": {"verified_principal": r.key.principal if r.verdict == VALID and r.key else None,
                      "claimed_principal": b["issuer"]["claimed_principal"],
                      "claimed_agent_id": b["issuer"]["claimed_agent_id"] or
                      (actor_party["claimed_agent_id"] if actor_party else None)},
            "status": r.status, "grade": r.grade, "receipt_verdict": r.verdict,
            "trace_id": b["correlation"]["trace_id"],
            "corroborated_by": sorted(set(r.corroborated_by)), "notes": list(r.notes),
            "_record": r,
        }
        if node["trace_id"]:
            trace_index.setdefault(node["trace_id"], []).append(r.ref)
        by_ref[r.ref] = len(nodes)
        nodes.append(node)
    for span in spans:
        attrs = span["attributes"]
        nodes.append({
            "ref": f"telemetry:{span['span_id']}", "event_type": f"telemetry:{span['name']}",
            "claimed_time": span["time"], "logical_task_id": attrs.get("logical_task_id"),
            "movement_id": attrs.get("movement_id"), "execution_id": attrs.get("execution_id"),
            "outcome": attrs.get("outcome"),
            "actor": {"verified_principal": None, "claimed_principal": None,
                      "claimed_agent_id": attrs.get("agent.claimed_id")},
            "status": UNVERIFIABLE, "grade": "E1", "receipt_verdict": None, "trace_id": span["trace_id"],
            "corroborated_by": [],
            "notes": ["unsigned telemetry: names, labels and trace_id are claims/correlation, not authentication"],
        })
    for gap in gaps:
        nodes.append({
            "ref": f"gap:{gap['key_id']}:{gap['missing_seq'][0]}-{gap['missing_seq'][1]}",
            "event_type": "evidence.gap_detected", "claimed_time": gap["time"],
            "logical_task_id": None, "movement_id": None, "execution_id": None, "outcome": None,
            "actor": {"verified_principal": gap["principal"], "claimed_principal": None, "claimed_agent_id": None},
            "status": UNVERIFIABLE, "grade": None, "receipt_verdict": None, "trace_id": None,
            "corroborated_by": [],
            "notes": [f"receipts seq {gap['missing_seq'][0]}..{gap['missing_seq'][1]} from this signer are "
                      "absent; absence of a receipt is not evidence that nothing happened"],
            "_before": gap["before"],
        })
    for node in nodes:
        if node["ref"].startswith("telemetry:") and node["trace_id"] in trace_index:
            node["correlated_receipts"] = sorted(trace_index[node["trace_id"]])
            node["notes"].append("shares a trace_id with signed receipts: correlation only")

    # Causal edges: per-signer sequence, dispatch -> response -> execution, parent -> child.
    edges: dict[int, set[int]] = {i: set() for i in range(len(nodes))}
    receipts = [(i, n["_record"]) for i, n in enumerate(nodes) if "_record" in n]
    trusted = [(i, r) for i, r in receipts if r.verdict == VALID]
    chain: dict[str, list[tuple[int, int]]] = {}
    for i, r in trusted:
        chain.setdefault(r.key.key_id, []).append((r.body["seq"], i))
    for items in chain.values():
        items.sort()
        for (_, a), (_, b) in zip(items, items[1:]):
            edges[a].add(b)
    for i, node in enumerate(nodes):
        if "_before" in node and node["_before"] in by_ref:
            edges[i].add(by_ref[node["_before"]])
    stage = {"movement.dispatched": 0, "movement.accepted": 1, "movement.rejected": 1,
             "execution.started": 2, "execution.completed": 3}
    for i, a in trusted:
        for j, b in trusted:
            ma, mb = a.body["movement"], b.body["movement"]
            if not ma or not mb or i == j:
                continue
            ta, tb = a.body["receipt_type"], b.body["receipt_type"]
            if ma["movement_id"] == mb["movement_id"] and ta in stage and tb in stage and stage[ta] < stage[tb]:
                edges[i].add(j)
            if mb["parent_movement_id"] == ma["movement_id"] and ta in RESPONSE_TYPES \
                    and tb == "movement.dispatched":
                edges[i].add(j)
    indegree = {i: 0 for i in edges}
    preds: dict[int, list[int]] = {i: [] for i in edges}
    for a, targets in edges.items():
        for b in targets:
            indegree[b] += 1
            preds[b].append(a)

    def key(i: int) -> tuple[str, str]:
        return nodes[i]["claimed_time"], nodes[i]["ref"]

    ready = [(key(i), i) for i, d in indegree.items() if d == 0]
    heapq.heapify(ready)
    order: list[int] = []
    placed: set[int] = set()
    while len(order) < len(nodes):
        if not ready:  # cycle in claimed links: fall back to claimed time
            rest = sorted((i for i in edges if i not in placed), key=key)
            nodes[rest[0]]["notes"].append("causal links form a cycle; placed by claimed time")
            indegree[rest[0]] = 0
            heapq.heappush(ready, (key(rest[0]), rest[0]))
        _, i = heapq.heappop(ready)
        if i in placed:
            continue
        placed.add(i)
        order.append(i)
        for j in edges[i]:
            indegree[j] -= 1
            if indegree[j] == 0:
                heapq.heappush(ready, (key(j), j))
    timeline = []
    for position, i in enumerate(order, 1):
        node = {k: v for k, v in nodes[i].items() if not k.startswith("_")}
        node["order"] = position
        node["ordering_basis"] = "causal+claimed_time" if preds[i] else "claimed_time"
        for p in preds[i]:
            if nodes[p]["claimed_time"] > node["claimed_time"]:
                node["notes"].append(f"claimed time precedes causal predecessor {nodes[p]['ref']}: "
                                     "clock skew or false timestamp; causal order used")
        timeline.append(node)
    return timeline


# --------------------------------------------------------------------------- CLI

def bundles_under(path: Path) -> list[Path]:
    if (path / "receipts.jsonl").is_file() or (path / "tool-records.jsonl").is_file():
        return [path]
    return sorted(p for p in path.iterdir() if p.is_dir() and
                  ((p / "receipts.jsonl").is_file() or (p / "tool-records.jsonl").is_file()))


def render_text(report: dict[str, Any]) -> str:
    mode = ", FIXTURE MODE: shipped with the evidence, proves nothing" \
        if report["trust_anchor_mode"] == "fixture" else ""
    lines = [f"bundle {report['bundle']}  (trust anchors: {report['trust_anchors']}{mode})",
             f"  signature checking: {report['signature_checking']}",
             "  receipts: " + ", ".join(f"{v} {k}" for k, v in report["receipt_verdicts"].items() if v)]
    for r in report["receipts"]:
        if r["verdict"] != VALID:
            where = "" if r["ref"] == r["source"] else f" ({r['source']})"
            lines.append(f"    [{r['verdict']:<9}] {r['ref']}{where}: " + "; ".join(r["reasons"]))
    for mid, m in report["movements"].items():
        lines.append(f"  movement {mid} [{m['lineage_relation']}] grade={m['grade']}")
        for name in ("source_principal", "destination_principal", "destination_execution_id", "outcome",
                     "source_agent_label", "destination_agent_label", "trace_ids"):
            claim = m[name]
            note = f"  ({claim['note']})" if claim.get("note") else ""
            lines.append(f"      {name:<25} {claim['status']:<17} {claim['value']}{note}")
    for e in report["effects"]:
        lines.append(f"  effect {e['effect_id']} (task {e['logical_task_id']}): {e['status']} "
                     f"agent={e['agent_claims']} tool={e['tool_records']}")
    for s in report["subjects"]:
        lines.append(f"  subject {s['role']} {s['ref']}: {s['status']}")
    for edge in report["lineage"]:
        lines.append(f"  lineage {edge['parent_movement_id']} -[{edge['relation']}]-> {edge['movement_id']}")
    for ex in report["executions"]:
        if ex["shares_definition_with"]:
            lines.append(f"  execution {ex['execution_id']} shares definition digest with "
                         f"{ex['shares_definition_with']}: kept distinct")
    lines.append("  timeline: " + ", ".join(f"{v} {k}" for k, v in report["timeline_status"].items()))
    for e in report["timeline"]:
        who = e["actor"]["verified_principal"] or f"claimed:{e['actor']['claimed_agent_id']}"
        lines.append(f"    {e['order']:>2}. {e['claimed_time']} {e['status']:<12} {e['grade'] or '--':<2} "
                     f"{e['event_type']} mov={e['movement_id']} by={who} [{e['ordering_basis']}]")
        for note in e["notes"]:
            lines.append(f"          - {note}")
    t = report["telemetry"]
    lines.append(f"  telemetry: {t['spans']} spans, {t['malformed_lines']} malformed lines skipped, "
                 f"{t['redactions']} values redacted, {t['dropped_attributes']} attributes dropped")
    lines.append(f"  exit code {report['exit_code']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent_movement.receipts",
                                     description="Offline verifier for experimental signed movement receipts")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="verify one bundle or a directory of bundles")
    timeline = sub.add_parser("timeline", help="print only the sanitized timeline JSON of one bundle")
    for command in (verify, timeline):
        command.add_argument("path", type=Path)
        anchors = command.add_mutually_exclusive_group()
        anchors.add_argument("--trust", type=Path,
                             help="REQUIRED: trust anchor file obtained out of band, never from the bundle")
        anchors.add_argument("--fixture-trust", action="store_true",
                             help="synthetic fixtures only: use the trust.json shipped in the bundle or its "
                                  "parent directory, with a warning (such anchors prove nothing)")
        command.add_argument("--now", help="verifier clock, YYYY-MM-DDTHH:MM:SSZ (default: system clock)")
    verify.add_argument("--json", action="store_true", help="print the full JSON report")
    make = sub.add_parser("make-fixtures", help="regenerate the deterministic synthetic fixture set")
    make.add_argument("path", type=Path)
    options = parser.parse_args(argv)
    try:
        if options.command == "make-fixtures":
            from .receipt_fixtures import write_fixtures
            write_fixtures(options.path)
            print(f"wrote synthetic fixtures to {options.path}")
            return 0
        if options.trust is None and not options.fixture_trust:
            raise ReceiptError(NO_TRUST)  # fail closed before reading any evidence
        now = parse_time(options.now) if options.now else None
        bundles = bundles_under(options.path)
        if not bundles:
            raise ReceiptError("no bundle (receipts.jsonl or tool-records.jsonl) found")
        if options.command == "timeline":
            bundles = bundles[:1]
        reports = [verify_bundle(b, options.trust, now, fixture_trust=options.fixture_trust) for b in bundles]
    except (ReceiptError, ContractError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if options.fixture_trust:
        for path in sorted({r["trust_anchors"] for r in reports}):
            print("WARNING: " + FIXTURE_TRUST_WARNING.format(path=path), file=sys.stderr)
    if options.command == "timeline":
        print(json.dumps(reports[0]["timeline"], indent=2, ensure_ascii=False))
        return reports[0]["exit_code"]
    if options.json:
        print(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2, ensure_ascii=False))
    else:
        print("\n\n".join(render_text(r) for r in reports))
        print("\nLimits: " + " ".join(LIMITS))
    codes = {r["exit_code"] for r in reports}
    return 1 if 1 in codes else 3 if 3 in codes else 0


if __name__ == "__main__":
    sys.exit(main())
