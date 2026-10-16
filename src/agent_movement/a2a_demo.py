"""Repeatable A2A v1 delegation demo: two independent OS processes plus audit join.

Run ``python -m agent_movement.a2a_demo`` after ``pip install -e '.[a2a]'``.

1. Starts the destination worker (``agent_movement.a2a_server``) as one process.
2. Fetches its Agent Card over plain HTTP (no SDK) as a wire-level smoke check.
3. Runs the origin client (``agent_movement.a2a_client``) as separate processes:
   a completed delegation (JSON-RPC, streaming), an exact retry (HTTP+JSON,
   blocking) that is answered from the receiver's idempotency ledger, a denied
   approval (task REJECTED), a request through the deprecated URN alias with a
   client-supplied contextId (profile 0.1 behaviour, still accepted), and three
   requests the A2A server refuses before any task exists: an unadvertised
   capability, an unknown schema version, and a client-supplied contextId under
   the current profile URI (this server keeps the default: server-generated).
4. Joins client-side A2A task IDs with the receiver-side audit tables.

This proves DELEGATION of one allowlisted pure task, NOT agent migration.
Authentication is absent/experimental. Synthetic data, loopback only.
This orchestrator itself uses only the standard library.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from .a2a_profile import EXTENSION_URI, LEGACY_EXTENSION_URI
from .core import SCHEMA_VERSION

EXTRA_HINT = "optional A2A extra not installed; run: python -m pip install -e '.[a2a]'"


def demo_envelope(**changes: Any) -> dict[str, Any]:
    envelope = {
        "schema_version": SCHEMA_VERSION, "movement_id": "a2a-demo-movement",
        "logical_task_id": "demo-task", "operation": "delegate",
        "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
        "task": {"kind": "word_count", "text": "synthetic agent movement test task"},
        "context": {"classification": "synthetic"},
        "authority": {"approval_ref": "demo-approval"},
        "execution": {"idempotency_key": "a2a-demo-operation"},
        "observability": {"trace_id": "a2a-demo-trace"},
    }
    envelope.update(changes)
    return envelope


def run_client(root: Path, url: str, name: str, envelope: dict[str, Any], *extra: str) -> dict[str, Any]:
    path = root / f"{name}.json"
    path.write_text(json.dumps(envelope), "utf-8")
    done = subprocess.run([sys.executable, "-m", "agent_movement.a2a_client", "--url", url,
                           "--envelope", str(path), *extra],
                          capture_output=True, text=True, timeout=60)
    if not done.stdout.strip():
        raise SystemExit(f"client {name} produced no output (exit {done.returncode}): {done.stderr[-2000:]}")
    return {"exit_code": done.returncode, **json.loads(done.stdout.strip().splitlines()[-1])}


def receiver_tables(db: Path) -> dict[str, list[dict[str, Any]]]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        audit = [dict(r) for r in conn.execute(
            "SELECT movement_id, task_id, event_type, info_digest FROM audit_events ORDER BY seq")]
        corr = [dict(r) for r in conn.execute(
            "SELECT a2a_task_id, a2a_context_id, a2a_message_id, movement_id, trace_id, outcome, "
            "envelope_digest, "
            "artifact_digest FROM a2a_correlations ORDER BY seq")]
    return {"audit_events": audit, "a2a_correlations": corr}


def check(results: dict[str, dict[str, Any]], tables: dict[str, list[dict[str, Any]]],
          card: dict[str, Any] | None = None) -> list[str]:
    failures = []
    first, retry, denied = results["first"], results["retry"], results["denied"]
    unknown_cap, unknown_schema = results["unknown_capability"], results["unknown_schema"]
    legacy, client_ctx = results["legacy_alias"], results["client_context_refused"]
    if card is not None:
        extensions = [(e.get("uri"), e.get("required", False))
                      for e in card.get("capabilities", {}).get("extensions", [])]
        if extensions != [(EXTENSION_URI, True), (LEGACY_EXTENSION_URI, False)]:
            failures.append("agent card does not advertise the resolvable profile URI (plus the deprecated alias)")
    if first.get("final_state") != "TASK_STATE_COMPLETED" or first["receipt"]["artifact"]["value"] != 5:
        failures.append("first delegation did not complete with the expected artifact")
    elif first["receipt"]["replayed"]:
        failures.append("first delegation unexpectedly replayed")
    for name in ("first", "retry", "denied"):
        r = results[name]
        if r.get("context_id_source") != "server" or r.get("a2a_context_id") in (None, "", "demo-task"):
            failures.append(f"{name}: contextId was not server-generated")
    if retry.get("a2a_context_id") == first.get("a2a_context_id"):
        failures.append("retry reused the first task's server-generated contextId")
    if legacy.get("final_state") != "TASK_STATE_COMPLETED" or legacy.get("a2a_context_id") != "demo-task" \
            or legacy.get("extension_uri") != LEGACY_EXTENSION_URI:
        failures.append("deprecated URN alias with a bound client contextId was not accepted")
    if client_ctx.get("error", {}).get("type") != "InvalidParamsError":
        failures.append("client-supplied contextId was not refused by a server that did not opt in")
    if first.get("observed_states", [])[-1:] != ["TASK_STATE_COMPLETED"] or \
            "TASK_STATE_WORKING" not in first.get("observed_states", []):
        failures.append("streamed lifecycle did not show WORKING then COMPLETED")
    if retry.get("final_state") != "TASK_STATE_COMPLETED" or not retry["receipt"]["replayed"]:
        failures.append("exact retry was not answered as a replay")
    elif retry["a2a_task_id"] == first["a2a_task_id"] or \
            retry["receipt"]["artifact_digest"] != first["receipt"]["artifact_digest"]:
        failures.append("retry must be a new A2A task with the identical receipt")
    if denied.get("final_state") != "TASK_STATE_REJECTED" or denied.get("reason") != "approval_denied":
        failures.append("unapproved delegation was not rejected")
    if unknown_cap.get("error", {}).get("type") != "UnsupportedOperationError":
        failures.append("unadvertised capability was not refused by the A2A server")
    if unknown_schema.get("error", {}).get("type") != "InvalidParamsError":
        failures.append("unknown schema version was not refused by the A2A server")
    by_task = {row["a2a_task_id"]: row for row in tables["a2a_correlations"] if row["a2a_task_id"]}
    for name, outcome in (("first", "completed"), ("retry", "replayed"), ("denied", "approval_denied"),
                          ("legacy_alias", "completed")):
        row = by_task.get(results[name].get("a2a_task_id"))
        if row is None or row["outcome"] != outcome or row["a2a_context_id"] != results[name].get("a2a_context_id"):
            failures.append(f"receiver audit has no '{outcome}' row for the {name} A2A task and context IDs")
    completed = [e for e in tables["audit_events"]
                 if e["event_type"] == "handoff.completed" and e["movement_id"] == "a2a-demo-movement"]
    if len(completed) != 1 or completed[0]["info_digest"] != first.get("receipt", {}).get("artifact_digest"):
        failures.append("core audit 'handoff.completed' digest does not match the A2A artifact")
    rejected = [r for r in tables["a2a_correlations"] if r["outcome"].startswith("rejected.")]
    if len(rejected) != 3 or any(r["a2a_task_id"] for r in rejected):
        failures.append("pre-task rejections must be audited without creating A2A tasks")
    rejected_ids = {r["a2a_message_id"] for r in rejected}
    if rejected_ids != {unknown_cap.get("a2a_message_id"), unknown_schema.get("a2a_message_id"),
                        client_ctx.get("a2a_message_id")}:
        failures.append("pre-task rejections are not correlated by A2A message ID")
    if any("synthetic agent movement" in json.dumps(t) for t in tables.values()):
        failures.append("raw task text leaked into receiver audit tables")
    return failures


def main(argv: Sequence[str] = ()) -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
                            ).parse_args(list(argv))  # no options; gives the demo a --help
    if importlib.util.find_spec("a2a") is None or importlib.util.find_spec("uvicorn") is None:
        print(EXTRA_HINT, file=sys.stderr)
        raise SystemExit(2)
    with tempfile.TemporaryDirectory(prefix="agent-movement-a2a-") as tmp:
        root = Path(tmp)
        db = root / "receiver.sqlite"
        server = subprocess.Popen([sys.executable, "-m", "agent_movement.a2a_server", "--db", str(db)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert server.stdout is not None
            line = server.stdout.readline()
            if not line:
                raise SystemExit("A2A server failed to start: " + (server.stderr.read() if server.stderr else ""))
            url = json.loads(line)["url"]
            with urllib.request.urlopen(url + "/.well-known/agent-card.json", timeout=10) as response:
                card = json.load(response)
            results = {
                "first": run_client(root, url, "first", demo_envelope()),
                "retry": run_client(root, url, "retry", demo_envelope(), "--binding", "HTTP+JSON",
                                    "--no-stream"),
                "denied": run_client(root, url, "denied", demo_envelope(
                    movement_id="a2a-demo-denied", authority={"approval_ref": "not-approved"},
                    execution={"idempotency_key": "a2a-denied-operation"})),
                "unknown_capability": run_client(root, url, "unknown-capability", demo_envelope(
                    movement_id="a2a-demo-sha", task={"kind": "sha256", "text": "synthetic"},
                    execution={"idempotency_key": "a2a-sha-operation"}), "--skip-card-check"),
                "unknown_schema": run_client(root, url, "unknown-schema", demo_envelope(
                    movement_id="a2a-demo-v9", execution={"idempotency_key": "a2a-v9-operation"}),
                    "--schema-version-override", "9.0"),
                "legacy_alias": run_client(root, url, "legacy-alias", demo_envelope(
                    movement_id="a2a-demo-legacy", execution={"idempotency_key": "a2a-legacy-operation"}),
                    "--legacy-extension-uri", "--client-context-id"),
                "client_context_refused": run_client(root, url, "client-context", demo_envelope(
                    movement_id="a2a-demo-client-context",
                    execution={"idempotency_key": "a2a-client-context-operation"}),
                    "--client-context-id", "--skip-card-check"),
            }
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        tables = receiver_tables(db)
        card_summary = {
            "name": card.get("name"),
            "interfaces": [(i.get("protocolBinding"), i.get("protocolVersion"))
                           for i in card.get("supportedInterfaces", [])],
            "skills": [s.get("id") for s in card.get("skills", [])],
            "extensions": [(e.get("uri"), e.get("required", False))
                           for e in card.get("capabilities", {}).get("extensions", [])],
            "security_schemes": card.get("securitySchemes", {}),
        }
        failures = check(results, tables, card)
        print(json.dumps({"agent_card": card_summary, "results": results, "receiver": tables,
                          "proves": "delegation (not migration)", "authentication": "none (experimental)",
                          "failures": failures}, indent=2, sort_keys=True))
        if failures:
            raise SystemExit("A2A delegation demo checks failed: " + "; ".join(failures))


if __name__ == "__main__":
    main(sys.argv[1:])
