"""Time-to-live purge for agent-movement SQLite stores (issue #39).

``purge`` deletes history older than a retention period from one store file and records
what it deleted in ``retention_purges``. It never deletes the rows that keep the system
safe: task owners and epochs (fencing), effect ledgers (exactly-once replay detection),
grant revocations, admissions or grant-use counts whose grant could still be presented,
replay nonces inside the clock-skew window, the store secret, and every relocation or
checkpoint table (they carry no timestamps and hold ownership or resume state).

Each table the store can hold has exactly one rule in :data:`POLICY`; docs/data-retention.md
explains each rule and how to delete what ``purge`` keeps. Tables this module does not know
are reported as ``unmanaged`` and left alone.

Deletion is physical, not only logical: the purge connection runs with
``PRAGMA secure_delete = ON`` (freed content is overwritten with zeros) and ends with
``PRAGMA wal_checkpoint(TRUNCATE)``, so purged rows do not linger in free pages or in the
write-ahead log. Standard library only. Synthetic, local experiment -- not production.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .core import SQLiteStore, StoreSchemaError, canonical

PURGE_LOG = "retention_purges"
_PURGE_LOG_DDL = f"""CREATE TABLE IF NOT EXISTS {PURGE_LOG} (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    older_than_s INTEGER NOT NULL,
    policy_json TEXT NOT NULL,
    deleted_json TEXT NOT NULL)"""
# Replay nonces younger than this are never purged, whatever the retention period. A
# receiver refuses preflights issued more than max_clock_skew (default 120 s) away from its
# clock and already drops nonces older than twice that itself; one hour leaves a wide margin.
NONCE_FLOOR_S = 3600
_DURATION = re.compile(r"(\d{1,9})([smhdw])\Z")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
FOREVER = "forever"


@dataclass(frozen=True)
class Rule:
    """How ``purge`` treats one table. ``column`` is the age column of a purged table."""

    action: str  # "purged" or "retained"
    reason: str
    column: str | None = None
    clock: str | None = None  # "iso" (ISO-8601 UTC text) or "epoch" (integer seconds)


def _purged(column: str, clock: str, reason: str) -> Rule:
    return Rule("purged", reason, column, clock)


def _retained(reason: str) -> Rule:
    return Rule("retained", reason)


_RELOCATION = ("relocation/checkpoint state: no timestamp column, and it holds ownership, "
               "fencing or resume state; delete a finished run's files instead")
POLICY: dict[str, Rule] = {
    # -- purged by age ------------------------------------------------------------------
    "audit_events": _purged("event_time", "iso", "handoff audit history (IDs and keyed commitments)"),
    "deliveries": _purged("created_at", "iso", "idempotency memo: an exact retry replays only while "
                          "its delivery row is retained, so the retention period is the retry window"),
    "a2a_correlations": _purged("event_time", "iso", "A2A task/message correlation history"),
    "peer_trace": _purged("at", "iso", "sanitized peer receiver trace"),
    "authority_log": _purged("at", "epoch", "grant revocation and effect authorization history; "
                             "enforcement reads grant_revocations and authorized_effects, not this log"),
    "peer_nonces": _purged("seen_at", "epoch", "preflight replay nonces; never inside the last "
                           f"{NONCE_FLOOR_S} s, whatever the retention period"),
    "peer_admissions": _purged("expires_at", "epoch", "preflight admissions; only once both the "
                               "admission and its grant expired before the cutoff (no in-flight delivery "
                               "and no live grant depends on it), together with its grant_uses row"),
    "grant_uses": Rule("purged", "single-use / counted grant uses; deleted only with their admission "
                       "(see peer_admissions), so a live grant never regains uses", "at", "epoch"),
    # -- retained ---------------------------------------------------------------------------
    "owners": _retained("fencing: current owner and epoch per task; deleting a row would let a "
                        "stale executor claim the task again at epoch 1"),
    "effects": _retained("fenced effect ledger: exactly-once replay detection and reconcile()"),
    "authorized_effects": _retained("peer effect ledger: exactly-once replay detection"),
    "grant_revocations": _retained("a revocation must outlive its grant, whose expiry this file "
                                   "does not always know"),
    "store_secret": _retained("key of the keyed commitments; deleting it makes the store unusable"),
    PURGE_LOG: _retained("the audit of purges (counts and policy only)"),
    # Operator reconciliation (issue #30), in the relocation coordinator file.
    "effect_reconciliations": _retained("parked unknown-outcome effects and their final operator "
                                        "decisions; an unresolved one must never disappear, and a "
                                        "decided one keeps the effect from being settled twice"),
    "reconciliation_events": _retained("append-only audit of operator reconciliation decisions, "
                                       "kept with the decisions it explains"),
    **{name: _retained(_RELOCATION) for name in (
        "relocations", "opaque_effects", "effect_intents", "node_runs", "bundle_imports",
        "checkpoints", "writes")},
}
# Tables with a configurable period. grant_uses has none of its own: it follows peer_admissions.
PURGEABLE = tuple(name for name, rule in POLICY.items() if rule.action == "purged" and name != "grant_uses")


def parse_duration(text: str) -> int:
    """``<n><unit>`` with unit s, m, h, d or w -> seconds (``30d`` -> 2592000)."""
    match = _DURATION.fullmatch(text.strip()) if isinstance(text, str) else None
    if match is None:
        raise ValueError(f"invalid duration {text!r}: use <number><unit>, unit one of s, m, h, d, w (e.g. 30d)")
    return int(match.group(1)) * _UNITS[match.group(2)]


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _tables(db: sqlite3.Connection) -> list[str]:
    return sorted(row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))


def _age_condition(rule: Rule, now: float, older_than: int) -> tuple[str, Any]:
    cutoff = now - older_than
    if rule.clock == "iso":
        # julianday() parses ISO-8601 with a UTC offset; unparseable text gives NULL, so a
        # row with a malformed timestamp is kept rather than guessed about.
        return f"julianday({rule.column}) < julianday(?)", _iso(cutoff)
    return f"{rule.column} < ?", int(cutoff)


def _purge_admissions(db: sqlite3.Connection, cutoff: int, tables: list[str], dry_run: bool) -> dict[str, int]:
    """Admissions whose admission AND grant expired before ``cutoff``, plus their grant uses."""
    victims = []
    for movement_id, raw in db.execute("SELECT movement_id, record_json FROM peer_admissions "
                                       "WHERE expires_at < ?", (cutoff,)).fetchall():
        try:
            payload = json.loads(raw)["grant"]["payload"]
            grant_id, grant_expires = payload["grant_id"], payload["expires_at"]
        except (ValueError, KeyError, TypeError):
            continue  # unreadable record: keep it
        if type(grant_expires) is int and grant_expires < cutoff:
            victims.append((movement_id, grant_id))
    uses = 0
    for movement_id, grant_id in victims:
        if "grant_uses" in tables:
            uses += db.execute("SELECT COUNT(*) FROM grant_uses WHERE grant_id=? AND movement_id=?",
                               (grant_id, movement_id)).fetchone()[0]
        if not dry_run:
            db.execute("DELETE FROM peer_admissions WHERE movement_id=?", (movement_id,))
            if "grant_uses" in tables:
                db.execute("DELETE FROM grant_uses WHERE grant_id=? AND movement_id=?", (grant_id, movement_id))
    counts = {"peer_admissions": len(victims)}
    if "grant_uses" in tables:
        counts["grant_uses"] = uses
    return counts


def purge(path: str | Path, older_than: int, *, retain: Mapping[str, int | None] | None = None,
          now: float | None = None, dry_run: bool = False, nonce_floor: int = NONCE_FLOOR_S) -> dict[str, Any]:
    """Delete rows older than ``older_than`` seconds from the store at ``path``.

    ``retain`` overrides the period per purgeable table (``None`` keeps that table whole).
    ``now`` (epoch seconds) defaults to the wall clock. A dry run counts without deleting
    and records nothing. A core store is opened through :class:`SQLiteStore` first, so an
    older layout is migrated (salted) before anything is deleted. All deletions and the
    ``retention_purges`` record commit in one transaction.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"no store file at {path}")
    retain = dict(retain or {})
    for table, period in retain.items():
        if table not in PURGEABLE:
            raise ValueError(f"{table!r} has no configurable retention; configurable tables: "
                             + ", ".join(PURGEABLE))
        if period is not None and (type(period) is not int or period < 0):
            raise ValueError(f"invalid retention period for {table!r}")
    if type(older_than) is not int or older_than < 0:
        raise ValueError("older_than must be a non-negative number of seconds")
    now = time.time() if now is None else float(now)
    with closing(sqlite3.connect(str(path), timeout=10)) as probe:
        core = bool({"deliveries", "audit_events"} & set(_tables(probe)))
    if core:
        SQLiteStore(path)  # migrate an older layout (plain digests) before purging

    db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    try:
        db.execute("PRAGMA busy_timeout = 10000")
        db.execute("PRAGMA secure_delete = ON")
        db.execute("BEGIN IMMEDIATE")
        tables = _tables(db)
        report: dict[str, dict[str, Any]] = {}
        deleted: dict[str, int] = {}
        periods: dict[str, int | None] = {}
        for table in tables:
            rule = POLICY.get(table)
            if rule is None:
                report[table] = {"action": "unmanaged", "reason": "not covered by the retention policy"}
                continue
            if rule.action == "retained":
                report[table] = {"action": "retained", "reason": rule.reason}
        for table in PURGEABLE:
            if table not in tables:
                continue
            period = retain.get(table, older_than)
            periods[table] = period
            if period is None:
                report[table] = {"action": "retained", "reason": "kept whole by a --retain override"}
                continue
            rule = POLICY[table]
            if table == "peer_admissions":
                counts = _purge_admissions(db, int(now - period), tables, dry_run)
                for name, count in counts.items():
                    deleted[name] = count
                    report[name] = {"action": "purged", "rows": count, "older_than_s": period,
                                    "cutoff": _iso(now - period), "reason": POLICY[name].reason}
                continue
            condition, cutoff = _age_condition(rule, now, period)
            if table == "peer_nonces":
                condition += " AND seen_at < ?"
                params: tuple[Any, ...] = (cutoff, int(now - nonce_floor))
            else:
                params = (cutoff,)
            count = db.execute(f"SELECT COUNT(*) FROM {table} WHERE {condition}", params).fetchone()[0]
            if not dry_run and count:
                db.execute(f"DELETE FROM {table} WHERE {condition}", params)
            deleted[table] = count
            report[table] = {"action": "purged", "rows": count, "older_than_s": period,
                             "cutoff": _iso(now - period), "reason": rule.reason}
        if "grant_uses" in tables and "peer_admissions" not in tables:
            report["grant_uses"] = {"action": "retained", "reason": "no admissions to purge it with"}
        seq = None
        if not dry_run:
            db.execute(_PURGE_LOG_DDL)
            seq = db.execute(f"INSERT INTO {PURGE_LOG}(at,older_than_s,policy_json,deleted_json) "
                             "VALUES(?,?,?,?)", (_iso(now), older_than, canonical(periods),
                                                 canonical(deleted))).lastrowid
            report.setdefault(PURGE_LOG, {"action": "retained", "reason": POLICY[PURGE_LOG].reason})
        db.commit()
        checkpoint = None
        if not dry_run:
            busy, log, done = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            checkpoint = {"busy": bool(busy), "wal_frames": log, "checkpointed": done}
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()
    return {"store": str(path), "now": _iso(now), "older_than_s": older_than, "dry_run": dry_run,
            "purge_seq": seq, "deleted_rows": sum(deleted.values()), "wal_checkpoint": checkpoint,
            "tables": dict(sorted(report.items()))}


def purge_log(path: str | Path) -> list[dict[str, Any]]:
    """The recorded purges of a store, oldest first (empty if it was never purged)."""
    with closing(sqlite3.connect(str(path), timeout=10)) as db:
        if PURGE_LOG not in _tables(db):
            return []
        rows = db.execute(f"SELECT seq, at, older_than_s, policy_json, deleted_json FROM {PURGE_LOG} "
                          "ORDER BY seq").fetchall()
    return [{"seq": seq, "at": at, "older_than_s": older_than, "policy": json.loads(policy),
             "deleted": json.loads(deleted_rows)} for seq, at, older_than, policy, deleted_rows in rows]


def _retain_arg(text: str) -> tuple[str, int | None]:
    table, sep, value = text.partition("=")
    if not sep or not table:
        raise argparse.ArgumentTypeError("use TABLE=DURATION or TABLE=forever")
    if table not in PURGEABLE:
        raise argparse.ArgumentTypeError(f"{table!r} is not configurable; choose from: " + ", ".join(PURGEABLE))
    if value == FOREVER:
        return table, None
    try:
        return table, parse_duration(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _duration_arg(text: str) -> int:
    try:
        return parse_duration(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete store rows older than a retention period and record the purge in "
                    f"{PURGE_LOG}. Never deletes fencing state (owners/epochs), effect ledgers, grant "
                    "revocations, admissions or grant uses of a grant that could still be presented, "
                    "or relocation/checkpoint tables. Prints a JSON report. See docs/data-retention.md.",
        epilog="Exit codes: 0 purged (or counted, with --dry-run); 1 the store could not be used; "
               "2 usage error or no such store file.")
    parser.add_argument("--db", required=True, type=Path, help="SQLite store file to purge (never created)")
    parser.add_argument("--older-than", required=True, type=_duration_arg, metavar="DURATION",
                        help="default retention period for every purgeable table, as <number><unit> "
                             "with unit s, m, h, d or w (e.g. 30d)")
    parser.add_argument("--retain", action="append", default=[], type=_retain_arg, metavar="TABLE=DURATION",
                        help="override the period for one table (repeatable); TABLE=forever keeps it whole. "
                             "Tables: " + ", ".join(PURGEABLE))
    parser.add_argument("--dry-run", action="store_true", help="count the rows that would go; delete nothing")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else list(argv))
    try:
        report = purge(args.db, args.older_than, retain=dict(args.retain), dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(f"purge: {exc}", file=sys.stderr)
        return 2
    except (StoreSchemaError, sqlite3.DatabaseError) as exc:
        print(f"purge: cannot use {args.db}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
