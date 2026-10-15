"""Deterministic SYNTHETIC fixture set for the movement-receipt verifier.

Every private key here is derived from a public label, so anybody can recompute
it: these keys are test vectors, never credentials. Ed25519 signatures are
deterministic (RFC 8032), so regenerating produces byte-identical files.
Requires the optional ``signing`` extra. Run:
``python -m agent_movement.receipts make-fixtures tests/fixtures/movement-receipts``
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .core import SCHEMA_VERSION, Approval, EffectGateway, HandoffReceiver, PolicyDenied, SQLiteStore, digest
from .jcs import canonicalize, jcs_digest
from .receipts import (RECEIPT_SCHEMA, SIGNATURE_DOMAIN, TRUST_SCHEMA, Ed25519Signer, b64u, commitment,
                       format_time, validate_body)

BASE = datetime(2026, 10, 15, 9, 0, 0, tzinfo=timezone.utc)
DOMAIN = "spiffe://synthetic.test"
AGENTS = {"agent-a": "agent/a", "agent-b": "agent/b", "agent-c": "agent/c", "agent-d": "agent/d",
          "agent-r": "agent/r", "tool-ledger": "tool/ledger"}
REVOKED_AT = "2026-10-15T08:30:00Z"
# Digest of a hypothetical external signed revocation notice; this profile only references it.
REVOCATION_REF = jcs_digest({"notice": "synthetic-revocation", "key_id": "synthetic-agent-r-2026",
                             "revoked_at": REVOKED_AT})
USE_KEY = object()


def salted(label: str, value: Any) -> dict[str, Any]:
    """Salted commitment document (never publish unsalted digests of task content)."""
    return commitment(value, hexid(f"salt/{label}", 32))


def principal(name: str) -> str:
    return f"{DOMAIN}/{AGENTS[name]}"


def synthetic_seed(name: str) -> bytes:
    """PUBLIC derivation: these are fixture keys, not secrets."""
    return hashlib.sha256(b"agent-movement/SYNTHETIC-PUBLIC-TEST-KEY/v1/" + name.encode()).digest()


def key_id(name: str) -> str:
    return f"synthetic-{name}-2026"


def signer(name: str) -> Ed25519Signer:
    return Ed25519Signer(key_id(name), synthetic_seed(name))


def hexid(label: str, size: int) -> str:
    value = hashlib.sha256(label.encode()).hexdigest()[:size]
    return value if value[0].isalpha() else "f" + value[1:]


def at(seconds: int) -> str:
    return format_time(BASE + timedelta(seconds=seconds))


def party(agent: str | None, who: str | None, execution: str | None) -> dict[str, Any]:
    return {"claimed_agent_id": agent, "claimed_principal": principal(who) if who else None,
            "execution_id": execution}


def trust_document() -> dict[str, Any]:
    keys = []
    for name in sorted(AGENTS):
        keys.append({"key_id": key_id(name), "principal": principal(name),
                     "role": "tool" if name.startswith("tool-") else "agent", "alg": "Ed25519",
                     "public_key": signer(name).public_key, "not_before": "2026-10-01T00:00:00Z",
                     "not_after": "2027-10-01T00:00:00Z",
                     "revoked_at": REVOKED_AT if name == "agent-r" else None,
                     "revocation_ref": REVOCATION_REF if name == "agent-r" else None})
    return {"schema": TRUST_SCHEMA, "keys": keys,
            "note": "SYNTHETIC test anchors. Private keys derive from public labels in "
                    "receipt_fixtures.py; never use them for anything real."}


class Scenario:
    def __init__(self, name: str):
        self.name = name
        self.files: dict[str, list[bytes]] = {"receipts.jsonl": [], "tool-records.jsonl": [], "telemetry.jsonl": []}
        self.subjects: dict[str, Any] = {}
        self.chains: dict[str, tuple[int, str | None]] = {}

    def trace(self, label: str) -> str:
        return hexid(f"trace/{self.name}/{label}", 32)

    def body(self, who: str, receipt_id: str, receipt_type: str, seconds: int, *, task: str | None,
             movement: tuple[str, str | None, str | None] | None = None, source: dict | None = None,
             destination: dict | None = None, execution: dict | None = None, trace: str | None = None,
             subjects: tuple[tuple[str, str, str], ...] = (), effect: dict | None = None,
             outcome: str | None = None, audience: str | None = None, claimed: Any = USE_KEY,
             agent_label: str | None = None, seq: int | None = None, prev: Any = USE_KEY,
             signing_key: str | None = None) -> dict[str, Any]:
        kid = key_id(signing_key or who)
        last_seq, last_digest = self.chains.get(kid, (0, None))
        body = {
            "schema": RECEIPT_SCHEMA, "receipt_id": receipt_id, "receipt_type": receipt_type,
            "issuer": {"key_id": kid, "claimed_principal": principal(who) if claimed is USE_KEY else claimed,
                       "claimed_agent_id": agent_label if agent_label is not None else
                       (who if who.startswith("agent-") else None)},
            "audience": principal(audience) if audience else None,
            "nonce": hexid(f"nonce/{self.name}/{kid}/{receipt_id}", 32),
            "issued_at": at(seconds), "seq": seq or last_seq + 1,
            "prev_receipt_digest": last_digest if prev is USE_KEY else prev,
            "logical_task_id": task,
            "movement": None if movement is None else
            {"movement_id": movement[0], "parent_movement_id": movement[1], "lineage_relation": movement[2]},
            "source": source, "destination": destination, "execution": execution,
            "correlation": {"trace_id": trace, "span_id": hexid(f"span/{self.name}/{receipt_id}", 16) if trace else None},
            "subjects": [{"role": r, "ref": ref, "digest": d} for r, ref, d in subjects],
            "effect": effect, "outcome": outcome, "data_classification": "synthetic",
        }
        validate_body(body)
        self.chains[kid] = (body["seq"], jcs_digest(body))
        return body

    def add(self, wire: dict[str, Any], file: str = "receipts.jsonl") -> dict[str, Any]:
        self.files[file].append(canonicalize(wire))
        return wire

    def span(self, label: str, name: str, seconds: int, trace: str, attributes: dict[str, Any]) -> None:
        self.files["telemetry.jsonl"].append(canonicalize({
            "trace_id": trace, "span_id": hexid(f"telemetry/{self.name}/{label}", 16), "name": name,
            "time": at(seconds), "attributes": attributes}))

    def write(self, root: Path) -> None:
        target = root / self.name
        target.mkdir(parents=True, exist_ok=True)
        for name, lines in self.files.items():
            if lines:
                (target / name).write_bytes(b"".join(line + b"\n" for line in lines))
        if self.subjects:
            (target / "subjects").mkdir(exist_ok=True)
            for ref, value in self.subjects.items():
                (target / "subjects" / f"{ref}.json").write_bytes(canonicalize(value) + b"\n")


def seal(who: str, body: dict[str, Any]) -> dict[str, Any]:
    return signer(who).seal(body)


def seal_unchecked(who: str, body: dict[str, Any]) -> dict[str, Any]:
    """Sign WITHOUT the signer's schema/credential checks (adversarial fixtures only)."""
    key = signer(who)._key
    return {"receipt": body, "body_digest": jcs_digest(body),
            "signature": {"alg": "Ed25519", "key_id": key_id(who),
                          "value": b64u(key.sign(SIGNATURE_DOMAIN + canonicalize(body)))}}


def pr6_handoff(movement_id: str, task_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the PR #6 receiver for real and return (envelope, core receipt)."""
    envelope = {
        "schema_version": SCHEMA_VERSION, "movement_id": movement_id, "logical_task_id": task_id,
        "operation": "delegate", "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
        "task": {"kind": "word_count", "text": "synthetic agent movement test task"},
        "context": {"classification": "synthetic"}, "authority": {"approval_ref": f"approval-{task_id}"},
        "execution": {"idempotency_key": f"op-{movement_id}"}, "observability": {"trace_id": f"trace-{movement_id}"},
    }
    with tempfile.TemporaryDirectory() as root:
        store = SQLiteStore(Path(root) / "fixture.sqlite")
        approval = Approval(f"approval-{task_id}", task_id, "agent-a", "agent-b", "word_count")
        receipt = HandoffReceiver("agent-b", store, [approval]).receive(envelope)
    if jcs_digest(envelope) != "sha256:" + digest(envelope):
        raise AssertionError("PR #6 digest and JCS digest diverged for the fixture envelope")
    return envelope, receipt


def gateway_epochs(stale_commit: bool) -> tuple[int, bool]:
    """Run the PR #6 simulated fenced gateway; return (epoch, committed?)."""
    with tempfile.TemporaryDirectory() as root:
        gateway = EffectGateway(SQLiteStore(Path(root) / "effects.sqlite"))
        old = gateway.claim("fixture-task", "agent-a")
        new = gateway.transfer("fixture-task", "agent-a", old, "agent-b")
        if not stale_commit:
            return new, gateway.commit("fixture-task", "agent-b", new, "effect-1", "synthetic")
        gateway.transfer("fixture-task", "agent-b", new, "agent-d")
        try:
            gateway.commit("fixture-task", "agent-b", new, "effect-1", "synthetic")
        except PolicyDenied:
            return new, False
        return new, True


def _delegation(s: Scenario, mid: str, task: str, *, start: int = 0) -> tuple[dict, dict, str]:
    trace = s.trace(mid)
    dispatch = s.body("agent-a", f"rcpt-{mid}-dispatch", "movement.dispatched", start, task=task,
                      movement=(mid, None, "delegate"), source=party("agent-a", "agent-a", f"exec-a-{mid}"),
                      destination=party("agent-b", "agent-b", None), trace=trace, outcome="dispatched",
                      audience="agent-b")
    accept = s.body("agent-b", f"rcpt-{mid}-accept", "movement.accepted", start + 2, task=task,
                    movement=(mid, None, "delegate"), source=party("agent-a", None, None),
                    destination=party("agent-b", "agent-b", f"exec-b-{mid}"), trace=trace,
                    outcome="accepted", audience="agent-a")
    return dispatch, accept, trace


def scenario_valid() -> Scenario:
    s = Scenario("01-valid-delegation")
    mid, task = "mov-valid-1", "task-valid-1"
    envelope, core_receipt = pr6_handoff(mid, task)
    artifact = salted("art-mov-valid-1", core_receipt["artifact"])
    s.subjects = {"env-mov-valid-1": salted("env-mov-valid-1", envelope), "art-mov-valid-1": artifact}
    # Both sides sign the salted commitment to the same PR #6 envelope (the receiver attests what it received).
    env_subject = ("envelope", "env-mov-valid-1", jcs_digest(s.subjects["env-mov-valid-1"]))
    trace = s.trace(mid)
    dispatch = s.body("agent-a", "rcpt-mov-valid-1-dispatch", "movement.dispatched", 0, task=task,
                      movement=(mid, None, "delegate"), source=party("agent-a", "agent-a", f"exec-a-{mid}"),
                      destination=party("agent-b", "agent-b", None), trace=trace, subjects=(env_subject,),
                      outcome="dispatched", audience="agent-b")
    accept = s.body("agent-b", "rcpt-mov-valid-1-accept", "movement.accepted", 2, task=task,
                    movement=(mid, None, "delegate"), source=party("agent-a", None, None),
                    destination=party("agent-b", "agent-b", f"exec-b-{mid}"), trace=trace,
                    subjects=(env_subject,), outcome="accepted", audience="agent-a")
    epoch, committed = gateway_epochs(stale_commit=False)
    execution = {"execution_id": f"exec-b-{mid}", "parent_execution_id": f"exec-a-{mid}",
                 "agent_instance_id": "inst-b-1", "definition_digest": jcs_digest({"definition": "worker-b"})}
    started = s.body("agent-b", "rcpt-mov-valid-1-started", "execution.started", 3, task=task,
                     movement=(mid, None, "delegate"), destination=party("agent-b", "agent-b", f"exec-b-{mid}"),
                     execution=execution, trace=trace, outcome="started")
    tool = s.body("tool-ledger", "rcpt-mov-valid-1-tool-effect", "tool.effect_recorded", 4, task=task,
                  source=party(None, "agent-b", f"exec-b-{mid}"),
                  effect={"effect_id": "effect-valid-1", "tool_principal": principal("tool-ledger"),
                          "status": "committed" if committed else "rejected", "fencing_epoch": epoch})
    completed = s.body("agent-b", "rcpt-mov-valid-1-completed", "execution.completed", 5, task=task,
                       movement=(mid, None, "delegate"), destination=party("agent-b", "agent-b", f"exec-b-{mid}"),
                       execution=execution, trace=trace, outcome="completed",
                       subjects=(("artifact", "art-mov-valid-1", jcs_digest(artifact)),),
                       effect={"effect_id": "effect-valid-1", "tool_principal": principal("tool-ledger"),
                               "status": "committed", "fencing_epoch": epoch})
    for who, body in (("agent-a", dispatch), ("agent-b", accept), ("agent-b", started), ("agent-b", completed)):
        s.add(seal(who, body))
    s.add(seal("tool-ledger", tool), "tool-records.jsonl")
    s.span("t1", "movement.dispatched", 0, trace, {"agent.claimed_id": "agent-a", "movement_id": mid})
    s.span("t2", "movement.accepted", 2, trace, {"agent.claimed_id": "agent-b", "movement_id": mid})
    s.span("t3", "tool.call", 4, trace, {"agent.claimed_id": "agent-b", "gen_ai.operation.name": "execute_tool"})
    return s


def scenario_tampered() -> Scenario:
    s = Scenario("02-tampered-receipts")
    mid, task = "mov-tamper-1", "task-tamper-1"
    envelope, core_receipt = pr6_handoff(mid, task)
    signed_artifact = salted("art-mov-tamper-1", core_receipt["artifact"])
    altered = salted("art-mov-tamper-1", {**core_receipt["artifact"], "value": core_receipt["artifact"]["value"] + 1})
    s.subjects = {"env-mov-tamper-1": salted("env-mov-tamper-1", envelope),
                  "art-mov-tamper-1": altered}  # artifact altered after signing
    trace = s.trace(mid)
    dispatch = s.body("agent-a", "rcpt-mov-tamper-1-dispatch", "movement.dispatched", 0, task=task,
                      movement=(mid, None, "delegate"), source=party("agent-a", "agent-a", "exec-a-t"),
                      destination=party("agent-b", "agent-b", None), trace=trace, outcome="dispatched",
                      subjects=(("envelope", "env-mov-tamper-1", jcs_digest(s.subjects["env-mov-tamper-1"])),))
    accept = s.body("agent-b", "rcpt-mov-tamper-1-accept", "movement.accepted", 2, task=task,
                    movement=(mid, None, "delegate"), destination=party("agent-b", "agent-b", "exec-b-t"),
                    trace=trace, outcome="accepted")
    execution = {"execution_id": "exec-b-t", "parent_execution_id": None, "agent_instance_id": None,
                 "definition_digest": None}
    started = s.body("agent-b", "rcpt-mov-tamper-1-started", "execution.started", 3, task=task,
                     movement=(mid, None, "delegate"), execution=execution, trace=trace, outcome="started")
    completed = s.body("agent-b", "rcpt-mov-tamper-1-completed", "execution.completed", 5, task=task,
                       movement=(mid, None, "delegate"), execution=execution, trace=trace, outcome="completed",
                       subjects=(("artifact", "art-mov-tamper-1", jcs_digest(signed_artifact)),))
    s.add(seal("agent-a", dispatch))
    forged = seal("agent-b", accept)  # attacker swaps the executor and re-computes the digest
    forged["receipt"] = {**accept, "destination": party("agent-b", "agent-b", "exec-evil-1")}
    forged["body_digest"] = jcs_digest(forged["receipt"])
    s.add(forged)
    edited = seal("agent-b", started)  # attacker edits the outcome, keeps the old digest
    edited["receipt"] = {**started, "outcome": "failed"}
    s.add(edited)
    s.add(seal("agent-b", completed))
    return s


def scenario_replayed() -> Scenario:
    s = Scenario("03-replayed-receipts")
    dispatch, accept, _ = _delegation(s, "mov-replay-1", "task-replay-1")
    first = s.add(seal("agent-a", dispatch))
    accepted = s.add(seal("agent-b", accept))
    s.add(first)  # exact replay in the same log
    s.add(accepted, "tool-records.jsonl")  # replay injected through another evidence source
    return s


def scenario_forged() -> Scenario:
    s = Scenario("04-forged-identity")
    mid, task = "mov-forged-1", "task-forged-1"
    dispatch, accept, trace = _delegation(s, mid, task)
    s.add(seal("agent-a", dispatch))
    attacker = Ed25519Signer("synthetic-attacker-key", hashlib.sha256(b"agent-movement/attacker/v1").digest())
    fake = s.body("agent-b", "rcpt-mov-forged-1-accept-attacker", "movement.accepted", 2, task=task,
                  movement=(mid, None, "delegate"), destination=party("agent-b", "agent-b", "exec-b-fake"),
                  trace=trace, outcome="accepted", signing_key="attacker")
    fake["issuer"]["key_id"] = attacker.key_id
    s.add(attacker.seal(fake))
    impostor = s.body("agent-c", "rcpt-mov-forged-1-accept-impostor", "movement.accepted", 3, task=task,
                      movement=(mid, None, "delegate"), destination=party("agent-b", "agent-b", "exec-c-x"),
                      trace=trace, outcome="accepted", claimed=principal("agent-b"), agent_label="agent-b")
    s.add(seal("agent-c", impostor))
    revoked = s.body("agent-r", "rcpt-mov-forged-2-dispatch", "movement.dispatched", 4, task="task-forged-2",
                     movement=("mov-forged-2", None, "delegate"), source=party("agent-r", "agent-r", None),
                     destination=party("agent-b", "agent-b", None), outcome="dispatched")
    s.add(seal("agent-r", revoked))
    self_confirmed = s.body("agent-a", "rcpt-mov-forged-1-self-tool", "tool.effect_recorded", 5, task=task,
                            source=party("agent-a", "agent-a", None),
                            effect={"effect_id": "effect-forged-1", "tool_principal": principal("tool-ledger"),
                                    "status": "committed", "fencing_epoch": 1})
    s.add(seal("agent-a", self_confirmed), "tool-records.jsonl")
    s.span("t1", "movement.accepted", 2, trace, {"agent.claimed_id": "agent-b", "movement_id": mid,
                                                  "outcome": "accepted"})
    return s


def scenario_missing() -> Scenario:
    s = Scenario("05-missing-claims")
    first = s.body("agent-a", "rcpt-mov-missing-1-dispatch", "movement.dispatched", 0, task="task-missing-1",
                   movement=("mov-missing-1", None, "delegate"), source=party("agent-a", None, None),
                   destination=party(None, None, None), outcome="dispatched")
    second = s.body("agent-a", "rcpt-mov-missing-2-dispatch", "movement.dispatched", 30, task="task-missing-2",
                    movement=("mov-missing-2", None, "delegate"), source=party("agent-a", None, None),
                    destination=party("agent-c", "agent-c", None), outcome="dispatched", seq=4,
                    prev=jcs_digest({"absent": "seq-3"}))
    completed = s.body("agent-b", "rcpt-mov-missing-1-completed", "execution.completed", 20, task="task-missing-1",
                       movement=("mov-missing-1", None, "delegate"),
                       execution={"execution_id": None, "parent_execution_id": None, "agent_instance_id": None,
                                  "definition_digest": None},
                       effect={"effect_id": "effect-missing-1", "tool_principal": None, "status": "committed",
                               "fencing_epoch": None}, outcome="completed")
    for who, body in (("agent-a", first), ("agent-a", second), ("agent-b", completed)):
        s.add(seal(who, body))
    return s


def scenario_conflicting() -> Scenario:
    s = Scenario("06-conflicting-accounts")
    task = "task-conflict-1"
    t1, t2 = s.trace("c1"), s.trace("c2")
    s.add(seal("agent-a", s.body("agent-a", "rcpt-mov-conflict-1-dispatch", "movement.dispatched", 0, task=task,
                                 movement=("mov-conflict-1", None, "delegate"),
                                 source=party("agent-a", "agent-a", None),
                                 destination=party("agent-b", "agent-b", None), trace=t1, outcome="dispatched")))
    s.add(seal("agent-a", s.body("agent-a", "rcpt-mov-conflict-2-dispatch", "movement.dispatched", 1, task=task,
                                 movement=("mov-conflict-2", None, "delegate"),
                                 source=party("agent-a", "agent-a", None),
                                 destination=party("agent-b", "agent-b", None), trace=t2, outcome="dispatched")))
    s.add(seal("agent-b", s.body("agent-b", "rcpt-mov-conflict-1-accept", "movement.accepted", 2, task=task,
                                 movement=("mov-conflict-1", None, "delegate"),
                                 destination=party("agent-b", "agent-b", "exec-b-c1"), trace=t1,
                                 outcome="accepted")))
    s.add(seal("agent-b", s.body("agent-b", "rcpt-mov-conflict-1-reject", "movement.rejected", 3, task=task,
                                 movement=("mov-conflict-1", None, "delegate"),
                                 destination=party("agent-b", "agent-b", None), trace=t1, outcome="rejected")))
    s.add(seal("agent-c", s.body("agent-c", "rcpt-mov-conflict-2-accept", "movement.accepted", 3, task=task,
                                 movement=("mov-conflict-2", None, "delegate"),
                                 destination=party("agent-c", "agent-c", "exec-c-c2"), trace=t2,
                                 outcome="accepted")))
    epoch, committed = gateway_epochs(stale_commit=True)
    effect = {"effect_id": "effect-conflict-1", "tool_principal": principal("tool-ledger"),
              "fencing_epoch": epoch}
    s.add(seal("agent-b", s.body("agent-b", "rcpt-mov-conflict-1-completed", "execution.completed", 6, task=task,
                                 movement=("mov-conflict-1", None, "delegate"),
                                 execution={"execution_id": "exec-b-c1", "parent_execution_id": None,
                                            "agent_instance_id": None, "definition_digest": None},
                                 trace=t1, effect={**effect, "status": "committed"}, outcome="completed")))
    s.add(seal("tool-ledger", s.body("tool-ledger", "rcpt-effect-conflict-1-tool", "tool.effect_recorded", 5,
                                     task=task, source=party(None, "agent-b", "exec-b-c1"),
                                     effect={**effect, "status": "committed" if committed else "rejected"})),
          "tool-records.jsonl")
    return s


def scenario_fork() -> Scenario:
    s = Scenario("07-fork-lineage")
    task, root = "task-fork-1", "mov-root-1"
    trace = s.trace(root)
    worker = jcs_digest({"definition": "shared-worker-v1"})
    dispatch, accept, _ = _delegation(s, root, task)
    s.add(seal("agent-a", dispatch))
    s.add(seal("agent-b", accept))
    s.add(seal("agent-b", s.body("agent-b", "rcpt-mov-root-1-started", "execution.started", 3, task=task,
                                 movement=(root, None, "delegate"),
                                 execution={"execution_id": f"exec-b-{root}", "parent_execution_id": None,
                                            "agent_instance_id": "inst-b-1",
                                            "definition_digest": jcs_digest({"definition": "orchestrator-v1"})},
                                 trace=trace, outcome="started")))
    for index, (child, who) in enumerate((("mov-fork-1", "agent-c"), ("mov-fork-2", "agent-d")), 1):
        s.add(seal("agent-b", s.body("agent-b", f"rcpt-{child}-dispatch", "movement.dispatched", 4 + index,
                                     task=task, movement=(child, root, "fork"),
                                     source=party("agent-b", "agent-b", f"exec-b-{root}"),
                                     destination=party(who, who, None), trace=trace, outcome="dispatched")))
        execution = {"execution_id": f"exec-{who}-{child}", "parent_execution_id": f"exec-b-{root}",
                     "agent_instance_id": f"inst-{who}-1", "definition_digest": worker}
        s.add(seal(who, s.body(who, f"rcpt-{child}-accept", "movement.accepted", 7 + index, task=task,
                               movement=(child, root, "fork"),
                               destination=party(who, who, execution["execution_id"]), trace=trace,
                               outcome="accepted")))
        s.add(seal(who, s.body(who, f"rcpt-{child}-started", "execution.started", 9 + index, task=task,
                               movement=(child, root, "fork"), execution=execution, trace=trace,
                               outcome="started")))
    return s


def scenario_privacy() -> Scenario:
    s = Scenario("08-privacy-canaries")
    dispatch, accept, trace = _delegation(s, "mov-privacy-1", "task-privacy-1")
    s.add(seal("agent-a", dispatch))
    s.add(seal("agent-b", accept))
    jwt_shaped = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzeW50aGV0aWMiOiJjYW5hcnkifQ.c3ludGhldGlj"
    leaky = s.body("agent-b", "rcpt-mov-privacy-1-leaky", "execution.started", 3, task="task-privacy-1",
                   movement=("mov-privacy-1", None, "delegate"),
                   execution={"execution_id": "exec-b-p", "parent_execution_id": None,
                              "agent_instance_id": None, "definition_digest": None}, trace=trace)
    leaky["execution"]["agent_instance_id"] = jwt_shaped  # token-shaped value smuggled into an ID field
    s.add(seal_unchecked("agent-b", leaky))
    chatty = {**s.body("agent-b", "rcpt-mov-privacy-1-chatty", "execution.completed", 4, task="task-privacy-1",
                       movement=("mov-privacy-1", None, "delegate"),
                       execution={"execution_id": "exec-b-p", "parent_execution_id": None,
                                  "agent_instance_id": None, "definition_digest": None}, trace=trace),
              "prompt": "synthetic canary prompt text: must never be exported"}
    s.add(seal_unchecked("agent-b", chatty))
    s.span("t1", "tool.call", 3, trace, {
        "agent.claimed_id": "agent-b", "movement_id": "Bearer synthetic-canary-not-a-credential",
        "authorization": "Bearer synthetic-canary-not-a-credential",
        "gen_ai.prompt": "synthetic canary prompt: do not export",
        "http.request.header.cookie": "session=synthetic-canary-cookie",
        "db.statement": "api_key=synthetic-canary-value"})
    s.span("t2", "Bearer synthetic-canary-span-name", 4, trace, {"agent.claimed_id": "agent-b"})
    return s


def scenario_skew() -> Scenario:
    s = Scenario("09-clock-skew")
    mid, task = "mov-skew-1", "task-skew-1"
    trace = s.trace(mid)
    s.add(seal("agent-a", s.body("agent-a", "rcpt-mov-skew-1-dispatch", "movement.dispatched", 10, task=task,
                                 movement=(mid, None, "delegate"), source=party("agent-a", "agent-a", None),
                                 destination=party("agent-b", "agent-b", None), trace=trace,
                                 outcome="dispatched")))
    s.add(seal("agent-b", s.body("agent-b", "rcpt-mov-skew-1-accept", "movement.accepted", 4, task=task,
                                 movement=(mid, None, "delegate"),
                                 destination=party("agent-b", "agent-b", "exec-b-s"), trace=trace,
                                 outcome="accepted")))
    s.add(seal("agent-b", s.body("agent-b", "rcpt-mov-skew-1-started", "execution.started", 5, task=task,
                                 movement=(mid, None, "delegate"),
                                 execution={"execution_id": "exec-b-s", "parent_execution_id": None,
                                            "agent_instance_id": None, "definition_digest": None},
                                 trace=trace, outcome="started")))
    return s


SCENARIOS = (scenario_valid, scenario_tampered, scenario_replayed, scenario_forged, scenario_missing,
             scenario_conflicting, scenario_fork, scenario_privacy, scenario_skew)

# Hand-written expectations (the specification the verifier is tested against).
EXPECTED: dict[str, Any] = {
    "01-valid-delegation": {
        "exit_code": 0, "receipt_verdicts": {"VALID": 5},
        "timeline_status": {"VERIFIABLE": 5, "UNVERIFIABLE": 3, "CONFLICTING": 0},
        "claims": {"mov-valid-1": {"source_principal": "VERIFIED", "destination_principal": "VERIFIED",
                                   "outcome": "SIGNED_CLAIM", "trace_ids": "CORRELATION_ONLY", "grade": "E3"}},
        "effects": {"effect-valid-1": "CONFIRMED_BY_TOOL"},
        "subjects": {"env-mov-valid-1": "DIGEST_MATCH", "art-mov-valid-1": "DIGEST_MATCH"}},
    "02-tampered-receipts": {
        "exit_code": 1, "receipt_verdicts": {"VALID": 2, "TAMPERED": 2},
        "timeline_status": {"VERIFIABLE": 1, "UNVERIFIABLE": 0, "CONFLICTING": 1},
        "claims": {"mov-tamper-1": {"destination_principal": "SIGNED_CLAIM", "outcome": "UNKNOWN", "grade": "E2"}},
        "subjects": {"env-mov-tamper-1": "DIGEST_MATCH", "art-mov-tamper-1": "DIGEST_MISMATCH"}},
    "03-replayed-receipts": {
        "exit_code": 1, "receipt_verdicts": {"VALID": 2, "REPLAYED": 2},
        "timeline_status": {"VERIFIABLE": 2, "UNVERIFIABLE": 0, "CONFLICTING": 0},
        "claims": {"mov-replay-1": {"destination_principal": "VERIFIED", "grade": "E3"}}},
    "04-forged-identity": {
        "exit_code": 1, "receipt_verdicts": {"VALID": 1, "UNTRUSTED": 4},
        "timeline_status": {"VERIFIABLE": 1, "UNVERIFIABLE": 5, "CONFLICTING": 0},
        "claims": {"mov-forged-1": {"source_principal": "VERIFIED", "destination_principal": "SIGNED_CLAIM",
                                    "outcome": "UNKNOWN", "grade": "E2"},
                   "mov-forged-2": {"source_principal": "UNVERIFIED_CLAIM", "destination_principal": "UNKNOWN",
                                    "grade": "E1"}}},
    "05-missing-claims": {
        "exit_code": 0, "receipt_verdicts": {"VALID": 3},
        "timeline_status": {"VERIFIABLE": 3, "UNVERIFIABLE": 1, "CONFLICTING": 0},
        "claims": {"mov-missing-1": {"source_principal": "VERIFIED", "destination_principal": "UNKNOWN",
                                     "destination_execution_id": "UNKNOWN", "outcome": "UNKNOWN",
                                     "destination_agent_label": "UNKNOWN"},
                   "mov-missing-2": {"destination_principal": "SIGNED_CLAIM", "outcome": "UNKNOWN"}},
        "effects": {"effect-missing-1": "UNKNOWN"}},
    "06-conflicting-accounts": {
        "exit_code": 1, "receipt_verdicts": {"VALID": 7},
        "timeline_status": {"VERIFIABLE": 1, "UNVERIFIABLE": 0, "CONFLICTING": 6},
        "claims": {"mov-conflict-1": {"source_principal": "VERIFIED", "destination_principal": "VERIFIED",
                                      "outcome": "CONFLICTING"},
                   "mov-conflict-2": {"source_principal": "VERIFIED", "destination_principal": "CONFLICTING",
                                      "destination_agent_label": "CONFLICTING"}},
        "effects": {"effect-conflict-1": "CONFLICTING"}},
    "07-fork-lineage": {
        "exit_code": 0, "receipt_verdicts": {"VALID": 9},
        "timeline_status": {"VERIFIABLE": 9, "UNVERIFIABLE": 0, "CONFLICTING": 0},
        "claims": {"mov-fork-1": {"source_principal": "VERIFIED", "destination_principal": "VERIFIED",
                                  "grade": "E3"},
                   "mov-fork-2": {"source_principal": "VERIFIED", "destination_principal": "VERIFIED",
                                  "grade": "E3"}},
        "lineage": 2},
    "08-privacy-canaries": {
        "exit_code": 1, "receipt_verdicts": {"VALID": 2, "MALFORMED": 2},
        "timeline_status": {"VERIFIABLE": 2, "UNVERIFIABLE": 2, "CONFLICTING": 0}},
    "09-clock-skew": {
        "exit_code": 0, "receipt_verdicts": {"VALID": 3},
        "timeline_status": {"VERIFIABLE": 3, "UNVERIFIABLE": 0, "CONFLICTING": 0},
        "timeline_order": ["rcpt-mov-skew-1-dispatch", "rcpt-mov-skew-1-accept", "rcpt-mov-skew-1-started"]},
}


def write_fixtures(root: str | Path) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "trust.json").write_text(json.dumps(trust_document(), indent=2, sort_keys=True) + "\n")
    (root / "expected.json").write_text(json.dumps(EXPECTED, indent=2, sort_keys=True) + "\n")
    for build in SCENARIOS:
        build().write(root)
