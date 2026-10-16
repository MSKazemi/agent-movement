"""Start two separate local processes, approve and replay a synthetic handoff.

``--receipts OUTDIR`` (default off, ``signing`` extra) also signs movement receipts on
both HTTP sides and for the fenced effect commits, exports them as an evidence bundle
plus a separate trust anchor file, and verifies the bundle offline (issue #32).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .core import SCHEMA_VERSION, EffectGateway, PolicyDenied, SQLiteStore


def handoff(url: str, message: dict, receipts: Any = None, destination_principal: str | None = None) -> tuple[int, dict]:
    if receipts is not None:  # sign the dispatch before any byte is sent
        receipts.dispatched(message, destination_principal)
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        with exc:  # HTTPError wraps an open response; close it
            return exc.code, json.load(exc)


class _Receipts:
    """Sender-side and tool-side emitters for one demo run, plus the bundle export."""

    def __init__(self, outdir: Path, root: Path):
        from .live_receipts import ReceiptEmitter
        self.outdir = outdir
        self.started = datetime.now(timezone.utc).replace(microsecond=0)
        self.receiver_log = root / "receipts-agent-b.jsonl"
        self.sender = ReceiptEmitter(root / "receipts-agent-a.jsonl", name="agent-a")
        self.tool = ReceiptEmitter(root / "receipts-effect-gateway.jsonl", name="effect-gateway", role="tool")

    def export_and_verify(self, receiver_key: dict[str, str]) -> dict[str, Any]:
        from .live_receipts import export_run
        from .receipts import verify_bundle
        bundle, trust = export_run(
            self.outdir, receipt_logs=[self.sender.log_path, self.receiver_log], tool_logs=[self.tool.log_path],
            descriptors=[self.sender.descriptor(), receiver_key, self.tool.descriptor()], not_before=self.started)
        report = verify_bundle(bundle, trust)
        return {"bundle": str(bundle), "trust_anchors": str(trust),
                "verify": f"python -m agent_movement.receipts verify --trust {trust} {bundle}",
                "receipt_verdicts": {k: v for k, v in report["receipt_verdicts"].items() if v},
                "emission_failures": self.sender.failures + self.tool.failures,
                "verifier_exit_code": report["exit_code"]}


def main(argv: Sequence[str] = ()) -> None:
    """Run the demo. ``argv`` holds command-line options (only the opt-in ``--receipts``)."""
    parser = argparse.ArgumentParser(description="Core local handoff demo: a loopback receiver process, an approved "
                                     "handoff, an idempotent replay, a denied request and stale-epoch fencing. "
                                     "Synthetic, stdlib-only, not A2A.")
    parser.add_argument("--receipts", type=Path, metavar="OUTDIR",
                        help="opt in: sign movement receipts and write OUTDIR/live-run/ (evidence bundle) and "
                             "OUTDIR/trust-anchors.json (out-of-band anchors); needs the 'signing' extra")
    options = parser.parse_args(list(argv))
    if options.receipts is not None:
        from .receipts import HAVE_ED25519
        from .live_receipts import BUNDLE_NAME
        if not HAVE_ED25519:
            parser.exit(2, 'error: --receipts needs the optional extra: python -m pip install -e ".[signing]"\n')
        existing = options.receipts / BUNDLE_NAME
        if existing.exists() and any(existing.iterdir()):
            parser.exit(2, f"error: {existing} already holds evidence; choose an empty --receipts directory\n")
    with tempfile.TemporaryDirectory(prefix="agent-movement-") as root:
        receipts = _Receipts(options.receipts, Path(root)) if options.receipts is not None else None
        command = [sys.executable, "-m", "agent_movement.http", "--db", str(Path(root) / "ledger.sqlite")]
        if receipts is not None:
            command += ["--receipts-log", str(receipts.receiver_log)]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert process.stdout is not None
            advertised = json.loads(process.stdout.readline())
            url = f"http://127.0.0.1:{advertised['port']}/v0/handoffs"
            sender = receipts.sender if receipts is not None else None
            # Learned from the receiver process itself, never from the evidence bundle.
            receiver_key = advertised.get("receipt_key", {})
            to = receiver_key.get("principal")
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
            first = handoff(url, message, sender, to)
            replay = handoff(url, message, sender, to)
            denied = handoff(url, {**message, "authority": {"approval_ref": "not-approved"},
                                   "movement_id": "demo-denied", "execution": {"idempotency_key": "denied-operation"}},
                             sender, to)
            # Separate bounded experiment: fence an old simulated worker.
            store = SQLiteStore(Path(root) / "ledger.sqlite")
            if receipts is not None:
                from .live_receipts import RecordingEffectGateway
                effects: EffectGateway = RecordingEffectGateway(store, receipts.tool)
            else:
                effects = EffectGateway(store)
            old_epoch = effects.claim("fenced-demo-task", "agent-a")
            new_epoch = effects.transfer("fenced-demo-task", "agent-a", old_epoch, "agent-b")
            stale_blocked = False
            try:
                effects.commit("fenced-demo-task", "agent-a", old_epoch, "effect-1", "synthetic")
            except PolicyDenied:
                stale_blocked = True
            new_committed = effects.commit("fenced-demo-task", "agent-b", new_epoch,
                                           "effect-1", "synthetic")
            result: dict[str, Any] = {"first": first, "replay": replay, "denied": denied,
                                      "fencing": {"old_epoch": old_epoch, "new_epoch": new_epoch,
                                                  "stale_blocked": stale_blocked,
                                                  "new_committed": new_committed}}
            if receipts is not None:
                result["receipts"] = receipts.export_and_verify(receiver_key)
            print(json.dumps(result, indent=2))
            if not stale_blocked or not new_committed:
                raise SystemExit("fencing demonstration failed")
            if first[0] != 200 or first[1]["artifact"]["value"] != 5 or first[1]["replayed"]:
                raise SystemExit("first handoff failed")
            if replay[0] != 200 or not replay[1]["replayed"] or denied[0] != 403:
                raise SystemExit("replay/denial checks failed")
            if receipts is not None and result["receipts"]["verifier_exit_code"] != 0:
                raise SystemExit("exported receipt bundle did not verify")
        finally:
            process.terminate()
            try:
                # communicate() drains and closes stdout/stderr (no leaked pipes).
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()


if __name__ == "__main__":
    main(sys.argv[1:])
