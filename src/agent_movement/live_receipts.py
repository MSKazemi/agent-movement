"""Optional, default-off signed receipts on the PR #6 live localhost HTTP path (issue #32).

What it does when enabled (``python -m agent_movement.demo --receipts OUTDIR`` or
``python -m agent_movement.http --receipts-log FILE``):

* the sender signs ``movement.dispatched`` before it POSTs a handoff;
* the receiver signs ``movement.accepted`` plus ``execution.completed`` for a new
  delivery, or ``movement.rejected`` for a policy denial, before it answers;
* a recording effect gateway signs ``tool.effect_recorded`` (committed or rejected)
  for every fenced simulated-effect commit attempt;
* the receiver signs ``authority.revoked`` when it applies a new runtime revocation of
  one of its approvals (issue #38). The receipt references the signed notice by its
  plain JCS digest (a ``revocation_notice`` subject, :func:`notice_subject_ref`): the
  notice is a public signed document, so it is neither salted nor secret;
* :func:`export_run` writes the run's receipts as one evidence bundle and a SEPARATE
  trust anchor file outside the bundle, which the offline verifier accepts.

Keys are SYNTHETIC and EPHEMERAL: each participant draws a fresh Ed25519 seed per run,
keeps it in memory only and publishes only the public half. Receipts never contain task
text: envelopes, artifacts and effect payloads are referenced by digests of SALTED
commitments, and the commitment documents themselves stay in process memory
(:attr:`ReceiptEmitter.commitments`); they are never written to the bundle.

Emission is best-effort and never changes a handoff's outcome: a receipt that cannot be
signed or written is counted in :attr:`ReceiptEmitter.failures` and shows up in the
verifier as an absent receipt (UNKNOWN), never as a fabricated one.
Requires the optional ``signing`` extra.
"""

from __future__ import annotations

import json
import secrets
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .core import ID, Conflict, EffectGateway, PolicyDenied, SQLiteStore
from .jcs import canonicalize, jcs_digest
from .receipts import (
    RECEIPT_SCHEMA,
    TRUST_SCHEMA,
    Ed25519Signer,
    ReceiptError,
    _require_crypto,
    commitment,
    format_time,
    validate_body,
)

LIVE_DOMAIN = "spiffe://synthetic.test/live"
BUNDLE_NAME = "live-run"
TRUST_NAME = "trust-anchors.json"
TRUST_NOTE = ("SYNTHETIC, EPHEMERAL anchors for one local demo run. Each private key existed only in its "
              "participant's memory. Obtained by the orchestrator from the participants, not from the bundle.")


def live_principal(name: str, role: str = "agent") -> str:
    """Synthetic principal for a live participant; never a real identity."""
    return f"{LIVE_DOMAIN}/{role}/{name}"


def _now() -> datetime:
    return datetime.now(UTC)


def notice_subject_ref(notice: Any) -> str:
    """Deterministic subject ref for a revocation notice: anyone holding the notice can
    place it at ``subjects/<ref>.json`` for the verifier to check against the signed digest."""
    return "notice-" + jcs_digest(notice)[len("sha256:"):][:32]


class ReceiptEmitter:
    """Signs and appends one participant's receipts to a JSONL log; thread-safe.

    ``role`` is ``agent`` (movement and execution receipts) or ``tool`` (effect records).
    Each emitter is its own signer with its own per-key ``seq``/``prev_receipt_digest``
    chain. ``receipt_id`` is ``<key_id>.<seq>``, so it is unique per key by construction.
    """

    def __init__(self, log_path: str | Path, *, name: str, role: str = "agent",
                 principal: str | None = None, clock: Callable[[], datetime] = _now):
        _require_crypto()
        if not isinstance(name, str) or not ID.fullmatch(name) or len(name) > 64:
            raise ReceiptError("invalid participant name")
        if role not in ("agent", "tool"):
            raise ReceiptError("role must be 'agent' or 'tool'")
        self.name, self.role = name, role
        self.principal = principal or live_principal(name, role)
        self.key_id = f"live-{name}-{secrets.token_hex(4)}"
        self._signer = Ed25519Signer(self.key_id, secrets.token_bytes(32))  # never persisted
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch()
        self._clock = clock
        self._lock = threading.Lock()
        self._seq = 0
        self._prev: str | None = None
        self._emitted: set[tuple[Any, ...]] = set()
        self.commitments: dict[str, dict[str, Any]] = {}  # in memory only; may contain task text
        self.failures = 0

    def descriptor(self) -> dict[str, str]:
        """Public half only: what a participant hands to the orchestrator out of band."""
        return {"key_id": self.key_id, "principal": self.principal, "role": self.role,
                "public_key": self._signer.public_key}

    # ------------------------------------------------------------------ emission core

    def _emit(self, once: tuple[Any, ...], build: Callable[[str, int, str | None, str], dict[str, Any]]) -> bool:
        """Sign and append one receipt unless ``once`` was already emitted; never raises."""
        with self._lock:
            if once in self._emitted:
                return False
            try:
                seq = self._seq + 1
                receipt_id = f"{self.key_id}.{seq}"
                body = validate_body(build(receipt_id, seq, self._prev, format_time(self._clock())))
                wire = self._signer.seal(body)
                with self.log_path.open("ab") as log:
                    log.write(canonicalize(wire) + b"\n")
            except Exception:  # noqa: BLE001 - best-effort: a lost receipt is a gap, never a changed outcome
                self.failures += 1
                return False
            self._seq, self._prev = seq, wire["body_digest"]
            self._emitted.add(once)
            return True

    def _commit_to(self, ref: str, value: Any) -> str:
        doc = commitment(value, secrets.token_hex(16))  # fresh 128-bit salt per subject
        self.commitments[ref] = doc
        return jcs_digest(doc)

    def _body(self, receipt_type: str, receipt_id: str, seq: int, prev: str | None, issued_at: str, *,
              agent_label: str | None, task_id: str | None, movement_id: str | None = None,
              audience: str | None = None, source: dict[str, Any] | None = None,
              destination: dict[str, Any] | None = None, execution: dict[str, Any] | None = None,
              subjects: Iterable[tuple[str, str, Any]] = (), effect: dict[str, Any] | None = None,
              outcome: str | None = None, classification: str = "synthetic") -> dict[str, Any]:
        return {
            "schema": RECEIPT_SCHEMA, "receipt_id": receipt_id, "receipt_type": receipt_type,
            "issuer": {"key_id": self.key_id, "claimed_principal": self.principal, "claimed_agent_id": agent_label},
            "audience": audience, "nonce": secrets.token_hex(16), "issued_at": issued_at, "seq": seq,
            "prev_receipt_digest": prev, "logical_task_id": task_id,
            "movement": None if movement_id is None else
            {"movement_id": movement_id, "parent_movement_id": None, "lineage_relation": "delegate"},
            "source": source, "destination": destination, "execution": execution,
            # PR #6 trace IDs are opaque local strings, not W3C trace-ids, so none is carried.
            "correlation": {"trace_id": None, "span_id": None},
            "subjects": [{"role": role, "ref": ref, "digest": self._commit_to(ref, value)}
                         for role, ref, value in subjects],
            "effect": effect, "outcome": outcome, "data_classification": classification,
        }

    # ------------------------------------------------------------------ live events

    def dispatched(self, envelope: dict[str, Any], destination_principal: str | None = None) -> bool:
        """Sender side, before transmission. One dispatch per movement: a retry re-delivers it."""
        def build(receipt_id: str, seq: int, prev: str | None, issued_at: str) -> dict[str, Any]:
            return self._body(
                "movement.dispatched", receipt_id, seq, prev, issued_at,
                agent_label=envelope["origin"]["agent_id"], task_id=envelope["logical_task_id"],
                movement_id=envelope["movement_id"], audience=destination_principal,
                source={"claimed_agent_id": envelope["origin"]["agent_id"], "claimed_principal": self.principal,
                        "execution_id": None},
                destination={"claimed_agent_id": envelope["destination"]["agent_id"],
                             "claimed_principal": destination_principal, "execution_id": None},
                subjects=(("envelope", f"{receipt_id}.envelope", envelope),), outcome="dispatched",
                classification=envelope["context"]["classification"])
        return self._emit(("dispatch", envelope["movement_id"]), build)

    def accepted(self, envelope: dict[str, Any], core_receipt: dict[str, Any]) -> bool:
        """Receiver side, for a NEW delivery (an idempotent replay emits nothing)."""
        if core_receipt.get("replayed"):
            return False
        accepted = self._emit(("response", envelope["movement_id"]), self._response(envelope, "accepted"))
        if not accepted:
            return False

        def build(receipt_id: str, seq: int, prev: str | None, issued_at: str) -> dict[str, Any]:
            return self._body(
                "execution.completed", receipt_id, seq, prev, issued_at,
                agent_label=envelope["destination"]["agent_id"], task_id=envelope["logical_task_id"],
                movement_id=envelope["movement_id"],
                destination={"claimed_agent_id": envelope["destination"]["agent_id"],
                             "claimed_principal": self.principal, "execution_id": None},
                execution={"execution_id": None, "parent_execution_id": None, "agent_instance_id": None,
                           "definition_digest": None},
                subjects=(("artifact", f"{receipt_id}.artifact", core_receipt["artifact"]),),
                outcome="completed" if core_receipt.get("status") == "completed" else "unknown",
                classification=envelope["context"]["classification"])
        return self._emit(("completed", envelope["movement_id"]), build)

    def rejected(self, envelope: dict[str, Any]) -> bool:
        """Receiver side, for a policy denial. At most one signed response per movement."""
        return self._emit(("response", envelope["movement_id"]), self._response(envelope, "rejected"))

    def _response(self, envelope: dict[str, Any],
                  decision: str) -> Callable[[str, int, str | None, str], dict[str, Any]]:
        def build(receipt_id: str, seq: int, prev: str | None, issued_at: str) -> dict[str, Any]:
            return self._body(
                f"movement.{decision}", receipt_id, seq, prev, issued_at,
                agent_label=envelope["destination"]["agent_id"], task_id=envelope["logical_task_id"],
                movement_id=envelope["movement_id"],
                # PR #6 does not authenticate the sender: its label stays a claim, its principal unknown.
                source={"claimed_agent_id": envelope["origin"]["agent_id"], "claimed_principal": None,
                        "execution_id": None},
                destination={"claimed_agent_id": envelope["destination"]["agent_id"],
                             "claimed_principal": self.principal, "execution_id": None},
                subjects=(("envelope", f"{receipt_id}.envelope", envelope),), outcome=decision,
                classification=envelope["context"]["classification"])
        return build

    def effect_recorded(self, *, task_id: str, effect_id: str, agent_id: str, epoch: int, status: str,
                        payload: str) -> bool:
        """Tool side: the gateway's own record of one fenced commit attempt."""
        def build(receipt_id: str, seq: int, prev: str | None, issued_at: str) -> dict[str, Any]:
            return self._body(
                "tool.effect_recorded", receipt_id, seq, prev, issued_at, agent_label=None, task_id=task_id,
                # The PR #6 gateway does not authenticate its caller: the agent label is a claim.
                source={"claimed_agent_id": agent_id, "claimed_principal": None, "execution_id": None},
                subjects=(("effect_payload", f"{receipt_id}.payload", payload),),
                effect={"effect_id": effect_id, "tool_principal": self.principal, "status": status,
                        "fencing_epoch": epoch})
        return self._emit(("effect", task_id, effect_id, agent_id, epoch, status), build)

    def revoked(self, notice: Any, approval_ref: str, task_id: str) -> bool:
        """Receiver side: a verified runtime revocation was newly applied (issue #38).

        Once per approval: re-applying the same revocation is idempotent and signs nothing.
        The receipt says the receiver applied the notice; the notice's own signature is the
        evidence that the authority issued it.
        """
        external = {"role": "revocation_notice", "ref": notice_subject_ref(notice), "digest": jcs_digest(notice)}

        def build(receipt_id: str, seq: int, prev: str | None, issued_at: str) -> dict[str, Any]:
            body = self._body(
                "authority.revoked", receipt_id, seq, prev, issued_at, agent_label=self.name, task_id=task_id,
                destination={"claimed_agent_id": self.name, "claimed_principal": self.principal,
                             "execution_id": None},
                outcome="revoked")
            body["subjects"] = [external]
            return body
        return self._emit(("revoked", approval_ref), build)


class RecordingEffectGateway(EffectGateway):
    """PR #6 fenced gateway that also signs a tool-side record of each commit attempt.

    A new commit is recorded as ``committed``; a fenced (stale epoch) or conflicting
    attempt as ``rejected``, and the original exception is re-raised unchanged. An
    identical replay that commits nothing new records nothing.
    """

    def __init__(self, store: SQLiteStore, receipts: ReceiptEmitter):
        super().__init__(store)
        if receipts.role != "tool":
            raise ReceiptError("effect records must be signed by a key with role 'tool'")
        self.receipts = receipts

    def commit(self, task_id: str, agent_id: str, epoch: int, effect_id: str, payload: str) -> bool:
        record: dict[str, Any] = {"task_id": task_id, "effect_id": effect_id, "agent_id": agent_id,
                                  "epoch": epoch, "payload": payload}
        try:
            committed = super().commit(task_id, agent_id, epoch, effect_id, payload)
        except (PolicyDenied, Conflict):
            self.receipts.effect_recorded(status="rejected", **record)
            raise
        if committed:
            self.receipts.effect_recorded(status="committed", **record)
        return committed


# ---------------------------------------------------------------------- export

def trust_document(descriptors: Iterable[dict[str, str]], *, not_before: datetime, not_after: datetime,
                   revocation_issuers: Iterable[dict[str, str]] = ()) -> dict[str, Any]:
    """Trust anchor document for the participants' PUBLIC descriptors."""
    keys = [{"key_id": d["key_id"], "principal": d["principal"], "role": d["role"], "alg": "Ed25519",
             "public_key": d["public_key"], "not_before": format_time(not_before),
             "not_after": format_time(not_after), "revoked_at": None, "revocation_ref": None}
            for d in descriptors]
    doc: dict[str, Any] = {"schema": TRUST_SCHEMA, "note": TRUST_NOTE, "keys": keys}
    issuers = list(revocation_issuers)
    if issuers:
        doc["revocation_issuers"] = issuers
    return doc


def _jsonl(paths: Iterable[str | Path]) -> bytes:
    out = b""
    for path in paths:
        data = Path(path).read_bytes()
        out += data if not data or data.endswith(b"\n") else data + b"\n"
    return out


def export_run(outdir: str | Path, *, receipt_logs: Iterable[str | Path], tool_logs: Iterable[str | Path] = (),
               descriptors: Iterable[dict[str, str]], not_before: datetime,
               not_after: datetime | None = None,
               revocation_issuers: Iterable[dict[str, str]] = (),
               notices: Iterable[Any] = ()) -> tuple[Path, Path]:
    """Write ``<outdir>/live-run/`` (the evidence) and ``<outdir>/trust-anchors.json`` (NOT evidence).

    The anchor file sits beside the bundle, never inside it, because anchors shipped with
    the evidence prove nothing. An existing non-empty bundle directory is refused so two
    runs are never mixed into one body of evidence. Commitment documents are not exported.
    ``notices`` are approval revocation notices (public signed documents) written to
    ``subjects/<notice_subject_ref>.json`` so the verifier can match ``authority.revoked``
    subjects. They are not key revocations and do not go to ``revocations.jsonl``.
    """
    outdir = Path(outdir)
    bundle, trust = outdir / BUNDLE_NAME, outdir / TRUST_NAME
    if bundle.exists() and any(bundle.iterdir()):
        raise ReceiptError(f"{bundle} already holds evidence; choose an empty output directory")
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "receipts.jsonl").write_bytes(_jsonl(receipt_logs))
    tools = _jsonl(tool_logs)
    if tools:
        (bundle / "tool-records.jsonl").write_bytes(tools)
    for notice in notices:
        (bundle / "subjects").mkdir(exist_ok=True)
        (bundle / "subjects" / f"{notice_subject_ref(notice)}.json").write_bytes(canonicalize(notice) + b"\n")
    doc =trust_document(descriptors, not_before=not_before,
                         not_after=not_after or not_before + timedelta(days=1),
                         revocation_issuers=revocation_issuers)
    trust.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return bundle, trust
