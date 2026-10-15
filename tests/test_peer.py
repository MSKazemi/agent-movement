"""Issue #8: authenticated peers, scoped grants and denial BEFORE task text is transmitted.

Every key, grant and canary below is synthetic and generated per test run.
"""

import json
import logging
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_movement.core import SQLiteStore, canonical
from agent_movement.peer import (CARD_PATH, DELIVERY_PATH, PREFLIGHT_PATH, REVOCATION_PATH,
                                 TRACE_FIELDS, AuthorizedEffectGateway, HandoffAborted,
                                 HttpTransport, InProcessTransport, PeerClient, PeerLedger,
                                 PeerReceiver, RecordingTransport)
from agent_movement.peer_http import make_peer_server
from agent_movement.trust import (ED25519, HS256, PEER_SCHEMA_VERSION, DisclosureBlocked,
                                  TrustStore, Unauthorized, ed25519_available, generate_key,
                                  issue_card, issue_grant, issue_revocation, seal)

# Synthetic canaries. They must never appear where the test says they must not.
TASK_CANARY = "CANARY-TASK-c0ffee-7d1e"
PROVIDER_CANARY = "CANARY-PROVIDER-TOKEN-91ab-not-a-real-token"
TEXT = f"synthetic four words {TASK_CANARY}"
B_URL, C_URL = "local://agent-b", "local://agent-c"


class Clock:
    def __init__(self, t=1_800_000_000):
        self.t = t

    def __call__(self):
        return self.t


class World:
    """Synthetic test CA, user authority, three honest agents and rogue material."""

    def __init__(self, alg, root, b_url=B_URL):
        self.alg, self.clock = alg, Clock()
        now = self.clock.t
        self.ca, self.rogue_ca = generate_key(alg, "test-ca"), generate_key(alg, "test-ca")
        self.users, self.rogue_users = generate_key(alg, "user-authority"), generate_key(alg, "user-authority")
        self.keys = {name: generate_key(alg, f"{name}-key") for name in ("agent-a", "agent-b", "agent-c")}
        # Rogue keys reuse the honest kids: the attacker can copy any public identifier.
        self.rogue = {name: generate_key(alg, f"{name}-key") for name in self.keys}
        hmac_peers = list(self.keys.values()) if alg == HS256 else []
        self.trust = TrustStore.build([self.ca], [self.users], hmac_peers)
        self.b_url = b_url
        self.cards = {
            "agent-a": self.card("agent-a", "local://agent-a", ["word_count"]),
            "agent-b": self.card("agent-b", b_url, ["word_count"]),
            "agent-c": self.card("agent-c", C_URL, ["word_count", "sha256"]),
        }
        self.store = SQLiteStore(Path(root) / "receiver.sqlite")
        self.receiver = PeerReceiver(self.cards["agent-b"], self.keys["agent-b"], self.trust, self.store,
                                     ["word_count"], clock=self.clock)
        self.routes = {b_url: self.receiver}
        self.wire = RecordingTransport(InProcessTransport(self.routes))
        self.now = now

    def card(self, agent, url, caps, ca=None, key=None, **kw):
        times = {"not_before": self.clock.t - 60, "expires_at": self.clock.t + 3600, **kw}
        return issue_card(ca or self.ca, agent_id=agent, endpoint_url=url, capabilities=caps,
                          agent_key=key or self.keys[agent], **times)

    def grant(self, issuer=None, **kw):
        fields = {"grant_id": "grant-1", "subject": "user-synthetic-1", "actor": "agent-a",
                  "audience": "agent-b", "task_id": "task-1", "capabilities": ["word_count"],
                  "not_before": self.clock.t - 60, "expires_at": self.clock.t + 600, **kw}
        return issue_grant(issuer or self.users, **fields)

    def client(self, agent="agent-a", card=None, key=None, transport=None, **kw):
        return PeerClient(card or self.cards[agent], key or self.keys[agent], self.trust,
                          transport or self.wire, never_send=[PROVIDER_CANARY], clock=self.clock, **kw)

    def handoff(self, client=None, grant=None, **kw):
        args = {"url": self.b_url, "destination_id": "agent-b", "movement_id": "movement-1",
                "task_id": "task-1", "kind": "word_count", "text": TEXT,
                "grant": grant or self.grant(), "idempotency_key": "op-1", "trace_id": "trace-1", **kw}
        return (client or self.client()).handoff(**args)


class PeerAuthTests(unittest.TestCase):
    ALG = HS256

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(self.ALG, self.tmp.name)
        self.logs = []
        handler = logging.Handler()
        handler.emit = lambda record: self.logs.append(record.getMessage())
        self.handler = handler
        logging.getLogger("agent_movement.peer").addHandler(handler)
        logging.getLogger("agent_movement.peer").setLevel(logging.INFO)

    def tearDown(self):
        logging.getLogger("agent_movement.peer").removeHandler(self.handler)
        self.tmp.cleanup()

    # ---------------------------------------------------------------- helpers
    def db_bytes(self):
        return b"".join(p.read_bytes() for p in Path(self.tmp.name).iterdir())

    def assert_no_canary_anywhere(self, *, wire=True):
        """No task or provider canary in transmitted bytes, traces, logs or the SQLite files."""
        blobs = {"traces": canonical(self.w.receiver.ledger.traces()).encode(),
                 "audit": canonical(self.w.store.audit()).encode(),
                 "logs": "\n".join(self.logs).encode(), "sqlite": self.db_bytes()}
        if wire:
            blobs["wire"] = self.w.wire.transmitted()
        for name, blob in blobs.items():
            for canary in (TASK_CANARY, PROVIDER_CANARY):
                with self.subTest(blob=name, canary=canary):
                    self.assertNotIn(canary.encode(), blob)

    def assert_denied_before_disclosure(self, stage, reason, *, receiver_reason=None):
        with self.assertRaises(HandoffAborted) as ctx:
            self.w.handoff(**getattr(self, "_handoff_kw", {}))
        self.assertEqual(ctx.exception.stage, stage)
        self.assertFalse(ctx.exception.payload_sent)
        self.assertIn(reason, ctx.exception.reason)
        self.assertNotIn(DELIVERY_PATH, self.w.wire.paths())
        self.assert_no_canary_anywhere()
        if receiver_reason:
            denials = [t for t in self.w.receiver.ledger.traces() if t["outcome"] == "denied"]
            self.assertEqual([t["reason"] for t in denials], [receiver_reason])
        self.assertEqual(self.w.receiver.ledger.effects(), [])
        return ctx.exception

    def post(self, path, obj_or_bytes, url=None):
        body = obj_or_bytes if isinstance(obj_or_bytes, bytes) else canonical(obj_or_bytes).encode()
        status, raw = self.w.wire.request("POST", url or self.w.b_url, path, body)
        return status, json.loads(raw)

    # ------------------------------------------------------------ happy path
    def test_success_metadata_first_payload_last(self):
        receipt = self.w.handoff()
        self.assertEqual(receipt["receipt"]["artifact"], {"kind": "word_count", "value": 4})
        self.assertEqual(receipt["effect"], "committed")
        self.assertEqual(self.w.wire.paths(), [CARD_PATH, PREFLIGHT_PATH, DELIVERY_PATH])
        card_req, preflight, delivery = self.w.wire.exchanges
        # Task text leaves the process exactly once, in the delivery request.
        for exchange in (card_req, preflight):
            self.assertNotIn(TASK_CANARY.encode(), exchange["request"] + exchange["response"])
            self.assertNotIn(b"synthetic four words", exchange["request"])
        self.assertIn(TASK_CANARY.encode(), delivery["request"])
        self.assertNotIn(TASK_CANARY.encode(), delivery["response"])
        # Never a reusable user/provider credential or key material on the wire.
        wire = self.w.wire.transmitted()
        self.assertNotIn(PROVIDER_CANARY.encode(), wire)
        for key in (*self.w.keys.values(), self.w.ca, self.w.users):
            for form in key.secret_forms():
                self.assertNotIn(form, wire)
        self.assert_no_canary_anywhere(wire=False)
        self.assertEqual([(t["stage"], t["outcome"]) for t in self.w.receiver.ledger.traces()],
                         [("preflight", "allowed"), ("delivery", "allowed")])
        self.assertEqual(self.w.receiver.ledger.traces()[0]["peer"], "agent-a")

    def test_identical_delivery_retry_is_idempotent(self):
        client = self.w.client()
        self.w.handoff(client=client)
        delivery = self.w.wire.exchanges[-1]["request"]
        status, body = self.post(DELIVERY_PATH, delivery)
        self.assertEqual(status, 200)
        self.assertEqual(body["payload"]["effect"], "replayed")
        self.assertTrue(body["payload"]["receipt"]["replayed"])
        self.assertEqual(len(self.w.receiver.ledger.effects()), 1)

    # ---------------------------------------------------------- fake receiver
    def test_fake_receiver_card_from_untrusted_ca(self):
        rogue_card = self.w.card("agent-b", B_URL, ["word_count"], ca=self.w.rogue_ca, key=self.w.rogue["agent-b"])
        fake = PeerReceiver.__new__(PeerReceiver)
        fake.handle = lambda method, path, body: (200, rogue_card) if path == CARD_PATH else (200, {})
        self.w.routes[B_URL] = fake
        # The rogue CA copies the pinned CA's kid, so it fails on the signature itself.
        self.assert_denied_before_disclosure("discovery", "bad_card_signature")
        self.assertEqual(self.w.wire.paths(), [CARD_PATH])

    def test_fake_receiver_card_from_unknown_ca_kid(self):
        other_ca = generate_key(self.ALG, "other-ca")
        rogue_card = self.w.card("agent-b", B_URL, ["word_count"], ca=other_ca, key=self.w.rogue["agent-b"])
        self.w.routes[B_URL] = type("Fake", (), {"handle": staticmethod(lambda m, p, b: (200, rogue_card))})()
        self.assert_denied_before_disclosure("discovery", "untrusted_card_issuer")

    def test_fake_receiver_replays_stolen_card_without_key(self):
        stolen = self.w.cards["agent-b"]
        rogue_key = self.w.rogue["agent-b"]

        class Impostor:
            def handle(self, method, path, body):
                if path == CARD_PATH:
                    return 200, stolen
                payload = json.loads(body)["payload"]
                return 200, seal("admission", {"type": "admission", "admission_id": "adm-" + "1" * 32,
                                               "movement_id": payload["movement_id"],
                                               "destination": payload["destination"],
                                               "client_nonce": payload["client_nonce"],
                                               "preflight_digest": "0" * 64, "expires_at": 2 ** 39}, rogue_key)

        self.w.routes[B_URL] = Impostor()
        self.assert_denied_before_disclosure("preflight", "admission_bad_signature")
        self.assertEqual(self.w.wire.paths(), [CARD_PATH, PREFLIGHT_PATH])

    def test_fake_receiver_with_other_valid_identity(self):
        self.w.routes[B_URL] = PeerReceiver(self.w.cards["agent-c"], self.w.keys["agent-c"], self.w.trust,
                                            self.w.store, ["word_count"], clock=self.w.clock)
        self.assert_denied_before_disclosure("discovery", "wrong_destination_identity")

    def test_fake_receiver_serving_real_card_at_other_endpoint(self):
        fake = PeerReceiver.__new__(PeerReceiver)
        fake.handle = lambda method, path, body: (200, self.w.cards["agent-b"])
        self.w.routes["local://evil"] = fake
        with self.assertRaises(HandoffAborted) as ctx:
            self.w.handoff(url="local://evil")
        self.assertEqual(ctx.exception.reason, "endpoint_mismatch")
        self.assertEqual(self.w.wire.paths(), [CARD_PATH])
        self.assert_no_canary_anywhere()

    def test_expired_receiver_card(self):
        self.w.routes[B_URL] = type("Expired", (), {"handle": staticmethod(
            lambda m, p, b: (200, self.w.card("agent-b", B_URL, ["word_count"], expires_at=self.w.now - 1)))})()
        self.assert_denied_before_disclosure("discovery", "card_expired")

    # ------------------------------------------------------------ fake sender
    def test_fake_sender_card_from_untrusted_ca(self):
        rogue_card = self.w.card("agent-a", "local://agent-a", ["word_count"], ca=self.w.rogue_ca,
                                 key=self.w.rogue["agent-a"])
        client = self.w.client(card=rogue_card, key=self.w.rogue["agent-a"])
        self._handoff_kw = {"client": client}
        exc = self.assert_denied_before_disclosure("preflight", "http_401",
                                                   receiver_reason="bad_card_signature")
        self.assertEqual(exc.status, 401)
        self.assertIsNone(self.w.receiver.ledger.traces()[0]["peer"])
        self.assertEqual(self.w.receiver.ledger.traces()[0]["claimed_peer"], "agent-a")

    def test_fake_sender_with_stolen_card_but_no_key(self):
        client = self.w.client(card=self.w.cards["agent-a"], key=self.w.rogue["agent-a"])
        self._handoff_kw = {"client": client}
        self.assert_denied_before_disclosure("preflight", "http_401", receiver_reason="bad_signature")

    def test_insider_sender_with_stolen_grant(self):
        # agent-c is a genuine, CA-certified peer -- but the user granted agent-a, not agent-c.
        self._handoff_kw = {"client": self.w.client("agent-c")}
        self.assert_denied_before_disclosure("preflight", "http_403", receiver_reason="wrong_actor")

    def test_self_declared_legacy_envelope_is_not_identity(self):
        from test_core import fixture
        status, body = self.post(PREFLIGHT_PATH, fixture())
        self.assertEqual((status, body), (400, {"error": "invalid_contract"}))

    def test_tampered_preflight_rejected(self):
        body, _ = self.w.client().build_preflight(
            url=B_URL, destination_id="agent-b", movement_id="movement-1", task_id="task-1",
            kind="word_count", text=TEXT, grant=self.w.grant(), idempotency_key="op-1", trace_id="t")
        sealed = json.loads(body)
        sealed["payload"]["logical_task_id"] = "task-2"
        self.assertEqual(self.post(PREFLIGHT_PATH, sealed)[0], 401)

    def test_replayed_and_stale_preflight(self):
        body, _ = self.w.client().build_preflight(
            url=B_URL, destination_id="agent-b", movement_id="movement-1", task_id="task-1",
            kind="word_count", text=TEXT, grant=self.w.grant(), idempotency_key="op-1", trace_id="t")
        self.assertEqual(self.post(PREFLIGHT_PATH, body)[0], 200)
        self.assertEqual(self.post(PREFLIGHT_PATH, body)[0], 409)
        self.w.clock.t += 121
        self.assertEqual(self.post(PREFLIGHT_PATH, body)[0], 401)
        self.assertEqual([t["reason"] for t in self.w.receiver.ledger.traces()],
                         ["admitted", "conflict", "stale_request"])

    def test_delivery_signed_by_other_peer_rejected(self):
        client = self.w.client()
        body, secret = client.build_preflight(
            url=B_URL, destination_id="agent-b", movement_id="movement-1", task_id="task-1",
            kind="word_count", text=TEXT, grant=self.w.grant(), idempotency_key="op-1", trace_id="t")
        admission_id = self.post(PREFLIGHT_PATH, body)[1]["payload"]["admission_id"]
        hijack = self.w.client("agent-c").build_delivery(admission_id, secret["task"], secret["salt"])
        self.assertEqual(self.post(DELIVERY_PATH, hijack)[0], 401)
        self.assertEqual(self.w.store.audit(), [])
        self.assert_no_canary_anywhere(wire=False)

    def test_delivery_must_match_admitted_commitment(self):
        client = self.w.client()
        body, secret = client.build_preflight(
            url=B_URL, destination_id="agent-b", movement_id="movement-1", task_id="task-1",
            kind="word_count", text="harmless admitted text", grant=self.w.grant(),
            idempotency_key="op-1", trace_id="t")
        admission_id = self.post(PREFLIGHT_PATH, body)[1]["payload"]["admission_id"]
        swapped = client.build_delivery(admission_id, {"kind": "word_count", "text": TEXT}, secret["salt"])
        self.assertEqual(self.post(DELIVERY_PATH, swapped)[0], 403)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "commitment_mismatch")
        self.assert_no_canary_anywhere(wire=False)

    def test_delivery_without_admission_not_logged(self):
        body = self.w.client().build_delivery("adm-" + "2" * 32, {"kind": "word_count", "text": TEXT}, b"s" * 32)
        self.assertEqual(self.post(DELIVERY_PATH, body)[0], 403)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "unknown_admission")
        self.assert_no_canary_anywhere(wire=False)

    # ---------------------------------------------------------------- grants
    def test_expired_grant(self):
        self._handoff_kw = {"grant": self.w.grant(expires_at=self.w.now - 1)}
        self.assert_denied_before_disclosure("preflight", "http_403", receiver_reason="grant_expired")

    def test_not_yet_valid_grant(self):
        self._handoff_kw = {"grant": self.w.grant(not_before=self.w.now + 30)}
        self.assert_denied_before_disclosure("preflight", "http_403", receiver_reason="grant_not_yet_valid")

    def test_revoked_grant_via_signed_notice(self):
        status, _ = self.post(REVOCATION_PATH, issue_revocation(self.w.users, "grant-1", self.w.now))
        self.assertEqual(status, 200)
        self.assert_denied_before_disclosure("preflight", "http_403", receiver_reason="grant_revoked")

    def test_forged_revocation_notice_rejected(self):
        status, _ = self.post(REVOCATION_PATH, issue_revocation(self.w.rogue_users, "grant-1", self.w.now))
        self.assertEqual(status, 401)
        self.assertEqual(self.w.handoff()["effect"], "committed")

    def test_grant_from_untrusted_issuer(self):
        self._handoff_kw = {"grant": self.w.grant(issuer=self.w.rogue_users)}
        self.assert_denied_before_disclosure("preflight", "http_401", receiver_reason="bad_grant_signature")

    def test_wrong_audience(self):
        self._handoff_kw = {"grant": self.w.grant(audience="agent-c")}
        self.assert_denied_before_disclosure("preflight", "http_403", receiver_reason="wrong_audience")

    def test_wrong_task(self):
        self._handoff_kw = {"grant": self.w.grant(task_id="task-2")}
        self.assert_denied_before_disclosure("preflight", "http_403", receiver_reason="wrong_task")

    def test_capability_not_granted(self):
        self._handoff_kw = {"grant": self.w.grant(capabilities=["sha256"])}
        self.assert_denied_before_disclosure("preflight", "http_403", receiver_reason="capability_not_granted")

    def test_capability_not_allowlisted(self):
        # Client side: agent-b does not advertise sha256, so nothing beyond discovery is sent.
        self._handoff_kw = {"kind": "sha256", "grant": self.w.grant(capabilities=["sha256"])}
        self.assert_denied_before_disclosure("discovery", "capability_not_advertised")
        # Receiver side, if a client skips discovery checks: still denied, metadata only.
        body, _ = self.w.client().build_preflight(
            url=B_URL, destination_id="agent-b", movement_id="movement-2", task_id="task-1",
            kind="sha256", text=TEXT, grant=self.w.grant(capabilities=["sha256"]),
            idempotency_key="op-2", trace_id="t")
        self.assertEqual(self.post(PREFLIGHT_PATH, body)[0], 403)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "capability_not_allowlisted")
        self.assert_no_canary_anywhere()

    def test_unsupported_schema(self):
        client = self.w.client(schema_version="9.9.9-future")
        self._handoff_kw = {"client": client}
        self.assert_denied_before_disclosure("discovery", "unsupported_schema")
        body, _ = client.build_preflight(
            url=B_URL, destination_id="agent-b", movement_id="movement-1", task_id="task-1",
            kind="word_count", text=TEXT, grant=self.w.grant(), idempotency_key="op-1", trace_id="t")
        self.assertEqual(self.post(PREFLIGHT_PATH, body), (400, {"error": "unsupported_schema"}))
        self.assert_no_canary_anywhere()

    def test_wrong_destination_binding_in_preflight(self):
        body, _ = self.w.client().build_preflight(
            url="local://evil", destination_id="agent-b", movement_id="movement-1", task_id="task-1",
            kind="word_count", text=TEXT, grant=self.w.grant(), idempotency_key="op-1", trace_id="t")
        self.assertEqual(self.post(PREFLIGHT_PATH, body)[0], 403)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "wrong_destination")

    # ------------------------------------------------- revocation races / commit recheck
    def test_revocation_between_admission_and_delivery(self):
        def revoke_before_delivery(method, path, body):
            if path == DELIVERY_PATH:
                self.w.receiver.ledger.revoke("grant-1", self.w.clock.t)
        self.w.wire.on_request = revoke_before_delivery
        with self.assertRaises(HandoffAborted) as ctx:
            self.w.handoff()
        self.assertEqual((ctx.exception.stage, ctx.exception.status), ("delivery", 403))
        # Known window: the text WAS transmitted, but was neither executed nor persisted/logged.
        self.assertTrue(ctx.exception.payload_sent)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "grant_revoked")
        self.assertEqual(self.w.store.audit(), [])
        self.assertEqual(self.w.receiver.ledger.effects(), [])
        self.assert_no_canary_anywhere(wire=False)

    def test_revocation_between_admission_and_effect_commit(self):
        self.w.receiver.before_effect_commit = lambda record: self.w.receiver.ledger.revoke("grant-1", self.w.clock.t)
        with self.assertRaises(HandoffAborted) as ctx:
            self.w.handoff()
        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "effect_grant_revoked")
        self.assertEqual(self.w.receiver.ledger.effects(), [])
        self.assertEqual([e["event"] for e in self.w.receiver.ledger.authority_log()], ["revoke"])
        self.assert_no_canary_anywhere(wire=False)

    def test_expiry_between_admission_and_effect_commit(self):
        grant = self.w.grant(expires_at=self.w.now + 5)

        def advance(record):
            self.w.clock.t += 10
        self.w.receiver.before_effect_commit = advance
        with self.assertRaises(HandoffAborted):
            self.w.handoff(grant=grant)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "effect_grant_expired")
        self.assertEqual(self.w.receiver.ledger.effects(), [])

    def test_admission_expires(self):
        def late(method, path, body):
            if path == DELIVERY_PATH:
                self.w.clock.t += 61
        self.w.wire.on_request = late
        with self.assertRaises(HandoffAborted):
            self.w.handoff()
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "admission_expired")

    def test_concurrent_revocation_race_is_linearized(self):
        gateway = AuthorizedEffectGateway(PeerLedger(self.w.store), self.w.clock)
        grant = json.loads(canonical(self.w.grant()))["payload"]
        self.assertTrue(gateway.commit(grant, "agent-b", "task-1", "effect-0", "x"))
        start = threading.Barrier(9)

        def commit(i):
            start.wait()
            try:
                return gateway.commit(grant, "agent-b", "task-1", f"effect-{i}", "x")
            except Unauthorized:
                return None

        def revoke():
            start.wait()
            return self.w.receiver.ledger.revoke("grant-1", self.w.clock.t)

        with ThreadPoolExecutor(max_workers=9) as pool:
            futures = [pool.submit(commit, i) for i in range(1, 9)]
            futures.append(pool.submit(revoke))
            outcomes = [f.result() for f in futures]
        log = self.w.receiver.ledger.authority_log()
        revoke_seq = next(e["seq"] for e in log if e["event"] == "revoke")
        committed = [e for e in log if e["event"] == "effect"]
        self.assertTrue(outcomes[-1])
        self.assertTrue(all(e["seq"] < revoke_seq for e in committed), log)
        self.assertEqual(len(committed), 1 + sum(o is True for o in outcomes[:-1]))
        with self.assertRaises(Unauthorized):
            gateway.commit(grant, "agent-b", "task-1", "effect-late", "x")

    def test_effect_gateway_scope_checks(self):
        gateway = AuthorizedEffectGateway(PeerLedger(self.w.store), self.w.clock)
        grant = json.loads(canonical(self.w.grant()))["payload"]
        for agent, task, reason in [("agent-c", "task-1", "wrong_audience"), ("agent-b", "task-2", "wrong_task")]:
            with self.subTest(reason=reason):
                with self.assertRaises(Unauthorized) as ctx:
                    gateway.commit(grant, agent, task, "effect-1", "x")
                self.assertEqual(ctx.exception.reason, reason)

    # -------------------------------------------------- credentials and traces
    def test_sender_guard_blocks_held_credential_before_any_post(self):
        with self.assertRaises(DisclosureBlocked):
            self.w.handoff(text=f"please use {PROVIDER_CANARY}")
        self.assertEqual(self.w.wire.paths(), [CARD_PATH])
        self.assertNotIn(PROVIDER_CANARY.encode(), self.w.wire.transmitted())

    def test_traces_are_sanitized(self):
        self.w.handoff()
        for grant in (self.w.grant(expires_at=self.w.now - 1), self.w.grant(audience="agent-c")):
            with self.assertRaises(HandoffAborted):
                self.w.handoff(grant=grant, movement_id="movement-x", idempotency_key="op-x")
        for row in self.w.receiver.ledger.traces():
            self.assertEqual(tuple(row), TRACE_FIELDS)
            self.assertNotIn("sig", canonical(row))
        self.assertTrue(self.logs)
        self.assert_no_canary_anywhere(wire=False)

    def test_limitation_on_path_relay_sees_payload_without_channel_security(self):
        """Documented gap, not a feature: an attacker that *owns the real endpoint address*
        can relay preflight/admission verbatim and read the delivery. Needs mTLS / channel
        binding or payload encryption to the card key (docs/peer-authentication.md)."""
        real = self.w.receiver
        seen = []

        class Relay:
            def handle(self, method, path, body):
                seen.append(body)
                return real.handle(method, path, body)

        self.w.routes[B_URL] = Relay()
        self.assertEqual(self.w.handoff()["effect"], "committed")
        self.assertTrue(any(TASK_CANARY.encode() in b for b in seen))


@unittest.skipUnless(ed25519_available(), "optional [ed25519] extra (cryptography) not installed")
class PeerAuthEd25519Tests(PeerAuthTests):
    ALG = ED25519

    def test_verifier_cannot_forge_peer_signature(self):
        # Asymmetric mode: holding agent-a's *verification* key does not allow signing as agent-a.
        public_only = self.w.keys["agent-a"].verifier()
        with self.assertRaises(TypeError):
            public_only.sign(b"x")
        self.assertEqual(self.w.trust.peer_keys, {})


class PeerHttpTests(unittest.TestCase):
    """Same protocol over a real loopback socket."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_peer_server()
        url = f"http://127.0.0.1:{self.server.server_port}"
        self.w = World(HS256, self.tmp.name, b_url=url)
        self.server.receiver = self.w.receiver
        self.w.wire = RecordingTransport(HttpTransport())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def test_success_and_denials_over_loopback(self):
        self.assertEqual(self.w.handoff()["effect"], "committed")
        with self.assertRaises(HandoffAborted) as ctx:
            self.w.handoff(client=self.w.client(key=self.w.rogue["agent-a"]), movement_id="m-2")
        self.assertEqual(ctx.exception.status, 401)
        with self.assertRaises(HandoffAborted) as ctx:
            self.w.handoff(grant=self.w.grant(task_id="task-2"), movement_id="m-3")
        self.assertEqual(ctx.exception.status, 403)
        delivered = [x for x in self.w.wire.exchanges if x["path"] == DELIVERY_PATH]
        self.assertEqual(len(delivered), 1)
        self.assertNotIn(PROVIDER_CANARY.encode(), self.w.wire.transmitted())

    def test_http_strictness(self):
        url = self.w.b_url + PREFLIGHT_PATH
        import urllib.error
        import urllib.request
        request = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(ctx.exception.code, 415)
        ctx.exception.close()
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(PEER_SCHEMA_VERSION, "0.1.0-peer-draft")


if __name__ == "__main__":
    unittest.main()
