"""Bounded test harness: separate untrusted process + trusted pipe-only broker.

The harness is not a production launcher, OS container, or file confinement tool.
Caller retains credential/control custody; attacker sees only an allowlisted env and
anonymous broker pipe FDs. A kernel seccomp denylist blocks socket/spawn syscalls.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import PolicyDenied
from .egress_sandbox import supported

_MAX_REQUEST = 1024
_MAX_RESPONSE = 256
_TASK_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    broker_status: str
    request_count: int


def _interpret_request(raw: bytes, allowed: Mapping[str, Callable[[], str]]) -> str:
    """Strict single-command proxy; never trust the child to supply a grant or tool args."""
    if not raw.endswith(b"\n") or len(raw) > _MAX_REQUEST or raw.count(b"\n") != 1:
        return "invalid_request"
    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if len(pairs) != len({key for key, _ in pairs}):
            raise ValueError("duplicate object key")
        return dict(pairs)

    try:
        command: Any = json.loads(raw, object_pairs_hook=unique_keys)
    except (UnicodeDecodeError, ValueError):
        return "invalid_request"
    if (not isinstance(command, dict) or set(command) != {"version", "operation", "task_id"}
            or type(command["version"]) is not int or command["version"] != 1
            or command["operation"] != "delegate"
            or not isinstance(command["task_id"], str)
            or not _TASK_ID.fullmatch(command["task_id"])):
        return "denied"
    handler = allowed.get(command["task_id"])
    if handler is None:
        return "denied"
    try:
        outcome = handler()  # trusted process, not the attacker interpreter
    except PolicyDenied:
        return "denied"
    except Exception:  # noqa: BLE001 - callback failures must not escape into an untrusted broker reply
        # Do not disguise implementation errors as successful policy denials.
        return "backend_error"
    return outcome if outcome in ("committed", "replayed") else "backend_error"


def run_guarded_agent(
    script: Path, allowed: Mapping[str, Callable[[], str]], *,
    operation: str = "delegate", task_id: str = "task-1", probe_port: int,
    timeout: float = 15.0,
) -> SandboxResult:
    """Run agent source after kernel policy installation in a distinct process.

    This deliberately grants no arbitrary network, subprocess, host data access
    policy or external effect capability. The only modeled authorized effect is
    a named callback held by the trusted parent and invoked via a pipe broker.
    """
    if not supported():
        raise RuntimeError("independent egress experiment requires Linux x86_64")
    script = Path(script).resolve(strict=True)
    if not script.is_file():
        raise ValueError("attacker script is not a file")
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    workdir = tempfile.gettempdir()  # Avoid running in a package dir that shadows stdlib modules.
    env = {"PATH": os.path.dirname(sys.executable), "LANG": "C.UTF-8",
           "PYTHONUNBUFFERED": "1", "HOME": workdir,
           "AMV_BROKER_REQ_FD": str(request_write),
           "AMV_BROKER_RESP_FD": str(response_read),
           "AMV_PROBE_PORT": str(probe_port), "AMV_PROBE_OP": operation,
           "AMV_PROBE_TASK": task_id}
    # Local source checkouts need PYTHONPATH; installed packages on CI do not.
    if "PYTHONPATH" in os.environ:
        env["PYTHONPATH"] = os.environ["PYTHONPATH"]

    state: dict[str, Any] = {"status": "not_requested", "count": 0}
    child: subprocess.Popen[str]
    try:
        child = subprocess.Popen(
            [sys.executable, "-m", "agent_movement.egress_sandbox", str(script)],
            cwd=workdir, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            pass_fds=(request_write, response_read), close_fds=True,
            start_new_session=True,
        )
    finally:
        os.close(request_write)
        os.close(response_read)

    def broker() -> None:
        with os.fdopen(request_read, "rb", buffering=0) as incoming:
            # One command maximum. Never stream unrestricted attacker input.
            raw = incoming.readline(_MAX_REQUEST + 1)
        if raw:
            state["count"] = 1
            state["status"] = _interpret_request(raw, allowed)
        with os.fdopen(response_write, "wb", buffering=0) as outgoing:
            message = json.dumps({"status": state["status"]}, sort_keys=True).encode() + b"\n"
            assert len(message) <= _MAX_RESPONSE
            with suppress(BrokenPipeError):
                outgoing.write(message)

    thread = threading.Thread(target=broker, daemon=True)
    thread.start()
    try:
        stdout, stderr = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        child.kill()
        child.communicate()
        raise RuntimeError("sandboxed attacker did not exit") from None
    finally:
        thread.join(timeout=2.0)
    if thread.is_alive():
        raise RuntimeError("broker thread failed to finish")
    return SandboxResult(child.returncode, stdout, stderr, state["status"], state["count"])
