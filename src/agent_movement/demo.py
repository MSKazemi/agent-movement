"""Start two separate local processes, approve and replay a synthetic handoff."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .core import SCHEMA_VERSION, EffectGateway, PolicyDenied, SQLiteStore


def handoff(url: str, message: dict) -> tuple[int, dict]:
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        with exc:  # HTTPError wraps an open response; close it
            return exc.code, json.load(exc)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agent-movement-") as root:
        process = subprocess.Popen([
            sys.executable, "-m", "agent_movement.http", "--db", str(Path(root) / "ledger.sqlite")
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert process.stdout is not None
            advertised = json.loads(process.stdout.readline())
            url = f"http://127.0.0.1:{advertised['port']}/v0/handoffs"
            message = {
                "schema_version": SCHEMA_VERSION, "movement_id": "demo-movement",
                "logical_task_id": "demo-task", "operation": "delegate",
                "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
                "task": {"kind": "word_count", "text": "synthetic agent movement test task"},
                "context": {"classification": "synthetic"},
                "authority": {"approval_ref": "demo-approval"},
                "execution": {"idempotency_key": "demo-operation"},
                "observability": {"trace_id": "demo-trace"},
            }
            first = handoff(url, message)
            replay = handoff(url, message)
            denied = handoff(url, {**message, "authority": {"approval_ref": "not-approved"},
                                   "movement_id": "demo-denied", "execution": {"idempotency_key": "denied-operation"}})
            # Separate bounded experiment: fence an old simulated worker.
            effects = EffectGateway(SQLiteStore(Path(root) / "ledger.sqlite"))
            old_epoch = effects.claim("fenced-demo-task", "agent-a")
            new_epoch = effects.transfer("fenced-demo-task", "agent-a", old_epoch, "agent-b")
            stale_blocked = False
            try:
                effects.commit("fenced-demo-task", "agent-a", old_epoch, "effect-1", "synthetic")
            except PolicyDenied:
                stale_blocked = True
            new_committed = effects.commit("fenced-demo-task", "agent-b", new_epoch,
                                           "effect-1", "synthetic")
            print(json.dumps({"first": first, "replay": replay, "denied": denied,
                              "fencing": {"old_epoch": old_epoch, "new_epoch": new_epoch,
                                          "stale_blocked": stale_blocked,
                                          "new_committed": new_committed}}, indent=2))
            if not stale_blocked or not new_committed:
                raise SystemExit("fencing demonstration failed")
            if first[0] != 200 or first[1]["artifact"]["value"] != 5 or first[1]["replayed"]:
                raise SystemExit("first handoff failed")
            if replay[0] != 200 or not replay[1]["replayed"] or denied[0] != 403:
                raise SystemExit("replay/denial checks failed")
        finally:
            process.terminate()
            try:
                # communicate() drains and closes stdout/stderr (no leaked pipes).
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


if __name__ == "__main__":
    main()
