"""Start two separate local processes, approve and replay a synthetic handoff.

The parent also plays a synthetic user authority (an HS256 test key, stdlib-only) and
revokes the approval at runtime with a signed notice over ``POST /v0/revocations``
(issue #38): forged and unsigned notices are refused, the revocation is idempotent, and
afterwards a new handoff and the next simulated effect of the delegated task are denied.

``--receipts OUTDIR`` (default off, ``signing`` extra) also signs movement receipts on
both HTTP sides and for the fenced effect commits, exports them as an evidence bundle
plus a separate trust anchor file, and verifies the bundle offline (issue #32).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .core import SCHEMA_VERSION, EffectGateway, PolicyDenied, SQLiteStore
from .trust import HmacKey, issue_revocation, seal


def handoff(url: str, message: dict[str, Any], receipts: Any = None,
            destination_principal: str | None = None) -> tuple[int, dict[str, Any]]:
    if receipts is not None:  # sign the dispatch before any byte is sent
        receipts.dispatched(message, destination_principal)
    return post(url, message)


def post(url: str, message: Any) -> tuple[int, dict[str, Any]]:
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    # The demo only ever posts to the http://127.0.0.1 receiver it started itself.
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        with exc:  # HTTPError wraps an open response; close it
            return exc.code, json.load(exc)


class _Receipts:
    """Sender-side and tool-side emitters for one demo run, plus the bundle export."""

    def __init__(self, outdir: Path, root: Path):
        from .live_receipts import ReceiptEmitter
        self.outdir = outdir
        self.started = datetime.now(UTC).replace(microsecond=0)
        self.receiver_log = root / "receipts-agent-b.jsonl"
        self.sender = ReceiptEmitter(root / "receipts-agent-a.jsonl", name="agent-a")
        self.tool = ReceiptEmitter(root / "receipts-effect-gateway.jsonl", name="effect-gateway", role="tool")

    def export_and_verify(self, receiver_key: dict[str, str], notices: Sequence[Any] = ()) -> dict[str, Any]:
        from .live_receipts import export_run
        from .receipts import verify_bundle
        bundle, trust = export_run(
            self.outdir, receipt_logs=[self.sender.log_path, self.receiver_log], tool_logs=[self.tool.log_path],
            descriptors=[self.sender.descriptor(), receiver_key, self.tool.descriptor()], not_before=self.started,
            notices=notices)
        report = verify_bundle(bundle, trust)
        return {"bundle": str(bundle), "trust_anchors": str(trust),
                "verify": f"python -m agent_movement.receipts verify --trust {trust} {bundle}",
                "receipt_verdicts": {k: v for k, v in report["receipt_verdicts"].items() if v},
                "emission_failures": self.sender.failures + self.tool.failures,
                "revocation_notice_subjects": sorted(s["status"] for s in report["subjects"]
                                                     if s["role"] == "revocation_notice"),
                "verifier_exit_code": report["exit_code"]}


def _write_private(path: Path, obj: Any) -> None:
    """Out-of-band provisioning file for the receiver; holds a shared secret, so mode 0600."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(obj, handle)


def revocation_scenario(base: str, message: dict[str, Any], effects: EffectGateway, authority: HmacKey,
                        sender: Any = None, to: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Runtime revocation of ``demo-approval`` between two simulated effects of ``demo-task``."""
    epoch = effects.claim("demo-task", "agent-b")  # the delegated task's executor on agent-b
    before = effects.commit("demo-task", "agent-b", epoch, "demo-effect-1", "synthetic")
    now = int(time.time())
    notice = issue_revocation(authority, "demo-approval", now)
    impostor = HmacKey.generate(authority.kid)  # same kid, different secret: a forgery
    forged = post(base + "/v0/revocations", issue_revocation(impostor, "demo-approval", now))
    unsigned = post(base + "/v0/revocations", notice["payload"])
    wrong_purpose = post(base + "/v0/revocations", seal("grant", notice["payload"], authority))
    revoked = post(base + "/v0/revocations", notice)
    repeated = post(base + "/v0/revocations", notice)
    after = handoff(base + "/v0/handoffs", {**message, "movement_id": "demo-after-revocation",
                                             "execution": {"idempotency_key": "after-revocation-operation"}},
                    sender, to)
    replay_after = handoff(base + "/v0/handoffs", message, sender, to)
    try:
        effects.commit("demo-task", "agent-b", epoch, "demo-effect-2", "synthetic")
        effect_blocked = False
    except PolicyDenied:
        effect_blocked = True
    return {"effect_before_revocation_committed": before, "forged_notice": forged[0],
            "unsigned_notice": unsigned[0], "wrong_purpose_signature": wrong_purpose[0],
            "revoked": revoked[0], "replayed": repeated[1].get("replayed"),
            "new_handoff_after_revocation": after[0], "replay_after_revocation": replay_after[0],
            "effect_after_revocation_blocked": effect_blocked}, notice


EXPECTED_REVOCATION = {"effect_before_revocation_committed": True, "forged_notice": 401, "unsigned_notice": 401,
                       "wrong_purpose_signature": 401, "revoked": 200, "replayed": True,
                       "new_handoff_after_revocation": 403, "replay_after_revocation": 403,
                       "effect_after_revocation_blocked": True}


def main(argv: Sequence[str] = ()) -> None:
    """Run the demo. ``argv`` holds command-line options (only the opt-in ``--receipts``)."""
    parser = argparse.ArgumentParser(description="Core local handoff demo: a loopback receiver process, an approved "
                                     "handoff, an idempotent replay, a denied request, stale-epoch fencing and a "
                                     "runtime revocation by a signed notice. Synthetic, stdlib-only, not A2A.")
    parser.add_argument("--receipts", type=Path, metavar="OUTDIR",
                        help="opt in: sign movement receipts and write OUTDIR/live-run/ (evidence bundle) and "
                             "OUTDIR/trust-anchors.json (out-of-band anchors); needs the 'signing' extra")
    options = parser.parse_args(list(argv))
    if options.receipts is not None:
        from .live_receipts import BUNDLE_NAME
        from .receipts import HAVE_ED25519
        if not HAVE_ED25519:
            parser.exit(2, 'error: --receipts needs the optional extra: python -m pip install -e ".[signing]"\n')
        existing = options.receipts / BUNDLE_NAME
        if existing.exists() and any(existing.iterdir()):
            parser.exit(2, f"error: {existing} already holds evidence; choose an empty --receipts directory\n")
    with tempfile.TemporaryDirectory(prefix="agent-movement-") as root:
        receipts = _Receipts(options.receipts, Path(root)) if options.receipts is not None else None
        # The parent plays the synthetic user authority and provisions its key out of band.
        authority = HmacKey.generate("demo-authority")
        _write_private(Path(root) / "revocation-authority.json", authority.export())
        command = [sys.executable, "-m", "agent_movement.http", "--db", str(Path(root) / "ledger.sqlite"),
                   "--revocation-authority", str(Path(root) / "revocation-authority.json")]
        if receipts is not None:
            command += ["--receipts-log", str(receipts.receiver_log)]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert process.stdout is not None
            advertised = json.loads(process.stdout.readline())
            base = f"http://127.0.0.1:{advertised['port']}"
            url = base + "/v0/handoffs"
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
            revocation, notice = revocation_scenario(base, message, effects, authority, sender, to)
            result: dict[str, Any] = {"first": first, "replay": replay, "denied": denied,
                                      "fencing": {"old_epoch": old_epoch, "new_epoch": new_epoch,
                                                  "stale_blocked": stale_blocked,
                                                  "new_committed": new_committed},
                                      "revocation": revocation}
            if receipts is not None:
                result["receipts"] = receipts.export_and_verify(receiver_key, [notice])
            print(json.dumps(result, indent=2))
            if not stale_blocked or not new_committed:
                raise SystemExit("fencing demonstration failed")
            if revocation != EXPECTED_REVOCATION:
                raise SystemExit("revocation demonstration failed")
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
