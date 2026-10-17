"""Issue #29: per-sender idempotency keys, the store migration, and counted (single-use) grants.

Every key, grant and text below is synthetic and generated per test run. Concurrency is
exercised with threads (one SQLite connection each) and with separate OS processes.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_movement.core import (STORE_SCHEMA_VERSION, Approval, Conflict, HandoffReceiver,
                                 SQLiteStore, StoreSchemaError, canonical)
from agent_movement.peer import DELIVERY_PATH, PREFLIGHT_PATH, HandoffAborted, PeerClient, PeerLedger
from agent_movement.trust import (ED25519, HS256, ContractError, TrustDenied, TrustStore,
                                  ed25519_available, generate_key, hpke_available, issue_card,
                                  issue_grant, seal, verify_grant)
from test_core import fixture
from test_peer import TEXT, World

SRC = str(Path(__file__).resolve().parent.parent / "src")
# The exact PR #6 (store layout version 0) DDL, copied from core.py before issue #29.
LEGACY_DDL = """
    CREATE TABLE deliveries (idempotency_key TEXT PRIMARY KEY, movement_id TEXT NOT NULL UNIQUE,
                             envelope_digest TEXT NOT NULL, receipt_json TEXT NOT NULL);
    CREATE TABLE audit_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, movement_id TEXT NOT NULL,
                               task_id TEXT NOT NULL, event_type TEXT NOT NULL,
                               info_digest TEXT NOT NULL, event_time TEXT NOT NULL);
    CREATE TABLE owners (task_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, epoch INTEGER NOT NULL);
    CREATE TABLE effects (task_id TEXT NOT NULL, effect_id TEXT NOT NULL, payload_digest TEXT NOT NULL,
                          epoch INTEGER NOT NULL, PRIMARY KEY (task_id, effect_id));
"""


def envelope(origin="agent-a", movement="movement-1", key="op-1", approval="approval-a", text="one two three"):
    message = fixture()
    message.update(movement_id=movement)
    message["origin"]["agent_id"] = origin
    message["authority"]["approval_ref"] = approval
    message["execution"]["idempotency_key"] = key
    message["task"]["text"] = text
    return message


def run_children(code, argv_list, env_extra=None):
    """Start one interpreter per argv, release them together, return their stdout lines.

    Each child prints ``ready`` once set up, then waits for a go-file before the racing call.
    """
    with tempfile.TemporaryDirectory() as gate:
        go = Path(gate) / "go"
        env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [SRC, os.environ.get("PYTHONPATH")])),
               "PYTHONDONTWRITEBYTECODE": "1", **(env_extra or {})}
        children = [subprocess.Popen([sys.executable, "-c", code, str(go), *argv], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, env=env) for argv in argv_list]
        try:
            for child in children:
                assert child.stdout.readline().strip() == "ready", child.stderr.read()
            go.touch()
            results = []
            for child in children:
                out, err = child.communicate(timeout=60)
                if child.returncode != 0:
                    raise AssertionError(err)
                results.append(out.strip())
            return results
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.communicate()


# --------------------------------------------------------------------------- core store

class SenderScopedKeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.sqlite"
        approvals = [Approval("approval-a", "task-1", "agent-a", "agent-b", "word_count"),
                     Approval("approval-c", "task-1", "agent-c", "agent-b", "word_count")]
        self.receiver = HandoffReceiver("agent-b", SQLiteStore(self.path), approvals)

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_senders_with_the_same_key_both_succeed(self):
        a = envelope("agent-a", "movement-a", "op-1", "approval-a", "one two")
        c = envelope("agent-c", "movement-c", "op-1", "approval-c", "one two three four")
        first_a, first_c = self.receiver.receive(a), self.receiver.receive(c)
        self.assertEqual((first_a["replayed"], first_a["artifact"]["value"]), (False, 2))
        self.assertEqual((first_c["replayed"], first_c["artifact"]["value"]), (False, 4))
        # Each sender's retry replays its OWN receipt, not the other sender's.
        self.assertEqual(self.receiver.receive(a), {**first_a, "replayed": True})
        self.assertEqual(self.receiver.receive(c), {**first_c, "replayed": True})

    def test_same_sender_key_reuse_and_cross_sender_movement_reuse_still_conflict(self):
        self.receiver.receive(envelope("agent-a", "movement-a", "op-1", "approval-a"))
        with self.assertRaises(Conflict):  # same sender, same key, different envelope
            self.receiver.receive(envelope("agent-a", "movement-a2", "op-1", "approval-a"))
        with self.assertRaises(Conflict):  # movement IDs stay unique across senders
            self.receiver.receive(envelope("agent-c", "movement-a", "op-9", "approval-c"))

    def test_explicit_sender_scopes_the_key(self):
        store = self.receiver.store
        message = envelope("agent-a", "movement-x", "op-x", "approval-a")
        self.assertFalse(store.receive(message, sender="agent-a")["replayed"])
        self.assertTrue(store.receive(message, sender="agent-a")["replayed"])
        with self.assertRaises(Conflict):  # another sender's namespace: new key, same movement ID
            store.receive(message, sender="agent-z")
        with self.assertRaises(ContractError):
            store.receive(message, sender="not a valid id")


class StoreMigrationTests(unittest.TestCase):
    """A version-0 (PR #6) SQLite file is detected and migrated in place."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.legacy = self.root / "legacy.sqlite"
        self.approval = Approval("approval-a", "task-1", "agent-a", "agent-b", "word_count")
        # Real receipts, produced by the current code, then written in the legacy layout.
        scratch = HandoffReceiver("agent-b", SQLiteStore(self.root / "scratch.sqlite"), [self.approval])
        self.messages = [envelope(movement=f"movement-{i}", key=f"op-{i}") for i in range(3)]
        self.receipts = [scratch.receive(m) for m in self.messages]
        db = sqlite3.connect(self.legacy)
        db.executescript(LEGACY_DDL)
        for message, receipt in zip(self.messages, self.receipts):
            stored = {k: v for k, v in receipt.items() if k != "replayed"}
            db.execute("INSERT INTO deliveries VALUES(?,?,?,?)", (message["execution"]["idempotency_key"],
                       message["movement_id"], receipt["envelope_digest"], canonical(stored)))
        db.execute("INSERT INTO audit_events(movement_id,task_id,event_type,info_digest,event_time) "
                   "VALUES('movement-0','task-1','handoff.accepted','d','t')")
        db.execute("INSERT INTO owners VALUES('task-9','agent-a',3)")
        db.commit()
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def schema(self):
        db = sqlite3.connect(self.legacy)
        try:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            columns = [row[1] for row in db.execute("PRAGMA table_info(deliveries)")]
            pk = [row[1] for row in sorted(db.execute("PRAGMA table_info(deliveries)"), key=lambda r: r[5]) if row[5]]
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            rows = db.execute("SELECT sender_id, idempotency_key, movement_id FROM deliveries ORDER BY movement_id"
                              ).fetchall() if "sender_id" in columns else None
        finally:
            db.close()
        return version, columns, pk, tables, rows

    def test_legacy_file_is_migrated_in_place_and_keeps_replaying(self):
        self.assertEqual(self.schema()[0], 0)
        receiver = HandoffReceiver("agent-b", SQLiteStore(self.legacy), [self.approval])
        version, columns, pk, tables, rows = self.schema()
        self.assertEqual(version, STORE_SCHEMA_VERSION)
        self.assertEqual(columns[:2], ["sender_id", "idempotency_key"])
        self.assertEqual(pk, ["sender_id", "idempotency_key"])
        self.assertNotIn("deliveries_v1", tables)
        self.assertEqual(rows, [("agent-a", f"op-{i}", f"movement-{i}") for i in range(3)])
        for message, receipt in zip(self.messages, self.receipts):  # pre-migration retries replay
            self.assertEqual(receiver.receive(message), {**receipt, "replayed": True})
        # Other tables are untouched.
        self.assertEqual(len(receiver.store.audit()), 1)
        db = sqlite3.connect(self.legacy)
        self.assertEqual(db.execute("SELECT * FROM owners").fetchall(), [("task-9", "agent-a", 3)])
        db.close()
        # The point of the migration: another sender may now reuse a migrated key.
        receiver.approvals += (Approval("approval-c", "task-1", "agent-c", "agent-b", "word_count"),)
        other = receiver.receive(envelope("agent-c", "movement-c", "op-0", "approval-c"))
        self.assertFalse(other["replayed"])
        # Re-opening is a no-op.
        SQLiteStore(self.legacy)
        self.assertEqual(self.schema()[4][-1], ("agent-c", "op-0", "movement-c"))

    def test_concurrent_openers_migrate_exactly_once(self):
        code = ("import sys, time; from pathlib import Path\n"
                "from agent_movement.core import SQLiteStore\n"
                "print('ready', flush=True)\n"
                "while not Path(sys.argv[1]).exists(): time.sleep(0.002)\n"
                "SQLiteStore(sys.argv[2]); print('ok')\n")
        self.assertEqual(run_children(code, [[str(self.legacy)]] * 6), ["ok"] * 6)
        version, _, pk, tables, rows = self.schema()
        self.assertEqual((version, pk, len(rows)), (STORE_SCHEMA_VERSION, ["sender_id", "idempotency_key"], 3))
        self.assertNotIn("deliveries_v1", tables)

    def test_unmigratable_row_aborts_and_leaves_the_file_unchanged(self):
        db = sqlite3.connect(self.legacy)
        db.execute("INSERT INTO deliveries VALUES('op-bad','movement-bad','d','{\"status\":\"completed\"}')")
        db.commit()
        db.close()
        with self.assertRaises(StoreSchemaError):
            SQLiteStore(self.legacy)
        version, columns, *_ = self.schema()
        self.assertEqual((version, columns),
                         (0, ["idempotency_key", "movement_id", "envelope_digest", "receipt_json"]))

    def test_newer_schema_is_refused(self):
        db = sqlite3.connect(self.legacy)
        db.execute(f"PRAGMA user_version = {STORE_SCHEMA_VERSION + 1}")
        db.commit()
        db.close()
        with self.assertRaises(StoreSchemaError):
            SQLiteStore(self.legacy)

    def test_fresh_store_is_created_at_the_current_version(self):
        fresh = self.root / "fresh.sqlite"
        SQLiteStore(fresh)
        db = sqlite3.connect(fresh)
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], STORE_SCHEMA_VERSION)
        db.close()


# ------------------------------------------------------------------------- peer grants

class CountedGrantTests(unittest.TestCase):
    """Stdlib-only mode (HS256, plaintext delivery)."""

    ALG = HS256
    ENCRYPT = False

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(self.ALG, self.tmp.name, encrypt=self.ENCRYPT)
        self.ledger = self.w.receiver.ledger

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, body):
        status, raw = self.w.wire.request("POST", self.w.b_url, path, body)
        return status, json.loads(raw)

    def preflight(self, grant, movement="movement-1", key="op-1", client=None, **kw):
        client = client or self.w.client()
        body, secret = client.build_preflight(
            url=self.w.b_url, destination_id="agent-b", movement_id=movement, task_id="task-1",
            kind="word_count", text=TEXT, grant=grant, idempotency_key=key, trace_id="trace-1", **kw)
        return client, body, secret

    def deliver(self, client, admission, secret):
        card = PeerClient.discover(client, self.w.b_url, "agent-b", "word_count")
        sealed_to = client.delivery_seal(card, admission, secret["sealed"])
        status, body = self.post(DELIVERY_PATH, client.build_delivery(
            admission["admission_id"], secret["task"], secret["salt"], sealed_to))
        if status == 200 and sealed_to is not None:
            body = sealed_to.open_response(body)
        return status, body

    def reasons(self):
        return [t["reason"] for t in self.ledger.traces() if t["stage"] == "preflight"]

    def test_default_grant_is_single_use_and_signed(self):
        grant = self.w.grant()
        self.assertEqual(grant["payload"]["max_uses"], 1)
        self.assertEqual(self.w.handoff(grant=grant)["effect"], "committed")
        with self.assertRaises(HandoffAborted) as ctx:
            self.w.handoff(grant=grant, movement_id="movement-2", idempotency_key="op-2")
        # Denied at preflight, so the second task's text never left the sender.
        self.assertEqual((ctx.exception.stage, ctx.exception.status, ctx.exception.payload_sent),
                         ("preflight", 403, False))
        self.assertEqual(self.reasons(), ["admitted", "grant_uses_exhausted"])
        self.assertEqual([u["movement_id"] for u in self.ledger.grant_uses("grant-1")], ["movement-1"])
        self.assertEqual(len(self.ledger.effects()), 1)

    def test_max_uses_admits_exactly_that_many_movements(self):
        grant = self.w.grant(max_uses=2)
        for i in (1, 2):
            self.assertEqual(self.w.handoff(grant=grant, movement_id=f"movement-{i}",
                                            idempotency_key=f"op-{i}")["effect"], "committed")
        with self.assertRaises(HandoffAborted):
            self.w.handoff(grant=grant, movement_id="movement-3", idempotency_key="op-3")
        self.assertEqual([(u["use_number"], u["max_uses"]) for u in self.ledger.grant_uses()], [(1, 2), (2, 2)])

    def test_idempotent_retries_do_not_consume_uses(self):
        grant = self.w.grant()
        client, body, secret = self.preflight(grant)
        status, first = self.post(PREFLIGHT_PATH, body)
        self.assertEqual(status, 200)
        admission = first["payload"]
        self.assertEqual(self.deliver(client, admission, secret)[1]["payload"]["effect"], "committed")
        # 1. identical delivery retry
        self.assertEqual(self.deliver(client, admission, secret)[1]["payload"]["effect"], "replayed")
        # 2. preflight retry of the same movement (fresh nonce and salt, e.g. a lost admission reply)
        client, body, secret2 = self.preflight(grant, client=client)
        status, again = self.post(PREFLIGHT_PATH, body)
        self.assertEqual(status, 200)
        readmission = again["payload"]
        self.assertNotEqual(readmission["admission_id"], admission["admission_id"])
        status, receipt = self.deliver(client, readmission, secret2)
        self.assertEqual((status, receipt["payload"]["effect"]), (200, "replayed"))
        self.assertTrue(receipt["payload"]["receipt"]["replayed"])
        # The superseded admission is gone; the grant still holds exactly one use.
        self.assertEqual(self.deliver(client, admission, secret)[0], 403)
        self.assertEqual(self.reasons(), ["admitted", "readmitted"])
        self.assertEqual(len(self.ledger.grant_uses("grant-1")), 1)
        self.assertEqual(len(self.ledger.effects()), 1)
        # ... and it is still exhausted for any other movement.
        _, body, _ = self.preflight(grant, movement="movement-2", key="op-2")
        self.assertEqual(self.post(PREFLIGHT_PATH, body)[0], 403)

    def test_retry_with_a_different_binding_is_a_conflict_and_consumes_nothing(self):
        grant = self.w.grant(max_uses=3)
        self.assertEqual(self.post(PREFLIGHT_PATH, self.preflight(grant)[1])[0], 200)
        for changes in ({"key": "op-other"}, {"grant": self.w.grant(grant_id="grant-2")}):
            with self.subTest(changes=list(changes)):
                args = {"grant": grant, **changes}
                self.assertEqual(self.post(PREFLIGHT_PATH, self.preflight(**args)[1])[0], 409)
        self.assertEqual(self.reasons(), ["admitted", "conflict", "conflict"])
        self.assertEqual(len(self.ledger.grant_uses()), 1)

    def test_single_use_grant_admits_one_movement_under_thread_concurrency(self):
        grant = self.w.grant()
        retries = [self.preflight(grant)[1] for _ in range(8)]  # same movement, distinct nonces
        others = [self.preflight(grant, movement=f"movement-{i}", key=f"op-{i}")[1] for i in range(2, 10)]
        start = threading.Barrier(16)

        def send(body):
            start.wait()
            status, response = self.post(PREFLIGHT_PATH, body)
            return status, response.get("payload", {}).get("movement_id")

        with ThreadPoolExecutor(max_workers=16) as pool:
            outcomes = list(pool.map(send, [*retries, *others]))
        admitted = {movement for status, movement in outcomes if status == 200}
        self.assertEqual(len(admitted), 1, outcomes)
        self.assertTrue(all(status in (200, 403) for status, _ in outcomes), outcomes)
        winner = admitted.pop()
        # Retries of the winning movement are all re-admitted; nothing else is.
        self.assertEqual(sum(status == 200 for status, _ in outcomes), 8 if winner == "movement-1" else 1)
        uses = self.ledger.grant_uses("grant-1")
        self.assertEqual([(u["movement_id"], u["use_number"]) for u in uses], [(winner, 1)])

    def test_two_peer_senders_with_the_same_key_both_complete(self):
        a = self.w.handoff(grant=self.w.grant(grant_id="grant-a"), idempotency_key="op-shared")
        c_grant = self.w.grant(grant_id="grant-c", actor="agent-c")
        c = self.w.handoff(client=self.w.client("agent-c"), grant=c_grant, movement_id="movement-c",
                           idempotency_key="op-shared")
        self.assertEqual((a["effect"], c["effect"]), ("committed", "committed"))
        self.assertEqual((a["receipt"]["origin_agent_id"], c["receipt"]["origin_agent_id"]), ("agent-a", "agent-c"))

    def test_max_uses_is_validated_and_covered_by_the_signature(self):
        for bad in (0, -1, True, 1.0, "1", 1_000_001):
            with self.subTest(max_uses=bad), self.assertRaises(ContractError):
                self.w.grant(max_uses=bad)
        tampered = self.w.grant()
        tampered["payload"]["max_uses"] = 99
        with self.assertRaises(TrustDenied) as ctx:
            verify_grant(tampered, self.w.trust)
        self.assertEqual(ctx.exception.reason, "bad_grant_signature")
        resigned = seal("grant", {**self.w.grant()["payload"], "max_uses": 0}, self.w.users)
        with self.assertRaises(TrustDenied) as ctx:
            verify_grant(resigned, self.w.trust)
        self.assertEqual(ctx.exception.reason, "malformed_grant")

    def test_legacy_grant_without_max_uses_is_single_use(self):
        payload = {k: v for k, v in self.w.grant()["payload"].items() if k != "max_uses"}
        legacy = seal("grant", payload, self.w.users)
        self.assertEqual(verify_grant(legacy, self.w.trust)["max_uses"], 1)
        self.assertEqual(self.w.handoff(grant=legacy)["effect"], "committed")
        with self.assertRaises(HandoffAborted):
            self.w.handoff(grant=legacy, movement_id="movement-2", idempotency_key="op-2")

    def test_ledger_written_before_use_counting_is_backfilled(self):
        grant = self.w.grant()
        self.assertEqual(self.w.handoff(grant=grant)["effect"], "committed")
        db = sqlite3.connect(self.w.store.path)
        db.execute("DROP TABLE grant_uses")  # the pre-#29 ledger layout
        db.commit()
        db.close()
        ledger = PeerLedger(self.w.store)
        self.assertEqual([(u["grant_id"], u["movement_id"], u["use_number"]) for u in ledger.grant_uses()],
                         [("grant-1", "movement-1", 1)])
        with self.assertRaises(HandoffAborted):  # the upgrade handed the grant no extra use
            self.w.handoff(grant=grant, movement_id="movement-2", idempotency_key="op-2")


@unittest.skipUnless(ed25519_available() and hpke_available(),
                     "optional [ed25519,hpke] extras (cryptography) not installed")
class CountedGrantEd25519HpkeTests(CountedGrantTests):
    ALG = ED25519
    ENCRYPT = True


class CountedGrantProcessTests(unittest.TestCase):
    """Separate OS processes, each with its own receiver on one SQLite file, race one grant."""

    def test_single_use_grant_admits_one_movement_across_processes(self):
        now = int(time.time())
        ca, users = generate_key(HS256, "test-ca"), generate_key(HS256, "user-authority")
        keys = {n: generate_key(HS256, f"{n}-key") for n in ("agent-a", "agent-b")}
        trust = TrustStore.build([ca], [users], keys.values())
        window = {"not_before": now - 60, "expires_at": now + 600}
        cards = {n: issue_card(ca, agent_id=n, endpoint_url=f"local://{n}", capabilities=["word_count"],
                               agent_key=keys[n], **window) for n in keys}
        grant = issue_grant(users, grant_id="grant-proc", subject="user-synthetic-1", actor="agent-a",
                            audience="agent-b", task_id="task-1", capabilities=["word_count"], **window)
        client = PeerClient(cards["agent-a"], keys["agent-a"], trust, transport=None)
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "receiver.sqlite"
            config = Path(root) / "receiver.json"
            config.write_text(canonical({"card": cards["agent-b"], "key": keys["agent-b"].export(),
                                         "trust": trust.export(), "capabilities": ["word_count"],
                                         "db": str(db)}))
            SQLiteStore(db)  # created up front; the children race on admission, not on creation
            bodies = []
            for i in range(6):
                body, _ = client.build_preflight(
                    url="local://agent-b", destination_id="agent-b", movement_id=f"movement-{i}",
                    task_id="task-1", kind="word_count", text="synthetic words", grant=grant,
                    idempotency_key=f"op-{i}", trace_id=f"trace-{i}")
                path = Path(root) / f"preflight-{i}.json"
                path.write_bytes(body)
                bodies.append([str(config), str(path)])
            code = ("import sys, time; from pathlib import Path\n"
                    "from agent_movement.peer_http import load_receiver\n"
                    "receiver = load_receiver(Path(sys.argv[2])); body = Path(sys.argv[3]).read_bytes()\n"
                    "print('ready', flush=True)\n"
                    "while not Path(sys.argv[1]).exists(): time.sleep(0.002)\n"
                    "print(receiver.handle('POST', '/v0/preflight', body)[0])\n")
            statuses = run_children(code, bodies)
            self.assertEqual(sorted(statuses), ["200"] + ["403"] * 5, statuses)
            with sqlite3.connect(db) as conn:
                uses = conn.execute("SELECT use_number FROM grant_uses WHERE grant_id='grant-proc'").fetchall()
                admissions = conn.execute("SELECT COUNT(*) FROM peer_admissions").fetchone()[0]
            self.assertEqual((uses, admissions), ([(1,)], 1))


if __name__ == "__main__":
    unittest.main()
