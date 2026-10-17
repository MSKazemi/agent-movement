"""Issue #102: independently provisioned local tool-sink checks and adversarial cases.

All effects are SQLite records, not external operations. Runtime processes are
separate, but the test runner/worker share a Unix user and filesystem: this
does not demonstrate production sandboxing or cross-machine atomicity.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from agent_movement.core import digest
from agent_movement.tool_effect_service import ToolEffectService, load_service
from agent_movement.trust import (
    HmacKey,
    TrustStore,
    issue_grant,
    issue_revocation,
    seal,
    unseal,
)


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.path = tmp_path
        self.db = tmp_path / "effect-sink.sqlite"
        self.config = tmp_path / "trusted-config.json"
        self.issuer = HmacKey.generate("issuer")
        self.operator = HmacKey.generate("operator")
        self.origin = HmacKey.generate("worker-a")
        self.worker = HmacKey.generate("worker-b")
        self.receipt = HmacKey.generate("receipt")
        self.clock = int(time.time())
        self.grant = self.mint()
        cfg = {
            "service_id": "tool-service", "budget": 2,
            "grant_trust": TrustStore.build([], [self.issuer]).export(),
            "worker_verifiers": {
                "agent-a": self.origin.verifier().export(private=False),
                "agent-b": self.worker.verifier().export(private=False),
            },
            "operator_verifier": self.operator.verifier().export(private=False),
            "receipt_signer": self.receipt.export(),
        }
        self.config.write_text(json.dumps(cfg, sort_keys=True), encoding="utf-8")
        self.config.chmod(0o600)

    def mint(self, **changes: object) -> dict[str, object]:
        config = {
            "grant_id": "grant-1", "subject": "synthetic-user",
            "actor": "agent-b", "audience": "tool-service", "task_id": "task-1",
            "capabilities": ["word_count"], "classification": "synthetic",
            "not_before": self.clock - 30, "expires_at": self.clock + 180,
        }
        config.update(changes)
        return issue_grant(self.issuer, **config)

    def event(self, action: str, seq: int, **extra: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "type": "tool-operator-event", "action": action, "seq": seq,
            "task_id": "task-1", "movement_id": "movement-1",
        }
        if action == "enroll":
            payload.update(
                origin_id="agent-a", destination_id="agent-b", kind="word_count",
                classification="synthetic", owner_epoch=1, policy_epoch=4, grant=self.grant,
            )
        elif action == "transfer":
            payload.update(expected_owner="agent-a", expected_epoch=1)
        payload.update(extra)
        return seal("tool-operator-event", payload, self.operator)

    def effect(self, *, grant: object = None, actor: str = "agent-b",
               signer: HmacKey | None = None, **changes: object) -> dict[str, object]:
        grant = self.grant if grant is None else grant
        payload: dict[str, object] = {
            "type": "tool-effect-request", "movement_id": "movement-1",
            "task_id": "task-1", "actor_id": actor, "service_id": "tool-service",
            "kind": "word_count", "classification": "synthetic", "policy_epoch": 4,
            "owner_epoch": 2, "effect_id": "effect-1",
            "effect_tag": hashlib.sha256(b"synthetic-only-result").hexdigest(),
            "cost": 1, "grant_digest": digest(grant),
        }
        payload.update(changes)
        return {"version": 1, "operation": "synthetic_effect",
                "signed": seal("tool-effect-request", payload, signer or self.worker),
                "grant": grant}

    def authority(self, clock=None) -> ToolEffectService:
        if clock is None:
            return load_service(self.config, self.db)
        return ToolEffectService(
            self.db, service_id="tool-service",
            grant_trust=TrustStore.build([], [self.issuer]),
            worker_verifiers={"agent-a": self.origin, "agent-b": self.worker},
            operator_verifier=self.operator, receipt_signer=self.receipt,
            clock=clock,
        )

    def count(self) -> int:
        with sqlite3.connect(self.db) as db:
            return db.execute("SELECT count(*) FROM tool_effects").fetchone()[0]

    def audit(self) -> list[tuple[str, str]]:
        with sqlite3.connect(self.db) as db:
            return db.execute("SELECT category,outcome FROM tool_events ORDER BY seq").fetchall()


class Server:
    def __init__(self, rig: Rig) -> None:
        env = dict(os.environ)
        src = str(Path(__file__).resolve().parents[1] / "src")
        env["PYTHONPATH"] = os.pathsep.join(p for p in (src, env.get("PYTHONPATH")) if p)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "agent_movement.tool_effect_service",
             "--config", str(rig.config), "--db", str(rig.db)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            assert self.process.stderr is not None
            raise RuntimeError(self.process.stderr.read())
        ready = json.loads(line)
        assert ready["service"] == "tool-service"
        self.port = ready["port"]
        self.url = f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        self.process.stdout.close()
        self.process.stderr.close()

    def post(self, path: str, obj: object) -> tuple[int, dict[str, object]]:
        raw = json.dumps(obj, sort_keys=True).encode("utf-8")
        req = urllib.request.Request(
            self.url + path, data=raw, headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)


def status(rig: Rig, reply: tuple[int, dict[str, object]], kind: str) -> str:
    code, data = reply
    assert code in (200, 202, 403, 409)
    assert set(data) == {"receipt"}
    payload = unseal("tool-effect-receipt", data["receipt"], rig.receipt.verifier())
    assert payload["type"] == "tool-effect-receipt"
    assert payload["service_id"] == "tool-service"
    assert payload["kind"] == kind
    return payload["status"]


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


@pytest.fixture
def server(rig: Rig):
    svc = Server(rig)
    try:
        yield svc
    finally:
        svc.close()


def prepare(rig: Rig, server: Server) -> None:
    assert status(rig, server.post("/v0/operator", rig.event("enroll", 1)), "operator") == "applied"
    assert status(rig, server.post("/v0/operator", rig.event("transfer", 2)), "operator") == "applied"


def test_two_process_service_grants_one_effect_and_replays_exactly_once(rig: Rig, server: Server):
    prepare(rig, server)
    request = rig.effect()
    first = server.post("/v0/effects", request)
    second = server.post("/v0/effects", request)
    assert status(rig, first, "effect") == "committed"
    assert status(rig, second, "effect") == "replayed"
    assert rig.count() == 1
    assert rig.audit()[-2:] == [("effect", "committed"), ("effect", "replayed")]
    with pytest.raises(ValueError):
        bad = json.loads(json.dumps(first[1]))
        bad["receipt"]["payload"]["status"] = "replayed"
        unseal("tool-effect-receipt", bad["receipt"], rig.receipt.verifier())


def test_unsigned_or_forged_direct_calls_never_commit(rig: Rig, server: Server):
    prepare(rig, server)
    fake = rig.effect(signer=HmacKey.generate("worker-b"))
    denied = [
        fake, {"version": 1, "operation": "synthetic_effect", "grant": rig.grant,
               "signed": {"kid": "worker-b", "payload": {"approved": True}}},
        {**rig.effect(), "approved": True},
        {**rig.effect(), "operation": "replicate"},
        {**rig.effect(), "version": 2},
        {**rig.effect(), "raw_task_text": "synthetic-CANARY"},
    ]
    for item in denied:
        assert status(rig, server.post("/v0/effects", item), "effect") == "denied"
    assert rig.count() == 0
    assert b"synthetic-CANARY" not in rig.db.read_bytes()


@pytest.mark.parametrize("changes", [
    {"owner_epoch": 1}, {"owner_epoch": 3}, {"policy_epoch": 5},
    {"movement_id": "other-movement"}, {"task_id": "other-task"},
    {"service_id": "other-service"}, {"kind": "sha256"},
    {"classification": "public"}, {"cost": 2}, {"effect_tag": "wrong"},
])
def test_stale_scope_and_contract_violation_denied(rig: Rig, server: Server, changes):
    prepare(rig, server)
    assert status(rig, server.post("/v0/effects", rig.effect(**changes)), "effect") == "denied"
    assert rig.count() == 0


@pytest.mark.parametrize("grant_changes", [
    {"actor": "agent-a"}, {"audience": "other-service"},
    {"task_id": "other-task"}, {"capabilities": ["sha256"]},
    {"classification": "public"}, {"expires_at": 1},
    {"not_before": 2 ** 32},
])
def test_incorrect_or_expired_issuer_grant_cannot_enroll(rig: Rig, server: Server, grant_changes):
    rig.grant = rig.mint(**grant_changes)
    assert status(rig, server.post("/v0/operator", rig.event("enroll", 1)), "operator") == "denied"
    assert rig.count() == 0


def test_different_grant_or_worker_actor_denied_even_if_signed(rig: Rig, server: Server):
    prepare(rig, server)
    other = rig.mint(grant_id="grant-2")
    assert status(rig, server.post("/v0/effects", rig.effect(grant=other)), "effect") == "denied"
    assert status(rig, server.post("/v0/effects",
                                  rig.effect(actor="agent-a", signer=rig.origin, owner_epoch=1)),
                  "effect") == "denied"
    assert rig.count() == 0


def test_mutated_or_replayed_operator_control_refused(rig: Rig, server: Server):
    event = rig.event("enroll", 1)
    assert status(rig, server.post("/v0/operator", event), "operator") == "applied"
    assert status(rig, server.post("/v0/operator", event), "operator") == "conflict"
    tampered = json.loads(json.dumps(rig.event("transfer", 2)))
    tampered["payload"]["expected_epoch"] = 123
    assert status(rig, server.post("/v0/operator", tampered), "operator") == "denied"
    forged = rig.event("transfer", 2)
    forged["sig"] = "evil"
    assert status(rig, server.post("/v0/operator", forged), "operator") == "denied"
    assert status(rig, server.post("/v0/operator", rig.event("transfer", 2)), "operator") == "applied"
    assert status(rig, server.post("/v0/operator", rig.event("transfer", 2)), "operator") == "conflict"


def test_issuer_signed_revocation_blocks_existing_and_new_effects(rig: Rig, server: Server):
    prepare(rig, server)
    assert status(rig, server.post("/v0/effects", rig.effect()), "effect") == "committed"
    revoked = issue_revocation(rig.issuer, "grant-1", rig.clock)
    assert status(rig, server.post("/v0/operator",
                                  rig.event("revoke", 3, notice=revoked)), "operator") == "applied"
    for request in (rig.effect(), rig.effect(effect_id="effect-2")):
        assert status(rig, server.post("/v0/effects", request), "effect") == "denied"
    assert rig.count() == 1


def test_revocation_must_be_issuer_signed_and_correct_grant(rig: Rig, server: Server):
    prepare(rig, server)
    bad = issue_revocation(HmacKey.generate("issuer"), "grant-1", rig.clock)
    assert status(rig, server.post("/v0/operator",
                                  rig.event("revoke", 3, notice=bad)), "operator") == "denied"
    wrong = issue_revocation(rig.issuer, "some-other-grant", rig.clock)
    assert status(rig, server.post("/v0/operator",
                                  rig.event("revoke", 3, notice=wrong)), "operator") == "denied"
    assert status(rig, server.post("/v0/effects", rig.effect()), "effect") == "committed"


def test_policy_rollover_and_uncertain_holds_fail_closed(rig: Rig, server: Server):
    prepare(rig, server)
    event = rig.event("policy_rollover", 3, new_policy_epoch=5)
    assert status(rig, server.post("/v0/operator", event), "operator") == "applied"
    assert status(rig, server.post("/v0/effects", rig.effect()), "effect") == "denied"
    assert status(rig, server.post("/v0/effects",
                                  rig.effect(policy_epoch=5)), "effect") == "unknown"
    assert rig.count() == 0


def test_operator_unknown_halts_and_does_not_claim_external_reversal(rig: Rig, server: Server):
    prepare(rig, server)
    assert status(rig, server.post("/v0/operator", rig.event("mark_unknown", 3)),
                  "operator") == "applied"
    assert status(rig, server.post("/v0/effects", rig.effect()), "effect") == "unknown"
    assert rig.count() == 0


def test_concurrent_retries_and_budget_share_one_atomic_ledger(rig: Rig, server: Server):
    prepare(rig, server)
    request = rig.effect()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: status(rig, server.post("/v0/effects", request), "effect"),
                                 range(8)))
    assert outcomes.count("committed") == 1
    assert outcomes.count("replayed") == 7
    assert rig.count() == 1
    changed_tag = rig.effect(effect_tag=hashlib.sha256(b"changed").hexdigest())
    assert status(rig, server.post("/v0/effects", changed_tag), "effect") == "conflict"
    assert status(rig, server.post("/v0/effects", rig.effect(effect_id="effect-2")),
                  "effect") == "committed"
    assert status(rig, server.post("/v0/effects", rig.effect(effect_id="effect-3")),
                  "effect") == "denied"
    assert rig.count() == 2


def test_client_loses_response_then_queries_authoritative_effect_state(rig: Rig, server: Server):
    prepare(rig, server)
    raw = json.dumps(rig.effect(), sort_keys=True).encode("utf-8")
    with socket.create_connection(("127.0.0.1", server.port), timeout=3) as sock:
        request = (f"POST /v0/effects HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                   f"Content-Type: application/json\r\nContent-Length: {len(raw)}\r\n"
                   "Connection: close\r\n\r\n").encode() + raw
        sock.sendall(request)
        # Client did NOT receive a receipt; outcome is UNKNOWN TO THE CLIENT.
        sock.shutdown(socket.SHUT_RDWR)
    deadline = time.monotonic() + 3
    while rig.count() == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert rig.count() == 1
    assert status(rig, server.post("/v0/effects", rig.effect()), "effect") == "replayed"


def test_service_crash_restart_does_not_duplicate_an_effect(rig: Rig):
    first = Server(rig)
    try:
        prepare(rig, first)
        assert status(rig, first.post("/v0/effects", rig.effect()), "effect") == "committed"
    finally:
        first.close()
    second = Server(rig)
    try:
        assert status(rig, second.post("/v0/effects", rig.effect()), "effect") == "replayed"
        assert rig.count() == 1
    finally:
        second.close()


def test_trusted_sink_clock_expires_grant_between_enrollment_and_commit(rig: Rig):
    now = [rig.clock]
    service = rig.authority(clock=lambda: now[0])
    assert status(rig, service.operator_event(rig.event("enroll", 1)), "operator") == "applied"
    assert status(rig, service.operator_event(rig.event("transfer", 2)), "operator") == "applied"
    now[0] += 1000
    assert status(rig, service.effect(rig.effect()), "effect") == "denied"
    assert rig.count() == 0


def test_red_green_removing_sink_epoch_check_exposes_stale_worker(rig: Rig, monkeypatch):
    service = rig.authority()
    service.operator_event(rig.event("enroll", 1))
    service.operator_event(rig.event("transfer", 2))
    stale = rig.effect(owner_epoch=1)
    assert status(rig, service.effect(stale), "effect") == "denied"
    assert rig.count() == 0
    # Deliberately weakened verifier: the otherwise signed and in-scope stale
    # request now commits. This is a MUTATION CONTROL, NOT a shipping profile.
    monkeypatch.setattr(service, "_owner_matches", lambda _row, _req: True)
    assert status(rig, service.effect(stale), "effect") == "committed"
    assert rig.count() == 1


def test_direct_untrusted_separate_process_cannot_use_missing_signature(rig: Rig, server: Server):
    prepare(rig, server)
    code = (
        "import json,sys,urllib.request,urllib.error;"
        "d=json.loads(sys.stdin.read());"
        "req=urllib.request.Request(sys.argv[1],data=json.dumps(d).encode(),"
        "headers={'Content-Type':'application/json'});"
        "exec('try:\\n r=urllib.request.urlopen(req,timeout=3)\\n"
        "except urllib.error.HTTPError as e: r=e\\n');"
        "print(r.status)"
    )
    malformed = {"version": 1, "operation": "synthetic_effect",
                 "signed": {"approved": True}, "grant": rig.grant}
    child = subprocess.run(
        [sys.executable, "-c", code, server.url + "/v0/effects"],
        input=json.dumps(malformed), text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=5, check=True,
    )
    assert child.stdout.strip() == "403"
    assert rig.count() == 0
