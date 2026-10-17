"""Issue #119: no guarded task can enter peer preflight or retroactive peer state.

Only a single authority SQLite file and synthetic data; direct signed peer
metadata is trusted from issuer keys, but no live remote tools are involved.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

from agent_movement.core import EffectGateway, PolicyDenied
from agent_movement.peer import DELIVERY_PATH, PREFLIGHT_PATH, AuthorizedEffectGateway, HandoffAborted
from agent_movement.trust import verify_grant
from test_continuity_runtime import DEST, TEXT, Rig
from test_guarded_authority import intent, service


@pytest.fixture
def rig(tmp_path: Path):
    r = Rig(tmp_path)
    r.install()
    EffectGateway(r.store).claim("task-1", "agent-a")
    return r


def enroll(rig: Rig):
    guard = service(rig)
    guard.enroll(intent(rig), rig.grant)
    return guard


def build_preflight(rig: Rig):
    return rig.client.build_preflight(
        url=DEST, destination_id="agent-b", movement_id="movement-1",
        task_id="task-1", kind="word_count", text=TEXT, grant=rig.grant,
        idempotency_key="retry-1", trace_id="trace-1",
    )


def prior(rig: Rig):
    with sqlite3.connect(rig.store.path) as db:
        admissions = db.execute("SELECT count(*) FROM peer_admissions").fetchone()[0]
        effects = db.execute("SELECT count(*) FROM authorized_effects").fetchone()[0]
        accepted = db.execute("SELECT count(*) FROM audit_events "
                              "WHERE task_id='task-1' AND event_type='handoff.accepted'").fetchone()[0]
    return admissions, effects, accepted


def test_unmanaged_signed_peer_delegate_still_commits_one_synthetic_effect(rig):
    receipt = rig.handoff()
    assert receipt["effect"] == "committed"
    assert prior(rig) == (1, 1, 1)


def test_guarded_enrollment_denies_before_authenticated_sender_sends_task_text(rig):
    gate = enroll(rig)
    with pytest.raises(HandoffAborted) as exc:
        rig.handoff()
    assert exc.value.stage == "preflight"
    assert exc.value.payload_sent is False
    assert rig.wire.paths() == ["/v0/agent-card", PREFLIGHT_PATH]
    assert "/v0/deliveries" not in rig.wire.paths()
    assert TEXT.encode() not in rig.wire.transmitted()
    assert prior(rig) == (0, 0, 0)
    assert gate.inspect("task-1")["phase"] == "prepared"


def test_signed_raw_preflight_bypassing_official_client_denies(rig):
    enroll(rig)
    body, _ = build_preflight(rig)
    assert TEXT.encode() not in body
    status, response = rig.receiver.handle("POST", PREFLIGHT_PATH, body)
    assert status == 403 and response == {"error": "forbidden"}
    assert prior(rig) == (0, 0, 0)
    assert rig.receiver.ledger.traces()[-1]["outcome"] == "denied"


def test_admitted_peer_preflight_must_be_reconciled_before_guard_enrollment(rig):
    body, _ = build_preflight(rig)
    status, _ = rig.receiver.handle("POST", PREFLIGHT_PATH, body)
    assert status == 200
    assert prior(rig) == (1, 0, 0)
    with pytest.raises(PolicyDenied, match="prior peer admission"):
        enroll(rig)
    assert prior(rig) == (1, 0, 0)


def test_previous_peer_side_simulated_effect_prevents_budget_reset(rig):
    grant = verify_grant(rig.grant, rig.trust)
    bare = AuthorizedEffectGateway(rig.receiver.ledger, rig.clock)
    assert bare.commit(grant, "agent-b", "task-1", "peer-effect-1", "fake", movement_id="movement-1")
    assert prior(rig) == (0, 1, 0)
    with pytest.raises(PolicyDenied, match="prior peer effects"):
        enroll(rig)
    assert prior(rig) == (0, 1, 0)


def test_unrelated_peer_admissions_do_not_block_guarded_task(rig):
    with sqlite3.connect(rig.store.path) as db:
        db.execute("INSERT INTO peer_admissions VALUES(?,?,?,?)",
                   ("adm-" + "a" * 32, "other-movement",
                    json.dumps({"logical_task_id": "task-other"}), 9999999999))
        db.commit()
    gate = enroll(rig)
    assert gate.inspect("task-1")["phase"] == "prepared"


def test_preflight_target_gate_mutation_exposes_signed_bypass(rig, monkeypatch):
    gate = enroll(rig)
    body, _ = build_preflight(rig)
    assert rig.receiver.handle("POST", PREFLIGHT_PATH, body)[0] == 403
    assert prior(rig)[0] == 0
    # RED mutation: remove the actual SQLite preflight gate only in this
    # test. It now issues a signed admission for an already guarded task.
    monkeypatch.setattr(EffectGateway, "_deny_guarded", staticmethod(lambda _db, _task: None))
    status, admission = rig.receiver.handle("POST", PREFLIGHT_PATH, build_preflight(rig)[0])
    assert status == 200 and admission["payload"]["type"] == "admission"
    assert prior(rig)[0] == 1
    assert gate.inspect("task-1")["phase"] == "prepared"


def test_direct_delivery_of_old_admission_refused_before_receiver_task_processing(rig, monkeypatch):
    gate = enroll(rig)
    # Test-only controlled fault: deliberately allow an unauthorized
    # admission to exist first, as if a stale adapter had been left enabled.
    monkeypatch.setattr(EffectGateway, "_deny_guarded", staticmethod(lambda _db, _task: None))
    preflight, detail = build_preflight(rig)
    status, admission = rig.receiver.handle("POST", PREFLIGHT_PATH, preflight)
    assert status == 200
    # Restore the real independent sink gate before delivering text. Task
    # bytes cross this direct call's wire; this is POST-DISCLOSURE refusal.
    monkeypatch.undo()
    receipt = admission["payload"]
    signed_body = rig.client.build_delivery(receipt["admission_id"], detail["task"], detail["salt"])
    assert TEXT.encode() in signed_body
    status, answer = rig.receiver.handle("POST", DELIVERY_PATH, signed_body)
    assert status == 403 and answer == {"error": "forbidden"}
    assert prior(rig) == (1, 0, 0)
    assert gate.inspect("task-1")["phase"] == "prepared"


def test_parallel_preflight_and_enrollment_have_no_double_acceptance(rig):
    start = threading.Barrier(2)
    out: list[str] = []

    def admission():
        body, _ = build_preflight(rig)
        start.wait(4)
        status, _ = rig.receiver.handle("POST", PREFLIGHT_PATH, body)
        out.append(f"peer:{status}")

    def protected():
        start.wait(4)
        try:
            enroll(rig)
        except PolicyDenied:
            out.append("guard:denied")
        else:
            out.append("guard:enrolled")

    workers = [threading.Thread(target=admission), threading.Thread(target=protected)]
    for t in workers:
        t.start()
    for t in workers:
        t.join(8)
        assert not t.is_alive()
    assert sorted(out) in (
        ["guard:denied", "peer:200"], ["guard:enrolled", "peer:403"],
    )
    with sqlite3.connect(rig.store.path) as db:
        guard_rows = db.execute("SELECT count(*) FROM guarded_tasks").fetchone()[0]
    assert guard_rows + prior(rig)[0] == 1
