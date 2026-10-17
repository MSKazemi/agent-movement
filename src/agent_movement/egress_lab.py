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
    timeout: float = 15.0, child_uid: int | None = None,
    child_gid: int | None = None, protected_file: Path | None = None,
    protected_db: Path | None = None, protected_parent_fd: int | None = None,
    unapproved_write_dir: Path | None = None,
) -> SandboxResult:
    """Run a separately fenced synthetic worker and a one-task trusted pipe broker.

    With child_uid/child_gid, refuse to start unless the caller is a root-owned
    trusted supervisor; drop every child real/effective/saved UID/GID and group
    before installing the syscall fence. Root-only secret paths can then be
    tested for OS-level denial. No namespace, global egress or arbitrary-file
    containment is claimed. The non-UID legacy experiment is unchanged.
    """
    if not supported():
        raise RuntimeError("independent egress experiment requires Linux x86_64")
    if (child_uid is None) != (child_gid is None):
        raise ValueError("UID and GID must be provided together")
    separated = child_uid is not None
    if separated and (os.geteuid() != 0 or type(child_uid) is not int or type(child_gid) is not int
                      or not 1 <= child_uid <= 65534 or not 1 <= child_gid <= 65534):
        # Privilege separation is an explicit requirement for this profile.
        # Do not silently fall back to a same-UID seccomp-only child.
        raise RuntimeError("isolated worker requires root supervisor and non-root UID/GID")
    if any(x is not None for x in (protected_file, protected_db, protected_parent_fd,
                                   unapproved_write_dir)) and not separated:
        raise ValueError("protected-resource probe requires the distinct-UID profile")
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
    # Pytest can add src/ to sys.path without exporting PYTHONPATH. Child cwd is
    # deliberately neutral, so explicitly pass only this package source path.
    package_root = str(Path(__file__).resolve().parents[1])
    # The ordinary historical egress experiment keeps its original import behavior.
    # The root-owned secure lab deliberately disallows caller PYTHONPATH, user-site
    # imports and a writable current directory on sys.path (-P below).
    if separated:
        env["PYTHONPATH"] = package_root
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONSAFEPATH"] = "1"
        env["AMV_ISOLATION_UID"] = str(child_uid)
        env["AMV_ISOLATION_GID"] = str(child_gid)
        env["AMV_TEST_PARENT_PID"] = str(os.getpid())
        if protected_file is not None:
            env["AMV_TEST_PROTECTED_FILE"] = str(Path(protected_file).resolve(strict=True))
        if protected_db is not None:
            env["AMV_TEST_PROTECTED_DB"] = str(Path(protected_db).resolve(strict=True))
        if unapproved_write_dir is not None:
            target_dir = Path(unapproved_write_dir).resolve(strict=True)
            if not target_dir.is_dir():
                raise ValueError("unapproved write probe requires an existing directory")
            env["AMV_TEST_WRITABLE_DIR"] = str(target_dir)
        if protected_parent_fd is not None:
            if type(protected_parent_fd) is not int or protected_parent_fd < 3:
                raise ValueError("invalid protected parent FD")
            env["AMV_TEST_PARENT_FD"] = str(protected_parent_fd)
    else:
        extra_paths = os.environ.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join((package_root, extra_paths)) if extra_paths else package_root

    state: dict[str, Any] = {"status": "not_requested", "count": 0}
    child: subprocess.Popen[str]
    try:
        child = subprocess.Popen(
            [sys.executable, *(["-P"] if separated else []),
             "-m", "agent_movement.egress_sandbox", str(script)],
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
