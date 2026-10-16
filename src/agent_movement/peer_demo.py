"""Two-process authenticated handoff demo with denials captured BEFORE task text is sent.

The parent process plays the synthetic test CA, the synthetic user authority, the honest
origin ``agent-a`` and several attackers; ``agent-b`` runs as a separate OS process on
loopback. All keys are generated per run and deleted with the temp directory.

``--delivery hpke`` (the default with ``--alg Ed25519``) gives agent-b a CA-signed X25519
key and seals every delivery to it, so the task canary must not appear in *any* captured
bytes, not even for the successful handoff. ``--delivery plaintext`` (the default with the
stdlib-only ``HS256``) has **no confidentiality**: the successful delivery carries the text
in clear, and the output says so.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .core import canonical
from .peer import (DELIVERY_PATH, HandoffAborted, HttpTransport, PeerClient, RecordingTransport,
                   TRACE_FIELDS)
from .peer_http import make_peer_server
from .trust import (ED25519, HS256, HpkeKey, TrustStore, ed25519_available, generate_key,
                    hpke_available, issue_card, issue_grant, issue_revocation)

TASK_CANARY = "CANARY-TASK-demo-5a7b"
PROVIDER_CANARY = "CANARY-PROVIDER-TOKEN-demo-not-real"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Static:
    def __init__(self, card: dict) -> None:
        self.card = card

    def handle(self, method: str, path: str, body: bytes) -> tuple[int, dict]:
        return (200, self.card) if method == "GET" else (403, {"error": "forbidden"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Authenticated pre-disclosure handoff demo (NOT A2A)")
    parser.add_argument("--alg", choices=[HS256, ED25519], default=HS256)
    parser.add_argument("--delivery", choices=["auto", "plaintext", "hpke"], default="auto",
                        help="auto: hpke with Ed25519, plaintext (no confidentiality) with HS256")
    options = parser.parse_args()
    alg = options.alg
    delivery = options.delivery if options.delivery != "auto" else ("hpke" if alg == ED25519 else "plaintext")
    if alg == ED25519 and not ed25519_available():
        raise SystemExit("Ed25519 needs the optional extra: pip install -e '.[ed25519]'")
    if delivery == "hpke" and not hpke_available():
        raise SystemExit("HPKE delivery needs the optional extra: pip install -e '.[hpke]'")
    enc_b = HpkeKey.generate("agent-b-enc") if delivery == "hpke" else None
    now = int(time.time())
    ca, users = generate_key(alg, "test-ca"), generate_key(alg, "user-authority")
    keys = {n: generate_key(alg, f"{n}-key") for n in ("agent-a", "agent-b", "agent-c")}
    rogue_ca, rogue_a = generate_key(alg, "test-ca"), generate_key(alg, "agent-a-key")
    trust = TrustStore.build([ca], [users], keys.values() if alg == HS256 else ())
    window = {"not_before": now - 60, "expires_at": now + 900}
    b_url = f"http://127.0.0.1:{_free_port()}"
    cards = {"agent-a": issue_card(ca, agent_id="agent-a", endpoint_url="local://agent-a",
                                   capabilities=["word_count"], agent_key=keys["agent-a"], **window),
             "agent-b": issue_card(ca, agent_id="agent-b", endpoint_url=b_url, capabilities=["word_count"],
                                   agent_key=keys["agent-b"], enc_key=enc_b, **window),
             "agent-c": issue_card(ca, agent_id="agent-c", endpoint_url="local://agent-c",
                                   capabilities=["word_count"], agent_key=keys["agent-c"], **window)}

    def grant(grant_id: str, **kw: object) -> dict:
        fields = {"grant_id": grant_id, "subject": "user-synthetic-1", "actor": "agent-a",
                  "audience": "agent-b", "task_id": "demo-task", "capabilities": ["word_count"],
                  "not_before": now - 60, "expires_at": now + 600, **kw}
        return issue_grant(users, **fields)

    with tempfile.TemporaryDirectory(prefix="agent-movement-peer-") as root:
        db = Path(root) / "receiver.sqlite"
        config = Path(root) / "receiver.json"
        provisioning = {"card": cards["agent-b"], "key": keys["agent-b"].export(),
                        "trust": trust.export(), "capabilities": ["word_count"], "db": str(db)}
        if enc_b is not None:
            provisioning["enc_key"] = enc_b.export()
        config.write_text(canonical(provisioning))
        os.chmod(config, 0o600)
        process = subprocess.Popen([sys.executable, "-m", "agent_movement.peer_http", "--config", str(config)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        fake = make_peer_server()
        fake_url = f"http://127.0.0.1:{fake.server_port}"
        fake.receiver = _Static(issue_card(rogue_ca, agent_id="agent-b", endpoint_url=fake_url,
                                           capabilities=["word_count"], agent_key=rogue_a, **window))
        threading.Thread(target=fake.serve_forever, daemon=True).start()
        results = []
        try:
            assert process.stdout is not None
            json.loads(process.stdout.readline())  # receiver is listening

            def run(name: str, *, agent: str = "agent-a", key: object = None, url: str = b_url,
                    g: dict | None = None, schema: str | None = None, before: object = None) -> None:
                wire = RecordingTransport(HttpTransport(), on_request=before)
                extra = {"schema_version": schema} if schema else {}
                client = PeerClient(cards[agent], key or keys[agent], trust, wire,
                                    never_send=[PROVIDER_CANARY],
                                    require_confidentiality=delivery == "hpke", **extra)
                outcome = {"scenario": name}
                try:
                    receipt = client.handoff(url=url, destination_id="agent-b", movement_id=f"mv-{name}",
                                             task_id="demo-task", kind="word_count",
                                             text=f"synthetic demo words {TASK_CANARY}",
                                             grant=g or grant(f"grant-{name}"),
                                             idempotency_key=f"op-{name}", trace_id=f"trace-{name}")
                    outcome.update(result="completed", effect=receipt["effect"],
                                   value=receipt["receipt"]["artifact"]["value"], payload_sent=True)
                except HandoffAborted as exc:
                    outcome.update(result="denied", stage=exc.stage, reason=exc.reason,
                                   payload_sent=exc.payload_sent)
                wire_bytes = wire.transmitted()
                outcome["delivery_requests"] = sum(x["path"] == DELIVERY_PATH for x in wire.exchanges)
                outcome["task_canary_on_wire"] = TASK_CANARY.encode() in wire_bytes
                outcome["provider_canary_on_wire"] = PROVIDER_CANARY.encode() in wire_bytes
                results.append(outcome)

            def revoke_before_delivery(method: str, path: str, body: bytes | None) -> None:
                if path == DELIVERY_PATH:
                    HttpTransport().request("POST", b_url, "/v0/revocations", canonical(
                        issue_revocation(users, "grant-revoked-in-flight", int(time.time()))).encode())

            run("success")
            run("fake-receiver", url=fake_url)
            run("fake-sender", key=rogue_a)
            run("insider-wrong-actor", agent="agent-c")
            run("expired-grant", g=grant("grant-expired", expires_at=now - 1))
            HttpTransport().request("POST", b_url, "/v0/revocations",
                                    canonical(issue_revocation(users, "grant-revoked", now)).encode())
            run("revoked-grant", g=grant("grant-revoked"))
            run("wrong-audience", g=grant("grant-aud", audience="agent-c"))
            run("wrong-task", g=grant("grant-task", task_id="other-task"))
            run("unsupported-schema", schema="9.9.9-future")
            run("revoked-in-flight", g=grant("grant-revoked-in-flight"), before=revoke_before_delivery)
        finally:
            fake.shutdown()
            fake.server_close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        with sqlite3.connect(db) as conn:
            rows = conn.execute(f"SELECT {','.join(TRACE_FIELDS)} FROM peer_trace ORDER BY seq").fetchall()
        traces = [dict(zip(TRACE_FIELDS, row)) for row in rows]
        stored = b"".join(p.read_bytes() for p in Path(root).iterdir() if p.name.startswith("receiver.sqlite"))

    confidentiality = "hpke" if delivery == "hpke" else "none (plaintext delivery, no confidentiality)"
    print(json.dumps({"alg": alg, "delivery_confidentiality": confidentiality, "scenarios": results,
                      "receiver_sanitized_trace": traces,
                      "task_canary_in_receiver_db": TASK_CANARY.encode() in stored}, indent=2))
    expected_completed = {"success"}
    in_flight = {"revoked-in-flight"}  # documented window: payload sent, then refused
    for r in results:
        if (r["result"] == "completed") != (r["scenario"] in expected_completed):
            raise SystemExit(f"unexpected outcome: {r}")
        if r["provider_canary_on_wire"]:
            raise SystemExit(f"provider credential leaked: {r['scenario']}")
        if delivery == "hpke" and r["task_canary_on_wire"]:
            raise SystemExit(f"task text visible on the wire despite HPKE delivery: {r['scenario']}")
        if r["result"] == "denied" and r["scenario"] not in in_flight and (
                r["payload_sent"] or r["delivery_requests"] or r["task_canary_on_wire"]):
            raise SystemExit(f"task content disclosed before denial: {r['scenario']}")
    if TASK_CANARY.encode() in stored:
        raise SystemExit("task text persisted by receiver")


if __name__ == "__main__":
    main()
