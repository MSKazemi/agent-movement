"""Deterministic synthetic bypass report for the Linux-seccomp research profile."""

from __future__ import annotations

import argparse
import json
import socket
import socketserver
import sys
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

from .core import PolicyDenied
from .egress_lab import run_guarded_agent
from .egress_sandbox import supported

_CHECKED_SYSCALLS = (
    "tcp", "legacy_http", "a2a_http", "udp", "ipv6", "unix",
    "spawn", "fork", "raw_syscall",
)


class _Listener(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.hits = 0
        self.recorded = threading.Event()
        super().__init__(("127.0.0.1", 0), _ListenerHandler)


class _ListenerHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(1.0)
        with suppress(OSError):
            self.request.recv(512)
        self.server.hits += 1  # type: ignore[attr-defined]
        self.server.recorded.set()  # type: ignore[attr-defined]
        with suppress(OSError):
            self.request.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")


def _case(name: str, observed: str, expected: str, stage: str) -> dict[str, str]:
    return {"case_id": name, "stage": stage, "expected": expected, "observed": observed}


def build_report() -> dict[str, Any]:
    """Execute distinct-process control/probe; never reach the public Internet."""
    if not supported():
        raise RuntimeError("Linux x86_64 seccomp support is mandatory; never silently skip")
    script = Path(__file__).with_name("egress_probe.py")
    effect_count = 0

    def delegate() -> str:
        nonlocal effect_count
        effect_count += 1
        return "committed"

    def deny() -> str:
        raise PolicyDenied("synthetic revoked permission")

    with _Listener() as listener:
        monitor = threading.Thread(target=listener.serve_forever, daemon=True)
        monitor.start()
        try:
            # This *unfenced* local baseline is essential. A test removing the
            # network guard should turn the otherwise blocked network probes red.
            with socket.create_connection(("127.0.0.1", listener.server_address[1]), timeout=1) as sock:
                sock.sendall(b"synthetic-unfenced-control\n")
            baseline_hit = listener.recorded.wait(timeout=2)
            baseline_count = listener.hits

            allowed = run_guarded_agent(
                script, {"task-1": delegate}, probe_port=listener.server_address[1]
            )
            denied_op = run_guarded_agent(
                script, {"task-1": delegate}, operation="clone",
                probe_port=listener.server_address[1],
            )
            denied_grant = run_guarded_agent(
                script, {"task-1": deny}, probe_port=listener.server_address[1]
            )
            denied_unknown = run_guarded_agent(
                script, {"task-1": delegate}, task_id="unknown-task",
                probe_port=listener.server_address[1],
            )
            try:
                payload = json.loads(allowed.stdout)
            except ValueError:
                payload = {}
            cases = [_case(name, str(payload.get(name, "no_response")), "blocked", "kernel")
                     for name in _CHECKED_SYSCALLS]
            for name, result, want in (
                ("authorized_delegation", allowed, "committed"),
                ("unsupported_clone", denied_op, "denied"),
                ("revoked_grant", denied_grant, "denied"),
                ("unknown_task", denied_unknown, "denied"),
            ):
                try:
                    observed = json.loads(result.stdout).get("broker", "missing")
                except ValueError:
                    observed = "invalid_output"
                if result.exit_code != 0 or result.broker_status != observed or result.request_count != 1:
                    observed = "invalid_process_result"
                cases.append(_case(name, observed, want, "trusted_pipe_broker"))
            cases.append(_case("unfenced_loopback_control", "received" if baseline_hit else "missing",
                               "received", "independent_listener"))
            cases.append(_case("isolated_listener_hits", str(listener.hits - baseline_count),
                               "0", "independent_listener"))
            cases.append(_case("simulated_effect_count", str(effect_count), "1", "trusted_process"))
        finally:
            listener.shutdown()
            monitor.join(timeout=2)
    return {
        "schema": "agent-movement/isolated-egress-v0.1",
        "platform": "linux-x86_64",
        "model": "seccomp syscall-deny + one-command pipe broker; no filesystem confinement",
        "cases": cases,
        "unexpected": sum(item["observed"] != item["expected"] for item in cases),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded Linux agent egress experiment")
    parser.add_argument("--output", type=Path, help="Save stable, secret-free JSON report")
    args = parser.parse_args()
    report = build_report()
    content = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(content, encoding="utf-8")
    print(json.dumps({"cases": len(report["cases"]), "unexpected": report["unexpected"]}, sort_keys=True))
    return int(report["unexpected"] != 0)


if __name__ == "__main__":
    sys.exit(main())
