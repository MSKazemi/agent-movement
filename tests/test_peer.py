"""Issue #8: authenticated peers, scoped grants and denial BEFORE task text is transmitted.
Issue #19: HPKE-sealed delivery to the receiver's card key closes the on-path relay gap.

Every key, grant and canary below is synthetic and generated per test run.
"""

import json
import logging
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from agent_movement import peer as peer_module
from agent_movement.core import SQLiteStore, canonical, digest
from agent_movement.peer import (CARD_PATH, DELIVERY_PATH, PREFLIGHT_PATH, REVOCATION_PATH,
                                 TRACE_FIELDS, AuthorizedEffectGateway, DeliverySeal, HandoffAborted,
                                 HttpTransport, InProcessTransport, PeerClient, PeerLedger,
                                 PeerReceiver, RecordingTransport)
from agent_movement.peer_http import make_peer_server
from agent_movement.trust import (ED25519, HS256, PEER_SCHEMA_VERSION, ContractError, DisclosureBlocked,
                                  HpkeKey, TrustStore, Unauthorized, b64d, b64e, delivery_info,
                                  ed25519_available, generate_key, hpke_available, import_enc_key,
                                  issue_card, issue_grant, issue_revocation, seal, verify_card)

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

    def __init__(self, alg, root, b_url=B_URL, encrypt=False):
        self.alg, self.clock, self.encrypt = alg, Clock(), encrypt
        now = self.clock.t
        self.ca, self.rogue_ca = generate_key(alg, "test-ca"), generate_key(alg, "test-ca")
        self.users, self.rogue_users = generate_key(alg, "user-authority"), generate_key(alg, "user-authority")
        self.keys = {name: generate_key(alg, f"{name}-key") for name in ("agent-a", "agent-b", "agent-c")}
        # Rogue keys reuse the honest kids: the attacker can copy any public identifier.
        self.rogue = {name: generate_key(alg, f"{name}-key") for name in self.keys}
        # Receivers' X25519 delivery keys (HPKE mode only); the origin agent-a needs none.
        self.enc = {name: HpkeKey.generate(f"{name}-enc") for name in ("agent-b", "agent-c")} if encrypt else {}
        self.rogue_enc = {name: HpkeKey.generate(f"{name}-enc") for name in self.enc}
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
                                     ["word_count"], clock=self.clock, enc_key=self.enc.get("agent-b"))
        self.routes = {b_url: self.receiver}
        self.wire = RecordingTransport(InProcessTransport(self.routes))
        self.now = now

    def card(self, agent, url, caps, ca=None, key=None, enc_key="default", **kw):
        times = {"not_before": self.clock.t - 60, "expires_at": self.clock.t + 3600, **kw}
        enc_key = self.enc.get(agent) if enc_key == "default" else enc_key
        return issue_card(ca or self.ca, agent_id=agent, endpoint_url=url, capabilities=caps,
                          agent_key=key or self.keys[agent], enc_key=enc_key, **times)

    def all_secret_forms(self):
        keys = (*self.keys.values(), *self.enc.values(), self.ca, self.users)
        return [form for key in keys for form in key.secret_forms()]

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
    """Stdlib-only mode: HS256 signatures and plaintext delivery (NO confidentiality)."""

    ALG = HS256
    ENCRYPT = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(self.ALG, self.tmp.name, encrypt=self.ENCRYPT)
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

    def preflight(self, client=None, text=TEXT, **kw):
        """Run a preflight by hand; returns (client, admission payload, sender secret)."""
        client = client or self.w.client()
        args = {"url": self.w.b_url, "destination_id": "agent-b", "movement_id": "movement-1",
                "task_id": "task-1", "kind": "word_count", "text": text, "grant": self.w.grant(),
                "idempotency_key": "op-1", "trace_id": "t", **kw}
        body, secret = client.build_preflight(**args)
        status, response = self.post(PREFLIGHT_PATH, body)
        self.assertEqual(status, 200, response)
        return client, response["payload"], secret

    def receiver_card(self):
        return verify_card(self.w.cards["agent-b"], self.w.trust, self.w.clock.t)

    def delivery(self, sender, admission, secret, task=None, salt=None, origin=None):
        """Delivery as an honest client in this mode would build it (sealed iff HPKE mode).
        ``sender`` signs; ``origin`` (default: sender) is the client whose preflight it was."""
        sealed_to = (origin or sender).delivery_seal(self.receiver_card(), admission, secret["sealed"])
        return sender.build_delivery(admission["admission_id"], task or secret["task"],
                                     salt or secret["salt"], sealed_to)

    # ------------------------------------------------------------ happy path
    def test_success_metadata_first_payload_last(self):
        client = self.w.client()
        receipt = self.w.handoff(client=client)
        label = "hpke_sealed" if self.ENCRYPT else "plaintext_no_confidentiality"
        self.assertEqual([e["reason"] for e in self.client_events("delivery", client)],
                         [label, "effect_committed"])
        self.assertEqual(receipt["receipt"]["artifact"], {"kind": "word_count", "value": 4})
        self.assertEqual(receipt["effect"], "committed")
        self.assertEqual(self.w.wire.paths(), [CARD_PATH, PREFLIGHT_PATH, DELIVERY_PATH])
        card_req, preflight, delivery = self.w.wire.exchanges
        # Task text leaves the process exactly once, in the delivery request -- and in HPKE
        # mode only as ciphertext, so it is not visible in any captured byte at all.
        for exchange in (card_req, preflight):
            self.assertNotIn(TASK_CANARY.encode(), exchange["request"] + exchange["response"])
            self.assertNotIn(b"synthetic four words", exchange["request"])
        if self.ENCRYPT:
            self.assertNotIn(TASK_CANARY.encode(), delivery["request"])
            self.assertNotIn(b'"text"', delivery["request"])
            self.assertNotIn(b'"artifact"', delivery["response"])  # receipt is encrypted too
        else:
            self.assertIn(TASK_CANARY.encode(), delivery["request"])  # labelled: no confidentiality
        self.assertNotIn(TASK_CANARY.encode(), delivery["response"])
        # Never a reusable user/provider credential or key material on the wire.
        wire = self.w.wire.transmitted()
        self.assertNotIn(PROVIDER_CANARY.encode(), wire)
        for form in self.w.all_secret_forms():
            self.assertNotIn(form, wire)
        self.assert_no_canary_anywhere(wire=False)
        self.assertEqual([(t["stage"], t["outcome"]) for t in self.w.receiver.ledger.traces()],
                         [("preflight", "allowed"), ("delivery", "allowed")])
        self.assertEqual(self.w.receiver.ledger.traces()[0]["peer"], "agent-a")

    def test_identical_delivery_retry_is_idempotent(self):
        client, admission, secret = self.preflight()
        sealed_to = client.delivery_seal(self.receiver_card(), admission, secret["sealed"])
        delivery = client.build_delivery(admission["admission_id"], secret["task"], secret["salt"], sealed_to)
        bodies = [self.post(DELIVERY_PATH, delivery) for _ in range(2)]
        self.assertEqual([status for status, _ in bodies], [200, 200])
        receipts = [sealed_to.open_response(b) if sealed_to else b for _, b in bodies]
        self.assertEqual([r["payload"]["effect"] for r in receipts], ["committed", "replayed"])
        self.assertTrue(receipts[1]["payload"]["receipt"]["replayed"])
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
                                            self.w.store, ["word_count"], clock=self.w.clock,
                                            enc_key=self.w.enc.get("agent-c"))
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
        client, admission, secret = self.preflight()
        hijack = self.delivery(self.w.client("agent-c"), admission, secret, origin=client)
        self.assertEqual(self.post(DELIVERY_PATH, hijack)[0], 401)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "key_mismatch")  # not agent-a's kid
        self.assertEqual(self.w.store.audit(), [])
        self.assert_no_canary_anywhere(wire=False)

    def test_delivery_must_match_admitted_commitment(self):
        client, admission, secret = self.preflight(text="harmless admitted text")
        swapped = self.delivery(client, admission, secret, task={"kind": "word_count", "text": TEXT})
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

    @staticmethod
    def client_events(stage, client):
        return [e for e in client.trace if e["stage"] == stage]

    def test_on_path_relay_sees_only_ciphertext_with_hpke(self):
        """An attacker that *owns the real endpoint address* relays every exchange verbatim
        and keeps every byte in both directions.

        HPKE mode (issue #19): the relay captures ciphertext only -- no canary, no task
        field, no receipt result -- and the handoff still completes.
        Plaintext mode (stdlib-only, labelled "no confidentiality"): the documented gap
        from issue #8 remains, and the relay reads the task text."""
        real = self.w.receiver
        captured = []

        class Relay:
            def handle(self, method, path, body):
                status, response = real.handle(method, path, body)
                captured.extend([body, json.dumps(response, sort_keys=True).encode()])
                return status, response

        self.w.routes[B_URL] = Relay()
        self.assertEqual(self.w.handoff()["effect"], "committed")
        relay_bytes = b"\n".join(captured)
        self.assertGreater(len(captured), 4)
        if self.ENCRYPT:
            self.assertNotIn(TASK_CANARY.encode(), relay_bytes)
            for marker in (b"synthetic four words", b'"text"', b'"salt"', b'"artifact"', b'"envelope_digest"'):
                self.assertNotIn(marker, relay_bytes)
            self.assertIn(b'"enc"', relay_bytes)
            self.assertIn(b'"encrypted-receipt"', relay_bytes)
        else:
            self.assertIn(TASK_CANARY.encode(), relay_bytes)  # no confidentiality, by design


class SealedDeliveryCases:
    """Issue #19 cases that exist only when the receiver card carries an X25519 enc_key."""

    def resign(self, client, body, mutate):
        payload = json.loads(body)["payload"]
        mutate(payload)
        return canonical(seal("delivery", payload, client.key)).encode()

    def transcript(self, admission, secret):
        card = self.receiver_card()
        return {"card_digest": card.digest, "enc_kid": card.enc_key.kid,
                "movement_id": admission["movement_id"], "origin_id": "agent-a", "audience": "agent-b",
                "endpoint_url": self.w.b_url, "client_nonce": secret["sealed"]["payload"]["client_nonce"],
                "admission_id": admission["admission_id"], "preflight_digest": digest(secret["sealed"])}

    def assert_rejected_unused(self, body, status, reason):
        """Rejected with ``reason``; the decrypted task never reaches execution or storage."""
        with mock.patch.object(self.w.store, "receive", side_effect=AssertionError("task executed")):
            self.assertEqual(self.post(DELIVERY_PATH, body)[0], status)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], reason)
        self.assertEqual(self.w.store.audit(), [])
        self.assertEqual(self.w.receiver.ledger.effects(), [])
        self.assert_no_canary_anywhere(wire=False)

    def assert_honest_delivery_still_works(self, client, admission, secret):
        status, body = self.post(DELIVERY_PATH, self.delivery(client, admission, secret))
        self.assertEqual((status, body.get("type")), (200, "encrypted-receipt"))
        self.assertEqual(len(self.w.receiver.ledger.effects()), 1)

    def test_hpke_enc_key_is_signed_into_the_card(self):
        card = json.loads(canonical(self.w.cards["agent-b"]))
        self.assertEqual(card["payload"]["enc_key"], self.w.enc["agent-b"].descriptor())
        card["payload"]["enc_key"]["public"] = self.w.rogue_enc["agent-b"].public_value()  # relay's own key
        self.w.routes[B_URL] = type("Swap", (), {"handle": staticmethod(lambda m, p, b: (200, card))})()
        self.assert_denied_before_disclosure("discovery", "bad_card_signature")
        # A receiver must hold exactly the private key its card advertises.
        for enc_key in (None, self.w.rogue_enc["agent-b"]):
            with self.subTest(enc_key=enc_key), self.assertRaises(ContractError):
                PeerReceiver(self.w.cards["agent-b"], self.w.keys["agent-b"], self.w.trust, self.w.store,
                             ["word_count"], clock=self.w.clock, enc_key=enc_key)

    def test_hpke_tampered_ciphertext_rejected_before_use(self):
        client, admission, secret = self.preflight()
        body = self.delivery(client, admission, secret)

        def flip(payload):
            ct = bytearray(b64d(payload["enc"]["ct"], max_len=10 ** 6))
            ct[-1] ^= 1
            payload["enc"]["ct"] = b64e(bytes(ct))
        # Re-signed by the genuine origin: the signature passes, the AEAD tag does not.
        self.assert_rejected_unused(self.resign(client, body, flip), 401, "delivery_decrypt_failed")
        # Tampered by anyone else: the origin signature over the ciphertext fails first.
        forged = json.loads(body)
        flip(forged["payload"])
        self.assert_rejected_unused(canonical(forged).encode(), 401, "bad_signature")
        truncated = self.resign(client, body, lambda p: p["enc"].update(ct=p["enc"]["ct"][:40]))
        self.assert_rejected_unused(truncated, 401, "delivery_decrypt_failed")
        self.assert_honest_delivery_still_works(client, admission, secret)

    def test_hpke_transcript_mismatch_rejected(self):
        client, admission, secret = self.preflight()
        honest = self.transcript(admission, secret)
        self.assertEqual(delivery_info(**honest),
                         client.delivery_seal(self.receiver_card(), admission, secret["sealed"]).info)
        for name, value in [("movement_id", "movement-2"), ("origin_id", "agent-c"), ("audience", "agent-c"),
                            ("endpoint_url", C_URL), ("client_nonce", "A" * 32),
                            ("admission_id", "adm-" + "3" * 32), ("preflight_digest", "0" * 64),
                            ("card_digest", "f" * 64), ("enc_kid", "other-enc")]:
            with self.subTest(field=name):
                sealed_to = DeliverySeal(self.w.enc["agent-b"], delivery_info(**{**honest, name: value}),
                                         b"r" * 32)
                body = client.build_delivery(admission["admission_id"], secret["task"], secret["salt"], sealed_to)
                self.assert_rejected_unused(body, 401, "delivery_decrypt_failed")
        self.assert_honest_delivery_still_works(client, admission, secret)

    def test_hpke_ciphertext_cannot_move_to_another_admission(self):
        client, first, first_secret = self.preflight()
        _, second, _ = self.preflight(client=client, movement_id="movement-2", idempotency_key="op-2")
        body = self.delivery(client, first, first_secret)
        moved = self.resign(client, body, lambda p: p.update(admission_id=second["admission_id"]))
        self.assert_rejected_unused(moved, 401, "delivery_decrypt_failed")
        self.assert_honest_delivery_still_works(client, first, first_secret)

    def test_hpke_wrong_recipient_key_rejected(self):
        client, admission, secret = self.preflight()
        info = client.delivery_seal(self.receiver_card(), admission, secret["sealed"]).info
        # Sealed to an attacker's X25519 key that copies the honest kid.
        to_rogue = DeliverySeal(self.w.rogue_enc["agent-b"], info, b"r" * 32)
        body = client.build_delivery(admission["admission_id"], secret["task"], secret["salt"], to_rogue)
        self.assert_rejected_unused(body, 401, "delivery_decrypt_failed")
        # Addressed to a key ID the receiver does not hold.
        other_kid = self.resign(client, self.delivery(client, admission, secret),
                                lambda p: p["enc"].update(kid="agent-c-enc"))
        self.assert_rejected_unused(other_kid, 401, "wrong_enc_key")
        self.assert_honest_delivery_still_works(client, admission, secret)

    def test_hpke_receiver_refuses_plaintext_delivery(self):
        client, admission, secret = self.preflight()
        plaintext = client.build_delivery(admission["admission_id"], secret["task"], secret["salt"])
        self.assertEqual(self.post(DELIVERY_PATH, plaintext)[0], 403)
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "plaintext_delivery_refused")
        self.assertEqual(self.w.receiver.ledger.effects(), [])
        self.assert_no_canary_anywhere(wire=False)

    def test_hpke_sealed_delivery_to_receiver_without_enc_key_rejected(self):
        plain_card = self.w.card("agent-b", self.w.b_url, ["word_count"], enc_key=None)
        store = SQLiteStore(Path(self.tmp.name) / "plain.sqlite")
        self.w.routes[B_URL] = plain = PeerReceiver(plain_card, self.w.keys["agent-b"], self.w.trust, store,
                                                    ["word_count"], clock=self.w.clock)
        client, admission, secret = self.preflight()
        self.assertEqual(self.post(DELIVERY_PATH, self.delivery(client, admission, secret))[0], 400)
        self.assertEqual(plain.ledger.traces()[-1]["reason"], "invalid_contract")
        self.assertEqual(plain.ledger.effects(), [])

    def test_hpke_client_never_downgrades(self):
        with mock.patch.object(peer_module, "hpke_available", return_value=False):
            self.assert_denied_before_disclosure("discovery", "encryption_unavailable")
        self.assertEqual(self.w.wire.paths(), [CARD_PATH])

    def test_hpke_client_can_require_confidentiality(self):
        plain_card = self.w.card("agent-b", self.w.b_url, ["word_count"], enc_key=None)
        self.w.routes[B_URL] = type("Plain", (), {"handle": staticmethod(lambda m, p, b: (200, plain_card))})()
        self._handoff_kw = {"client": self.w.client(require_confidentiality=True)}
        self.assert_denied_before_disclosure("discovery", "no_confidentiality_key")

    def test_hpke_tampered_encrypted_receipt_rejected_by_client(self):
        real = self.w.receiver

        class TamperingRelay:
            def handle(self, method, path, body):
                status, response = real.handle(method, path, body)
                if path == DELIVERY_PATH and status == 200:
                    response = {**response, "nonce": b64e(b"\x00" * 12)}
                return status, response

        self.w.routes[B_URL] = TamperingRelay()
        with self.assertRaises(HandoffAborted) as ctx:
            self.w.handoff()
        self.assertEqual((ctx.exception.stage, ctx.exception.reason), ("delivery", "unverified_receipt"))
        self.assertTrue(ctx.exception.payload_sent)

    def test_hpke_key_export_round_trip_and_redaction(self):
        key = self.w.enc["agent-b"]
        self.assertTrue(import_enc_key(key.export()).matches(key))
        self.assertTrue(import_enc_key(key.export(private=False)).matches(key))
        self.assertNotIn("private", key.export(private=False))
        self.assertNotIn(key.export()["private"], repr(key))
        mismatched = {**key.export(), "public": self.w.rogue_enc["agent-b"].public_value()}
        with self.assertRaises(ContractError):
            import_enc_key(mismatched)
        with self.assertRaises(TypeError):
            import_enc_key(key.export(private=False)).open(b"x" * 64, b"")


@unittest.skipUnless(hpke_available(), "optional [hpke] extra (cryptography) not installed")
class PeerAuthHpkeTests(SealedDeliveryCases, PeerAuthTests):
    """HS256 signatures + HPKE-sealed delivery: confidentiality is independent of the signature alg."""

    ENCRYPT = True


@unittest.skipUnless(ed25519_available() and hpke_available(),
                     "optional [ed25519,hpke] extras (cryptography) not installed")
class PeerAuthEd25519Tests(SealedDeliveryCases, PeerAuthTests):
    ALG = ED25519
    ENCRYPT = True

    def test_verifier_cannot_forge_peer_signature(self):
        # Asymmetric mode: holding agent-a's *verification* key does not allow signing as agent-a.
        public_only = self.w.keys["agent-a"].verifier()
        with self.assertRaises(TypeError):
            public_only.sign(b"x")
        self.assertEqual(self.w.trust.peer_keys, {})


class PeerHttpTests(unittest.TestCase):
    """Same protocol over a real loopback socket."""

    ENCRYPT = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_peer_server()
        url = f"http://127.0.0.1:{self.server.server_port}"
        self.w = World(HS256, self.tmp.name, b_url=url, encrypt=self.ENCRYPT)
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
        # Real socket bytes: plaintext mode exposes the text (no confidentiality); HPKE does not.
        self.assertEqual(TASK_CANARY.encode() in self.w.wire.transmitted(), not self.ENCRYPT)

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


@unittest.skipUnless(hpke_available(), "optional [hpke] extra (cryptography) not installed")
class PeerHttpHpkeTests(PeerHttpTests):
    ENCRYPT = True


@unittest.skipUnless(hpke_available(), "optional [hpke] extra (cryptography) not installed")
class Rfc9180KnownAnswerTests(unittest.TestCase):
    """The suite really is RFC 9180 DHKEM(X25519, HKDF-SHA256)/HKDF-SHA256/ChaCha20Poly1305.

    Vector: RFC 9180 Appendix A.2.1 (base mode), first encryption (sequence number 0, so the
    nonce is base_nonce, as in the single-shot API). The vector uses a non-empty aad, which
    the public single-shot API does not take, so this check calls cryptography's private
    ``_decrypt_with_aad`` helper and is skipped if that helper disappears. The protocol
    itself uses only the public ``Suite.encrypt``/``decrypt`` with ``info``.
    """

    SK_R = "8057991eef8f1f1af18f4a9491d16a1ce333f695d4db8e38da75975c4478e0fb"
    PK_R = "4310ee97d88cc1f088a5576c77ab0cf5c3ac797f3d95139c6c84b5429c59662a"
    INFO = "4f6465206f6e2061204772656369616e2055726e"
    ENC = "1afa08d3dec047a643885163f1180476fa7ddb54c6a8029ea33f95796bf2ac4a"
    AAD = "436f756e742d30"
    CT = "1c5250d8034ec2b784ba2cfd69dbdb8af406cfe3ff938e131f0def8c8b60b4db21993c62ce81883d2dd1b51a28"
    PT = "4265617574792069732074727574682c20747275746820626561757479"

    def test_rfc9180_a21_vector_opens_with_project_suite(self):
        from cryptography.hazmat.bindings._rust import openssl as rust_openssl

        from agent_movement.trust import _hpke_suite
        decrypt = getattr(rust_openssl.hpke, "_decrypt_with_aad", None)
        if decrypt is None:
            self.skipTest("cryptography no longer exposes _decrypt_with_aad")
        key = HpkeKey.from_private("kat", b64e(bytes.fromhex(self.SK_R)))
        self.assertEqual(key.public_value(), b64e(bytes.fromhex(self.PK_R)))
        plaintext = decrypt(_hpke_suite(), bytes.fromhex(self.ENC + self.CT), key._private,
                            info=bytes.fromhex(self.INFO), aad=bytes.fromhex(self.AAD))
        self.assertEqual(plaintext, bytes.fromhex(self.PT))

    def test_project_seal_and_open_round_trip(self):
        key = HpkeKey.generate("rt")
        sealed = import_enc_key(key.export(private=False)).seal(b"synthetic", b"info")  # public-only
        self.assertEqual(len(sealed), len(b"synthetic") + 48)
        self.assertEqual(key.open(sealed, b"info"), b"synthetic")


if __name__ == "__main__":
    unittest.main()
