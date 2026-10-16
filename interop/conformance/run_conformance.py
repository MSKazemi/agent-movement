#!/usr/bin/env python3
"""A2A conformance smoke for the agent-movement A2A adapter (issue #28).

Starts ``python -m agent_movement.a2a_server`` on loopback, then

1. runs the official A2A TCK (a2aproject/a2a-tck, a checkout given by ``--tck``) against it and
   compares every requirement's status with ``tck-expected.json``, where each non-passing
   requirement is tied to a documented deviation (docs/a2a-adapter.md, "Conformance");
2. optionally (``--inspector``) applies the A2A Inspector's own validators
   (a2aproject/a2a-inspector ``backend/validators.py``) to the Agent Card and to every event of
   one real handoff, converted the way the Inspector backend converts them.

Exit status: 0 when nothing regressed (an expected PASS that no longer passes, or a FAIL that is
not a recorded deviation, is a regression), 1 on a regression or an Inspector validation error,
2 on a setup error. A known deviation that starts passing is reported, not failed: update the
expectations file.

Needs the ``a2a`` extra in the Python running this script. The TCK runs in its own environment
(``--tck-python``, default ``<tck>/.venv/bin/python``). Synthetic data only; loopback only.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "tck-expected.json"
# The server CLI's default approval (a2a_server --task-id/--approval/--origin-id/--receiver-id).
DEMO_ENVELOPE = {
    "schema_version": "0.1.0-draft", "movement_id": "conformance-movement", "logical_task_id": "demo-task",
    "operation": "delegate", "origin": {"agent_id": "agent-a"}, "destination": {"agent_id": "agent-b"},
    "task": {"kind": "word_count", "text": "synthetic conformance smoke text"},
    "context": {"classification": "synthetic"}, "authority": {"approval_ref": "demo-approval"},
    "execution": {"idempotency_key": "conformance-op-1"}, "observability": {"trace_id": "conformance-trace"},
}


class SetupError(RuntimeError):
    pass


def start_server(python: str, db: Path) -> tuple[subprocess.Popen, str]:
    server = subprocess.Popen([python, "-m", "agent_movement.a2a_server", "--db", str(db), "--port", "0"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    line = server.stdout.readline()
    if not line:
        server.kill()
        raise SetupError("A2A server did not start: " + server.stderr.read())
    return server, json.loads(line)["url"]


def stop_server(server: subprocess.Popen) -> None:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()
    for stream in (server.stdout, server.stderr):
        stream.close()


def run_tck(tck: Path, tck_python: str, url: str, out: Path, timeout: float) -> dict[str, Any]:
    reports = tck / "reports"
    shutil.rmtree(reports, ignore_errors=True)
    log = out / "tck.log"
    with log.open("w", encoding="utf-8") as handle:
        # The TCK exits non-zero whenever any requirement fails, deviations included; the
        # verdict comes from comparing compatibility.json with the expectations below.
        subprocess.run([tck_python, "run_tck.py", "--sut-host", url], cwd=tck, stdout=handle,
                       stderr=subprocess.STDOUT, timeout=timeout, check=False)
    report = reports / "compatibility.json"
    if not report.is_file():
        raise SetupError(f"TCK wrote no {report}; see {log}")
    shutil.copytree(reports, out / "tck-reports", dirs_exist_ok=True)
    return json.loads(report.read_text("utf-8"))


def compare(report: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    actual = {rid: entry["status"] for rid, entry in report["per_requirement"].items()}
    wanted = {rid: entry["status"] for rid, entry in expected["requirements"].items()}
    regressions, improvements, other = [], [], []
    for rid in sorted(set(actual) | set(wanted)):
        got, want = actual.get(rid, "ABSENT"), wanted.get(rid, "ABSENT")
        if got == want:
            continue
        change = {"requirement": rid, "expected": want, "actual": got,
                  "errors": report["per_requirement"].get(rid, {}).get("errors", [])[:2]}
        if want == "PASS" or got == "FAIL":
            regressions.append(change)
        elif want == "FAIL" and got == "PASS":
            improvements.append(change)
        else:
            other.append(change)
    counts: dict[str, int] = {}
    for status in actual.values():
        counts[status] = counts.get(status, 0) + 1
    return {"counts": dict(sorted(counts.items())), "summary": report.get("summary", {}),
            "per_transport": report.get("per_transport", {}), "regressions": regressions,
            "improvements": improvements, "other_changes": other}


def load_inspector_validators(inspector: Path) -> Any:
    path = inspector / "backend" / "validators.py"
    spec = importlib.util.spec_from_file_location("a2a_inspector_validators", path)
    if spec is None or spec.loader is None or not path.is_file():
        raise SetupError(f"no A2A Inspector validators at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def handoff_events(url: str) -> list[dict[str, Any]]:
    """Stream one handoff with the Python SDK client; events as the Inspector backend sees them."""
    import httpx
    from google.protobuf.json_format import MessageToDict

    from a2a.client import ClientCallContext, ClientConfig, ClientFactory
    from a2a.client.service_parameters import ServiceParametersFactory, with_a2a_extensions
    from a2a.types import SendMessageRequest
    from agent_movement.a2a_client import build_message, fetch_card
    from agent_movement.a2a_profile import EXTENSION_URI

    kinds = {"task": "task", "message": "message", "status_update": "status-update",
             "artifact_update": "artifact-update"}
    events = []
    async with httpx.AsyncClient(timeout=10) as http:
        client = ClientFactory(ClientConfig(streaming=True, httpx_client=http)).create(await fetch_card(url, http))
        call = ClientCallContext(service_parameters=ServiceParametersFactory.create(
            [with_a2a_extensions([EXTENSION_URI])]), timeout=10)
        try:
            async for event in client.send_message(SendMessageRequest(message=build_message(DEMO_ENVELOPE)),
                                                   context=call):
                field = event.WhichOneof("payload")
                data = MessageToDict(getattr(event, field), preserving_proto_field_name=False)
                data["kind"] = kinds[field]  # backend/app.py adds 'kind' for v1.0 protobuf events
                events.append(data)
        finally:
            await client.close()
    return events


def run_inspector(inspector: Path, url: str) -> dict[str, Any]:
    validators = load_inspector_validators(inspector)
    with urllib.request.urlopen(url + "/.well-known/agent-card.json", timeout=10) as response:
        card = json.load(response)
    # backend/app.py _get_agent_card_dict: v1.0 cards get 'url' from supportedInterfaces[0].
    card.setdefault("url", card["supportedInterfaces"][0]["url"])
    events = asyncio.run(handoff_events(url))
    checked = [{"kind": e["kind"], "state": e.get("status", {}).get("state"),
                "validation_errors": validators.validate_message(e)} for e in events]
    return {"agent_card_validation_errors": validators.validate_agent_card(card), "events": checked}


def git_head(path: Path) -> str:
    done = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return done.stdout.strip() or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tck", type=Path, help="a2a-tck checkout (skip the TCK if omitted)")
    parser.add_argument("--tck-python", help="Python of the TCK's environment (default <tck>/.venv/bin/python)")
    parser.add_argument("--inspector", type=Path, help="a2a-inspector checkout (skip if omitted)")
    parser.add_argument("--expected", type=Path, default=EXPECTED)
    parser.add_argument("--out", type=Path, default=Path("a2a-conformance"))
    parser.add_argument("--timeout", type=float, default=900)
    options = parser.parse_args()
    if not options.tck and not options.inspector:
        parser.error("give --tck and/or --inspector")
    options.out.mkdir(parents=True, exist_ok=True)
    expected = json.loads(options.expected.read_text("utf-8"))
    summary: dict[str, Any] = {"server": "python -m agent_movement.a2a_server"}
    failed = False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            if options.tck:
                tck_python = options.tck_python or str(options.tck / ".venv" / "bin" / "python")
                server, url = start_server(sys.executable, Path(tmp) / "tck.sqlite")
                try:
                    report = run_tck(options.tck, tck_python, url, options.out, options.timeout)
                finally:
                    stop_server(server)
                result = compare(report, expected)
                result.update(commit=git_head(options.tck), expected_commit=expected["tck"]["commit"])
                summary["tck"] = result
                failed |= bool(result["regressions"])
            if options.inspector:
                server, url = start_server(sys.executable, Path(tmp) / "inspector.sqlite")
                try:
                    result = run_inspector(options.inspector, url)
                finally:
                    stop_server(server)
                result["commit"] = git_head(options.inspector)
                summary["inspector"] = result
                failed |= bool(result["agent_card_validation_errors"]) or any(
                    e["validation_errors"] for e in result["events"])
                failed |= [e["state"] for e in result["events"]][-1:] != ["TASK_STATE_COMPLETED"]
    except (SetupError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    summary["verdict"] = "regression" if failed else "ok"
    (options.out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
