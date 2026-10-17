"""Issue #39: keyed (salted) store commitments, the version 1 -> 2 migration and the TTL purge.

Every text, key and grant below is synthetic and generated per test run. "Raw bytes" means
every file SQLite keeps for the store (the database, its WAL and its shared-memory index),
read after the last connection closed.
"""

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from agent_movement import retention
from agent_movement.core import (RECEIPT_CONTENT_FIELDS, STORE_SCHEMA_VERSION, Approval, Conflict,
                                 EffectGateway, HandoffReceiver, PolicyDenied, SQLiteStore,
                                 StoreSchemaError, build_receipt, canonical, digest)
from agent_movement.peer import HandoffAborted, PeerLedger
from agent_movement.trust import HS256
from test_core import fixture
from test_grant_uses_and_sender_keys import run_children
from test_peer import TEXT, World

REPO = Path(__file__).resolve().parent.parent
LOW_ENTROPY = "yes"  # the guessable kind of text a plain SHA-256 would give away
# The issue #29 (store layout version 1) DDL, copied from core.py before issue #39.
V1_DDL = """
    CREATE TABLE deliveries (sender_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                             movement_id TEXT NOT NULL UNIQUE, envelope_digest TEXT NOT NULL,
                             receipt_json TEXT NOT NULL, PRIMARY KEY (sender_id, idempotency_key));
    CREATE TABLE audit_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, movement_id TEXT NOT NULL,
                               task_id TEXT NOT NULL, event_type TEXT NOT NULL,
                               info_digest TEXT NOT NULL, event_time TEXT NOT NULL);
    CREATE TABLE owners (task_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, epoch INTEGER NOT NULL);
    CREATE TABLE effects (task_id TEXT NOT NULL, effect_id TEXT NOT NULL, payload_digest TEXT NOT NULL,
                          epoch INTEGER NOT NULL, PRIMARY KEY (task_id, effect_id));
    CREATE TABLE authorized_effects (task_id TEXT NOT NULL, effect_id TEXT NOT NULL, grant_id TEXT NOT NULL,
                                     agent_id TEXT NOT NULL, payload_digest TEXT NOT NULL,
                                     log_seq INTEGER NOT NULL, PRIMARY KEY (task_id, effect_id));
    CREATE TABLE a2a_correlations (seq INTEGER PRIMARY KEY AUTOINCREMENT, a2a_task_id TEXT,
                                   a2a_context_id TEXT, a2a_message_id TEXT NOT NULL, movement_id TEXT,
                                   trace_id TEXT, outcome TEXT NOT NULL, envelope_digest TEXT,
                                   artifact_digest TEXT, event_time TEXT NOT NULL);
    PRAGMA user_version = 1;
"""
V1_TIME = "2026-01-02T03:04:05.123456+00:00"


def envelope(movement="movement-1", key="op-1", kind="word_count", text=LOW_ENTROPY, origin="agent-a"):
    message = fixture()
    message.update(movement_id=movement)
    message["origin"]["agent_id"] = origin
    message["execution"]["idempotency_key"] = key
    message["task"] = {"kind": kind, "text": text}
    return message


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def raw_bytes(path):
    path = Path(path)
    return b"".join(p.read_bytes() for p in sorted(path.parent.glob(path.name + "*")))


def plain_digests(message, effect_payloads=()):
    """Every plain SHA-256 a pre-#39 store would have written for this envelope."""
    receipt = build_receipt(message)
    values = {receipt["envelope_digest"], receipt["artifact_digest"], sha256_hex(message["task"]["text"])}
    values |= {sha256_hex(p) for p in effect_payloads}
    return values


class Receivers:
    def approvals(self, kind="word_count", origin="agent-a"):
        return [Approval("approval-1", "task-1", origin, "agent-b", kind)]


class KeyedCommitmentTests(unittest.TestCase, Receivers):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_unsalted_envelope_digest_is_stored(self):
        store = SQLiteStore(self.path)
        receiver = HandoffReceiver("agent-b", store, self.approvals("sha256"))
        message = envelope(kind="sha256")
        first = receiver.receive(message)
        self.assertEqual(receiver.receive(message), {**first, "replayed": True})
        denied = envelope("movement-2", "op-2", kind="word_count")  # not approved for word_count
        with self.assertRaises(PolicyDenied):
            receiver.receive(denied)
        gateway = EffectGateway(store)
        self.assertEqual(gateway.claim("task-1", "agent-b"), 1)
        self.assertTrue(gateway.commit("task-1", "agent-b", 1, "effect-1", LOW_ENTROPY))
        del store, receiver, gateway
        data = raw_bytes(self.path)
        forbidden = plain_digests(message, [LOW_ENTROPY]) | plain_digests(denied)
        for value in forbidden:
            self.assertNotIn(value.encode("ascii"), data)
        self.assertEqual(first["envelope_digest"], digest(message))  # the receipt itself is unchanged
        self.assertNotIn(canonical(message["task"]).encode("utf-8"), data)

    def test_equal_inputs_commit_equally_within_a_store_but_not_across_stores(self):
        a, b = SQLiteStore(self.path), SQLiteStore(Path(self.tmp.name) / "other.sqlite")
        again = SQLiteStore(self.path)
        message = envelope()
        self.assertEqual(a.fingerprint(message), again.fingerprint(message))
        self.assertNotEqual(a.fingerprint(message), b.fingerprint(message))
        self.assertNotEqual(a.fingerprint(message), digest(message))
        self.assertRegex(a.fingerprint(message), r"\A[0-9a-f]{64}\Z")
        self.assertNotEqual(a.fingerprint(message), a.fingerprint(envelope(text="no")))

    def test_replay_conflict_and_effect_replay_still_work(self):
        store = SQLiteStore(self.path)
        receiver = HandoffReceiver("agent-b", store, self.approvals())
        first = receiver.receive(envelope())
        self.assertEqual(SQLiteStore(self.path).receive(envelope()), {**first, "replayed": True})
        with self.assertRaises(Conflict):
            receiver.receive(envelope(text="something else"))
        gateway = EffectGateway(store)
        gateway.claim("task-1", "agent-b")
        self.assertTrue(gateway.commit("task-1", "agent-b", 1, "effect-1", "payload"))
        self.assertFalse(gateway.commit("task-1", "agent-b", 1, "effect-1", "payload"))
        with self.assertRaises(Conflict):
            gateway.commit("task-1", "agent-b", 1, "effect-1", "other payload")

    def test_secret_stays_outside_audit_export_and_stored_receipts(self):
        store = SQLiteStore(self.path)
        HandoffReceiver("agent-b", store, self.approvals()).receive(envelope())
        with sqlite3.connect(self.path) as db:
            key = db.execute("SELECT hmac_key FROM store_secret").fetchone()[0]
            receipt_json = db.execute("SELECT receipt_json FROM deliveries").fetchone()[0]
        db.close()
        self.assertEqual(len(key), 32)
        exported = canonical(store.audit())
        self.assertNotIn(key.hex(), exported)
        self.assertEqual(len(store.audit()), 2)
        self.assertFalse(set(RECEIPT_CONTENT_FIELDS) & set(json.loads(receipt_json)))

    def test_missing_secret_refuses_to_open(self):
        SQLiteStore(self.path)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM store_secret")
        db.close()
        with self.assertRaises(StoreSchemaError):
            SQLiteStore(self.path)


class CommitmentMigrationTests(unittest.TestCase, Receivers):
    """A version-1 (issue #29) file holding plain digests is migrated to keyed commitments."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "v1.sqlite"
        self.messages = [envelope(f"movement-{i}", f"op-{i}", kind="sha256", text=f"t{i}") for i in range(3)]
        self.receipts = [build_receipt(m) for m in self.messages]
        db = sqlite3.connect(self.path)
        db.executescript(V1_DDL)
        for message, receipt in zip(self.messages, self.receipts):
            db.execute("INSERT INTO deliveries VALUES(?,?,?,?,?)",
                       ("agent-a", message["execution"]["idempotency_key"], message["movement_id"],
                        receipt["envelope_digest"], canonical(receipt)))
            db.execute("INSERT INTO audit_events(movement_id,task_id,event_type,info_digest,event_time) "
                       "VALUES(?,?,?,?,?)", (message["movement_id"], "task-1", "handoff.accepted",
                                             receipt["envelope_digest"], V1_TIME))
            db.execute("INSERT INTO audit_events(movement_id,task_id,event_type,info_digest,event_time) "
                       "VALUES(?,?,?,?,?)", (message["movement_id"], "task-1", "handoff.completed",
                                             receipt["artifact_digest"], V1_TIME))
            db.execute("INSERT INTO a2a_correlations(a2a_message_id,movement_id,outcome,envelope_digest,"
                       "artifact_digest,event_time) VALUES(?,?,?,?,?,?)",
                       (f"m-{message['movement_id']}", message["movement_id"], "completed",
                        receipt["envelope_digest"], receipt["artifact_digest"], V1_TIME))
        db.execute("INSERT INTO owners VALUES('task-1','agent-b',2)")
        db.execute("INSERT INTO effects VALUES('task-1','effect-1',?,2)", (sha256_hex("payload-1"),))
        db.execute("INSERT INTO authorized_effects VALUES('task-1','movement-0.result','grant-1','agent-b',?,1)",
                   (sha256_hex("payload-2"),))
        db.commit()
        db.close()
        self.plain = set().union(*(plain_digests(m) for m in self.messages),
                                 {sha256_hex("payload-1"), sha256_hex("payload-2")})
        self.assertTrue(all(p.encode() in raw_bytes(self.path) for p in self.plain))

    def tearDown(self):
        self.tmp.cleanup()

    def test_v1_store_is_migrated_and_no_plain_digest_survives(self):
        store = SQLiteStore(self.path)
        receiver = HandoffReceiver("agent-b", store, self.approvals("sha256"))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], STORE_SCHEMA_VERSION)
            created = [r[0] for r in db.execute("SELECT created_at FROM deliveries ORDER BY movement_id")]
            effect = db.execute("SELECT payload_digest FROM authorized_effects").fetchone()[0]
            corr = db.execute("SELECT envelope_digest, artifact_digest FROM a2a_correlations "
                              "WHERE movement_id='movement-0'").fetchone()
        db.close()
        self.assertEqual(created, [V1_TIME] * 3)  # backfilled from the movement's first audit event
        self.assertEqual(effect, store.keyed_digest(sha256_hex("payload-2")))
        self.assertEqual(corr, (store.fingerprint(self.messages[0]),
                                store.keyed_digest(self.receipts[0]["artifact_digest"])))
        # Pre-migration retries still replay, with the identical (plain-digest) receipt.
        for message, receipt in zip(self.messages, self.receipts):
            self.assertEqual(receiver.receive(message), {**receipt, "replayed": True})
        with self.assertRaises(Conflict):
            receiver.receive(envelope("movement-0", "op-0", kind="sha256", text="changed"))
        # The fenced effect ledger keeps detecting replays and payload conflicts.
        gateway = EffectGateway(store)
        self.assertFalse(gateway.commit("task-1", "agent-b", 2, "effect-1", "payload-1"))
        with self.assertRaises(Conflict):
            gateway.commit("task-1", "agent-b", 2, "effect-1", "payload-x")
        completed = [e for e in store.audit() if e["event_type"] == "handoff.completed"]
        self.assertEqual(completed[0]["info_digest"], store.keyed_digest(self.receipts[0]["artifact_digest"]))
        del store, receiver, gateway
        data = raw_bytes(self.path)
        for value in self.plain:
            self.assertNotIn(value.encode("ascii"), data)

    def test_concurrent_openers_wrap_exactly_once(self):
        code = ("import sys, time; from pathlib import Path\n"
                "from agent_movement.core import SQLiteStore\n"
                "print('ready', flush=True)\n"
                "while not Path(sys.argv[1]).exists(): time.sleep(0.002)\n"
                "SQLiteStore(sys.argv[2]); print('ok')\n")
        self.assertEqual(run_children(code, [[str(self.path)]] * 6), ["ok"] * 6)
        receiver = HandoffReceiver("agent-b", SQLiteStore(self.path), self.approvals("sha256"))
        for message, receipt in zip(self.messages, self.receipts):  # a double wrap would conflict
            self.assertEqual(receiver.receive(message), {**receipt, "replayed": True})

    def test_unreadable_receipt_aborts_and_leaves_the_file_unchanged(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE deliveries SET receipt_json='not json' WHERE movement_id='movement-1'")
        db.close()
        with self.assertRaises(StoreSchemaError):
            SQLiteStore(self.path)
        with sqlite3.connect(self.path) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            digests = {r[0] for r in db.execute("SELECT info_digest FROM audit_events")}
        db.close()
        self.assertEqual(version, 1)
        self.assertNotIn("store_secret", tables)
        self.assertTrue(digests <= self.plain)


DAY = 86400


class PurgeTests(unittest.TestCase, Receivers):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.sqlite"
        self.store = SQLiteStore(self.path)
        self.receiver = HandoffReceiver("agent-b", self.store, self.approvals())
        self.first = self.receiver.receive(envelope())
        self.gateway = EffectGateway(self.store)
        self.gateway.claim("task-1", "agent-a")
        self.gateway.commit("task-1", "agent-a", 1, "effect-1", "payload")
        self.assertEqual(self.gateway.transfer("task-1", "agent-a", 1, "agent-b"), 2)

    def tearDown(self):
        self.tmp.cleanup()

    def counts(self):
        with sqlite3.connect(self.path) as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                              "AND name NOT LIKE 'sqlite_%'")]
            counts = {n: db.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0] for n in names}
        db.close()
        return counts

    def test_purge_removes_old_history_and_keeps_fencing_rows(self):
        before = self.counts()
        self.assertEqual((before["deliveries"], before["audit_events"]), (1, 2))
        report = retention.purge(self.path, DAY, now=time.time() + 2 * DAY)
        self.assertEqual((report["tables"]["deliveries"]["rows"], report["tables"]["audit_events"]["rows"]), (1, 2))
        for table in ("owners", "effects", "store_secret"):
            self.assertEqual(report["tables"][table]["action"], "retained")
        after = self.counts()
        self.assertEqual((after["deliveries"], after["audit_events"]), (0, 0))
        self.assertEqual((after["owners"], after["effects"], after["store_secret"]), (1, 1, 1))
        # Fencing still holds: the stale owner is refused, the current one replays its effect.
        with self.assertRaises(PolicyDenied):
            self.gateway.commit("task-1", "agent-a", 1, "effect-2", "payload")
        self.assertFalse(self.gateway.commit("task-1", "agent-b", 2, "effect-1", "payload"))
        self.assertEqual(self.gateway.reconcile("task-1", "effect-1"), "committed")
        # The retry window ended with the delivery row: the same envelope executes again.
        self.assertFalse(self.receiver.receive(envelope())["replayed"])

    def test_recent_rows_survive(self):
        report = retention.purge(self.path, DAY)
        self.assertEqual(report["deleted_rows"], 0)
        self.assertTrue(self.receiver.receive(envelope())["replayed"])

    def test_purge_is_audited_and_dry_run_changes_nothing(self):
        later = time.time() + 2 * DAY
        dry = retention.purge(self.path, DAY, now=later, dry_run=True)
        self.assertEqual((dry["deleted_rows"], dry["purge_seq"]), (3, None))
        self.assertEqual(self.counts()["audit_events"], 2)
        self.assertEqual(retention.purge_log(self.path), [])
        done = retention.purge(self.path, DAY, now=later, retain={"audit_events": None})
        self.assertEqual(self.counts()["audit_events"], 2)
        log = retention.purge_log(self.path)
        self.assertEqual(len(log), 1)
        self.assertEqual((log[0]["seq"], log[0]["older_than_s"]), (done["purge_seq"], DAY))
        self.assertEqual(log[0]["deleted"], {"deliveries": 1})
        self.assertEqual(log[0]["policy"], {"audit_events": None, "deliveries": DAY})
        self.assertEqual(done["tables"]["retention_purges"]["action"], "retained")

    def test_retention_override_validation(self):
        with self.assertRaises(ValueError):
            retention.purge(self.path, DAY, retain={"owners": DAY})
        with self.assertRaises(ValueError):
            retention.purge(self.path, -1)
        with self.assertRaises(FileNotFoundError):
            retention.purge(Path(self.tmp.name) / "missing.sqlite", DAY)
        self.assertFalse((Path(self.tmp.name) / "missing.sqlite").exists())
        self.assertEqual(retention.parse_duration("30d"), 30 * DAY)
        for bad in ("30", "1y", "-1d", "d", ""):
            with self.assertRaises(ValueError):
                retention.parse_duration(bad)

    def test_purged_rows_are_physically_erased(self):
        movement = "movement-erase-0123456789"
        self.receiver.receive(envelope(movement, "op-erase"))
        del self.receiver, self.gateway
        self.store = None
        self.assertIn(movement.encode(), raw_bytes(self.path))
        report = retention.purge(self.path, 0, now=time.time() + 1)
        self.assertFalse(report["wal_checkpoint"]["busy"])
        self.assertNotIn(movement.encode(), raw_bytes(self.path))

    def test_unmanaged_and_relocation_tables_are_left_alone(self):
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE someone_elses (x)")
            db.execute("INSERT INTO someone_elses VALUES (1)")
            db.execute("CREATE TABLE relocations (movement_id TEXT)")
            # An unresolved parked effect (issue #30) must survive any purge.
            db.execute("CREATE TABLE effect_reconciliations (task_id TEXT, effect_id TEXT, status TEXT)")
            db.execute("INSERT INTO effect_reconciliations VALUES ('task-1', 'effect-9', 'parked')")
            db.execute("CREATE TABLE reconciliation_events (seq INTEGER PRIMARY KEY, event_time TEXT)")
            db.execute("INSERT INTO reconciliation_events(event_time) VALUES ('2020-01-01T00:00:00+00:00')")
        db.close()
        report = retention.purge(self.path, 0, now=time.time() + 1)
        self.assertEqual(report["tables"]["someone_elses"]["action"], "unmanaged")
        for table in ("relocations", "effect_reconciliations", "reconciliation_events"):
            self.assertEqual(report["tables"][table]["action"], "retained")
        counts = self.counts()
        self.assertEqual((counts["someone_elses"], counts["effect_reconciliations"],
                          counts["reconciliation_events"]), (1, 1, 1))

    @unittest.skipUnless(importlib.util.find_spec("langgraph"), "needs the optional 'relocation' extra")
    def test_policy_covers_every_relocation_table(self):
        from agent_movement import relocation
        tables = set()
        for name, init in (("single.sqlite", relocation.init_store), ("authority.sqlite", relocation.init_authority),
                           ("worker.sqlite", relocation.init_worker_store)):
            path = Path(self.tmp.name) / name
            init(path)
            with sqlite3.connect(path) as db:
                tables |= {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                                    "AND name NOT LIKE 'sqlite_%'")}
            db.close()
            report = retention.purge(path, 0, now=time.time() + 1)
            self.assertFalse([t for t, r in report["tables"].items() if r["action"] == "unmanaged"], name)
        self.assertIn("effect_reconciliations", tables)
        self.assertEqual(tables - set(retention.POLICY), set())

    def test_policy_covers_every_store_table_and_the_doc_names_them(self):
        doc = (REPO / "docs" / "data-retention.md").read_text(encoding="utf-8")
        for table in retention.POLICY:
            self.assertIn(f"`{table}`", doc, table)
        world_root = Path(self.tmp.name) / "peer"
        world_root.mkdir()
        world = World(HS256, world_root)
        world.handoff()
        with sqlite3.connect(world.store.path) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' "
                                               "AND name NOT LIKE 'sqlite_%'")}
        db.close()
        self.assertEqual(tables - set(retention.POLICY), set())

    def test_cli_purge_end_to_end(self):
        env = {"PYTHONPATH": str(REPO / "src"), "PATH": ""}
        done = subprocess.run([sys.executable, "-m", "agent_movement", "purge", "--db", str(self.path),
                               "--older-than", "0s", "--retain", "audit_events=forever"],
                              capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(report["tables"]["audit_events"]["action"], "retained")
        self.assertIsInstance(report["purge_seq"], int)
        missing = subprocess.run([sys.executable, "-m", "agent_movement", "purge", "--db",
                                  str(Path(self.tmp.name) / "nope.sqlite"), "--older-than", "1d"],
                                 capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(missing.returncode, 2)
        bad = subprocess.run([sys.executable, "-m", "agent_movement", "purge", "--db", str(self.path),
                              "--older-than", "1d", "--retain", "owners=1d"],
                             capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("not configurable", bad.stderr)


class PeerPurgeTests(unittest.TestCase):
    """Peer tables: in-flight admissions and live grants are kept; revocations and effects stay."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = World(HS256, self.tmp.name)
        self.t = self.w.clock.t
        self.receipt = self.w.handoff()  # single-use grant-1, expires t+600; admission expires t+60
        self.ledger = PeerLedger(self.w.store)

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, table):
        with sqlite3.connect(self.w.store.path) as db:
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        db.close()
        return count

    def test_in_flight_admission_and_live_grant_are_kept(self):
        for now in (self.t + 30, self.t + 300):  # admission live; then admission expired, grant live
            report = retention.purge(self.w.store.path, 0, now=now)
            self.assertEqual(report["tables"]["peer_admissions"]["rows"], 0)
            self.assertEqual((self.rows("peer_admissions"), self.rows("grant_uses")), (1, 1))
        # The single-use grant is still spent: purging never hands a live grant its uses back.
        with self.assertRaises(HandoffAborted) as caught:
            self.w.handoff(movement_id="movement-2", idempotency_key="op-2")
        self.assertEqual((caught.exception.stage, caught.exception.payload_sent), ("preflight", False))
        self.assertEqual(self.w.receiver.ledger.traces()[-1]["reason"], "grant_uses_exhausted")

    def test_expired_admission_and_grant_go_together_and_authority_state_stays(self):
        self.assertTrue(self.ledger.revoke("grant-other", self.t))
        report = retention.purge(self.w.store.path, 0, now=self.t + 1000)
        self.assertEqual((report["tables"]["peer_admissions"]["rows"], report["tables"]["grant_uses"]["rows"]),
                         (1, 1))
        self.assertEqual((self.rows("peer_admissions"), self.rows("grant_uses")), (0, 0))
        self.assertEqual((self.rows("grant_revocations"), self.rows("authorized_effects")), (1, 1))
        self.assertEqual(self.rows("authority_log"), 0)  # history; enforcement reads the state tables
        self.assertEqual(self.rows("peer_trace"), 0)
        self.assertFalse(self.ledger.revoke("grant-other", self.t + 1000))  # revocation still effective
        self.assertEqual(self.rows("peer_nonces"), 1)  # inside the nonce floor

    def test_nonces_are_kept_inside_the_floor_and_purged_after_it(self):
        retention.purge(self.w.store.path, 0, now=self.t + retention.NONCE_FLOOR_S - 1)
        self.assertEqual(self.rows("peer_nonces"), 1)
        retention.purge(self.w.store.path, 0, now=self.t + retention.NONCE_FLOOR_S + 1)
        self.assertEqual(self.rows("peer_nonces"), 0)

    def test_peer_effect_digest_is_keyed(self):
        self.assertEqual(self.receipt["effect"], "committed")
        artifact = self.receipt["receipt"]["artifact"]
        plain = sha256_hex(canonical(artifact))
        with sqlite3.connect(self.w.store.path) as db:
            stored = db.execute("SELECT payload_digest FROM authorized_effects").fetchone()[0]
        db.close()
        self.assertEqual(stored, self.w.store.keyed_digest(plain))
        self.assertNotIn(plain.encode(), raw_bytes(self.w.store.path))
        self.assertNotIn(TEXT.encode(), raw_bytes(self.w.store.path))


if __name__ == "__main__":
    unittest.main()
